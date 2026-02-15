import requests
import os
import json
import random  # [추가됨] 데일리 단어 뽑기에 필수
import datetime # [추가됨] 날짜 처리에 필수
import re
import time
import hashlib
from django.conf import settings
from gensim.models import KeyedVectors
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.core.cache import cache
from .models import GameRecord

# 워드프레스 API 기본 주소 설정
WP_BASE_URL = getattr(settings, 'WP_BASE_URL', 'http://127.0.0.1:4080/wp-json/wp/v2')
WP_REQUEST_TIMEOUT = getattr(settings, 'WP_REQUEST_TIMEOUT', 5)
WP_CACHE_TIMEOUT = getattr(settings, 'WP_CACHE_TIMEOUT', 300)

# settings.py에서 설정 가져오기
MODEL_PATH = getattr(settings, 'WORD2VEC_MODEL_PATH', None)
LIMIT = getattr(settings, 'WORD2VEC_LIMIT', 300000)

model = None
CANDIDATES = [] # 정답 후보 단어 리스트

KOREAN_WORD_PATTERN = re.compile(r'^[가-힣]{2,}$')
# 형태소 분석기 없이 조사 결합형을 줄이기 위한 보수적 휴리스틱
MULTI_CHAR_JOSA_SUFFIXES = (
    '으로부터', '으로서', '으로써', '에게서', '이라도', '이라서', '인데도', '인데요',
    '처럼', '까지', '부터', '보다', '한테', '에게', '에서', '으로', '라고', '이며',
    '인데', '이나', '라도', '밖에', '조차', '마저'
)

# 단일 글자 조사 중 오검출 위험이 상대적으로 낮은 것만 사용
SINGLE_CHAR_JOSA_SUFFIXES = (
    '은', '는', '을', '를', '와', '과', '에', '로', '도', '만', '랑'
)

EXCLUDED_STANDALONE_FUNCTION_WORDS = set(MULTI_CHAR_JOSA_SUFFIXES) | {
    '또는', '및', '또한',
}

NON_DICTIONARY_SUFFIXES = (
    # 공손/문장 종결형
    '습니까', '습니다', '니다', '입니다', '하세요', '세요', '네요', '군요', '아요', '어요', '해요',
    # 활용/어미 결합형
    '인가요', '라고요', '인데요', '지만', '니까', '면서', '거나', '도록', '려고',
    # 서술 활용형 (기본형 명사/동사/형용사에서 제외)
    '한다', '준다', '했다', '된다', '됐다', '였다', '있는', '없는',
)

NON_DICTIONARY_DA_SUFFIXES = (
    '한다', '준다', '된다', '했다', '됐다', '였다', '갔다', '왔다', '봤다',
)

DA_EXCLUDE_JONGSUNG_INDEXES = {20}  # ㅆ
DA_ALLOWLIST = {'있다', '없다'}


def _get_jongsung_index(ch):
    code = ord(ch) - 0xAC00
    if code < 0 or code > 11171:
        return 0
    return code % 28


def _looks_like_conjugated_da_form(word):
    if not word.endswith('다') or len(word) < 2:
        return False

    if word in DA_ALLOWLIST:
        return False

    if word.endswith(NON_DICTIONARY_DA_SUFFIXES):
        return True

    prev = word[-2]
    jongsung_idx = _get_jongsung_index(prev)
    if jongsung_idx in DA_EXCLUDE_JONGSUNG_INDEXES:
        return True

    return False


def _looks_like_josa_form(word, vocabulary):
    for suffix in MULTI_CHAR_JOSA_SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        # 예: 때부터 -> 때 + 부터
        if len(stem) < 1:
            continue
        return True

    for suffix in SINGLE_CHAR_JOSA_SUFFIXES:
        if not word.endswith(suffix):
            continue
        stem = word[:-1]
        # 한 글자 어근으로 인한 오검출(예: 마을/가을) 최소화
        if len(stem) < 2:
            continue
        if stem in vocabulary:
            return True

    return False


def _is_clean_korean_word(word, vocabulary):
    if not KOREAN_WORD_PATTERN.fullmatch(word):
        return False
    if word in EXCLUDED_STANDALONE_FUNCTION_WORDS:
        return False
    if word.endswith(NON_DICTIONARY_SUFFIXES):
        return False
    if _looks_like_conjugated_da_form(word):
        return False
    if _looks_like_josa_form(word, vocabulary):
        return False
    return True


def _build_related_words(secret_word, top_words, limit=10):
    if not model:
        return []

    result = []
    for index, word in enumerate(top_words[:limit], start=1):
        try:
            similarity = float(model.similarity(secret_word, word))
        except Exception:
            continue
        result.append({
            'word': word,
            'rank': index,
            'score': round(similarity * 100, 2),
        })
    return result


def _wp_cache_key(endpoint, params):
    payload = json.dumps(
        {'endpoint': endpoint, 'params': params or {}},
        sort_keys=True,
        ensure_ascii=True,
        separators=(',', ':')
    )
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    return f'wp-json:{digest}'


def fetch_wp_json(endpoint, params=None, cache_timeout=None):
    params = params or {}
    timeout = WP_CACHE_TIMEOUT if cache_timeout is None else cache_timeout
    cache_key = None

    if timeout > 0:
        cache_key = _wp_cache_key(endpoint, params)
        cached = cache.get(cache_key)
        if cached:
            return cached['data'], cached['headers']

    response = requests.get(
        f"{WP_BASE_URL}/{endpoint}",
        params=params,
        timeout=WP_REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    headers = {
        'X-WP-TotalPages': response.headers.get('X-WP-TotalPages', '1'),
        'X-WP-Total': response.headers.get('X-WP-Total', '0'),
    }

    if cache_key:
        cache.set(cache_key, {'data': data, 'headers': headers}, timeout=timeout)

    return data, headers


def normalize_player_name(raw_name):
    name = (raw_name or '').strip()
    if not name:
        return 'Anonymous'
    return name[:10]


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_rate_limited(request, scope, limit, window_seconds):
    if limit <= 0:
        return False

    ip_address = get_client_ip(request)
    cache_key = f"rate_limit:{scope}:{ip_address}"
    now_ts = int(time.time())
    entry = cache.get(cache_key)

    if not entry or now_ts >= entry.get('reset_at', 0):
        cache.set(
            cache_key,
            {'count': 1, 'reset_at': now_ts + window_seconds},
            timeout=window_seconds
        )
        return False

    if entry['count'] >= limit:
        return True

    entry['count'] += 1
    ttl = max(1, entry['reset_at'] - now_ts)
    cache.set(cache_key, entry, timeout=ttl)
    return False


def resolve_rank_period(request):
    period = (request.GET.get('period') or 'daily').strip().lower()
    if period in ('daily', 'weekly'):
        return period
    return 'daily'


def rank_date_filters(period):
    today = timezone.localdate()
    if period == 'weekly':
        start_date = today - datetime.timedelta(days=6)
        return {
            'created_at__date__gte': start_date,
            'created_at__date__lte': today,
        }
    return {'created_at__date': today}

# ==========================================
# 1. AI 모델 로딩 (서버 시작 시 1회 실행)
# ==========================================
if MODEL_PATH and os.path.exists(MODEL_PATH):
    print("⏳ AI 모델 로딩 중... (잠시만 기다려주세요)")
    try:
        model = KeyedVectors.load_word2vec_format(MODEL_PATH, binary=False, limit=LIMIT)
        print("✅ 모델 로딩 완료!")
        
        # [오늘의 단어 후보군 만들기]
        # 상위 빈도 단어 중 "한글 단어 + 조사 결합형 제외" 조건으로 필터링
        raw_candidates = model.index_to_key[:5000]
        vocabulary = set(model.key_to_index)
        CANDIDATES = [w for w in raw_candidates if _is_clean_korean_word(w, vocabulary)]
        
    except Exception as e:
        print(f"❌ 모델 로딩 실패: {e}")
else:
    print("🚀 개발 모드 또는 모델 파일 없음: AI 기능을 제한적으로 실행합니다.")


# ==========================================
# 2. 오늘의 정답 뽑기 함수 (핵심!)
# ==========================================
def get_daily_word():
    """
    오늘 날짜를 기준으로 정답 단어를 결정합니다.
    같은 날짜에는 누가 접속해도 항상 같은 단어가 나옵니다.
    """
    # 모델이나 후보군이 없으면 테스트용 단어 리턴
    if not model or not CANDIDATES:
        return "세포"

    # 1. 오늘 날짜 가져오기 (예: '2026-02-12')
    today_str = datetime.date.today().isoformat()
    
    # 2. 날짜를 '랜덤 시드'로 설정
    # 이렇게 하면 오늘 하루 동안은 random이 항상 같은 순서로 작동합니다.
    rng = random.Random(today_str)
    
    # 3. 후보군에서 하나 뽑기
    secret_word = rng.choice(CANDIDATES)
    return secret_word

# 정답 단어와 유사한 상위 1000개 단어 캐싱
TODAY_CACHE = {
    'date': None,
    'secret': None,
    'top_words': []
}

def get_top_words(secret_word):
    """정답 단어의 유사도 상위 단어 목록(최대 3000개)을 구하거나 캐시에서 가져옴"""
    today_str = datetime.date.today().isoformat()
    
    # 이미 구해놓은 게 오늘 거라면 그거 사용
    if TODAY_CACHE['date'] == today_str and TODAY_CACHE['secret'] == secret_word:
        return TODAY_CACHE['top_words']
    
    # 아니면 새로 계산 (하루에 한 번만 실행됨)
    if model:
        try:
            vocabulary = set(model.key_to_index)
            raw_list = model.most_similar(secret_word, topn=6000)
            top_list = []
            for item in raw_list:
                word = item[0]
                if _is_clean_korean_word(word, vocabulary):
                    top_list.append(word)
                if len(top_list) >= 3000:
                    break
            
            # 캐시 업데이트
            TODAY_CACHE['date'] = today_str
            TODAY_CACHE['secret'] = secret_word
            TODAY_CACHE['top_words'] = top_list
            return top_list
        except:
            return []
    return []


# ==========================================
# 3. 뷰 함수 (꼬맨틀)
# ==========================================

def game_kkomantle(request):
    return render(request, 'core/games/kkomantle.html')

def api_kkomantle_guess(request):
    if request.method != 'POST':
        return JsonResponse({'result': 'error'}, status=400)

    post_limit = getattr(settings, 'KKOMANTLE_POST_RATE_LIMIT', 45)
    post_window = getattr(settings, 'KKOMANTLE_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_guess', post_limit, post_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
        guess = data.get('word', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        print(f"Error: {e}")
        return JsonResponse({'result': 'error', 'message': '서버 오류가 발생했습니다.'}, status=500)

    if not guess:
        return JsonResponse({'result': 'fail', 'message': '단어를 입력해주세요.'}, status=400)

    max_length = getattr(settings, 'KKOMANTLE_MAX_WORD_LENGTH', 30)
    if len(guess) > max_length:
        return JsonResponse({'result': 'fail', 'message': f'단어 길이는 최대 {max_length}자입니다.'}, status=400)

    # 개발용 치트 키는 입력 검증보다 우선 허용
    if guess == "!b1023582":
        secret_word = get_daily_word()
        return JsonResponse({'result': 'fail', 'message': f"🤫 쉿! 오늘의 정답은 '{secret_word}' 입니다."})

    valid_pattern = re.compile(getattr(settings, 'KKOMANTLE_WORD_REGEX', r'^[0-9A-Za-z가-힣_]+$'))
    if not valid_pattern.fullmatch(guess):
        return JsonResponse(
            {'result': 'fail', 'message': '한글/영문/숫자/밑줄(_)만 입력할 수 있어요.'},
            status=400
        )

    # 모델 로딩 체크
    if not model:
        # 개발 모드일 때 임시 응답
        return JsonResponse({'result': 'success', 'score': 0, 'rank': 'Unknown'})
    
    # 오늘의 정답 가져오기
    secret_word = get_daily_word()
    
    # 단어가 사전에 있는지 체크
    if guess not in model.key_to_index:
        return JsonResponse({'result': 'fail', 'message': f"'{guess}'은(는) 제가 모르는 단어예요."})
    
    try:
        # 순위표 준비
        top_list = get_top_words(secret_word)

        # ★ 에러 수정 부분: float32 -> float 형변환 ★
        similarity = model.similarity(secret_word, guess)
        score = float(similarity) * 100 
        score = round(score, 2)

        # 순위 계산
        rank = None
        if guess == secret_word:
            rank = 1
        elif guess in top_list:
            rank = top_list.index(guess) + 1
        else:
            rank = "3000+"

        # 결과 반환
        result_type = 'success'
        if guess == secret_word:
            result_type = 'correct'

        payload = {
            'result': result_type,
            'score': score,
            'rank': rank
        }
        if result_type == 'correct':
            payload['answer'] = secret_word
            payload['similar_words'] = _build_related_words(secret_word, top_list, limit=12)

        return JsonResponse(payload)
    except Exception as e:
        print(f"Error: {e}") # 터미널에 에러 로그 출력
        return JsonResponse({'result': 'error', 'message': '서버 오류가 발생했습니다.'}, status=500)


def api_kkomantle_hint(request):
    if request.method != 'POST':
        return JsonResponse({'result': 'error'}, status=400)

    post_limit = getattr(settings, 'KKOMANTLE_POST_RATE_LIMIT', 45)
    post_window = getattr(settings, 'KKOMANTLE_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_hint', post_limit, post_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    if not model:
        return JsonResponse({'result': 'error', 'message': 'AI 모델을 불러오지 못했습니다.'}, status=503)

    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
        step = int(data.get('step', 1))
    except Exception:
        return JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)

    hint_ranks = (1000, 500, 250)
    if step < 1 or step > len(hint_ranks):
        return JsonResponse({'result': 'fail', 'message': '더 이상 사용할 수 있는 힌트가 없어요.'}, status=400)

    secret_word = get_daily_word()
    top_list = get_top_words(secret_word)
    target_rank = hint_ranks[step - 1]
    idx = target_rank - 1

    if idx >= len(top_list):
        return JsonResponse(
            {'result': 'fail', 'message': f'현재 모델에서는 {target_rank}위 힌트를 제공할 수 없습니다.'},
            status=400
        )

    hint_word = top_list[idx]
    similarity = round(float(model.similarity(secret_word, hint_word)) * 100, 2)
    return JsonResponse({
        'result': 'success',
        'step': step,
        'rank': target_rank,
        'word': hint_word,
        'score': similarity,
    })


def api_kkomantle_surrender(request):
    if request.method != 'POST':
        return JsonResponse({'result': 'error'}, status=400)

    post_limit = getattr(settings, 'KKOMANTLE_POST_RATE_LIMIT', 45)
    post_window = getattr(settings, 'KKOMANTLE_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_surrender', post_limit, post_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    secret_word = get_daily_word()
    top_list = get_top_words(secret_word)
    return JsonResponse({
        'result': 'success',
        'answer': secret_word,
        'similar_words': _build_related_words(secret_word, top_list, limit=12),
    })


# ==========================================
# 4. 기타 뷰 함수 (블로그, 로비, 다른 게임)
# ==========================================

def home(request):
    """대시보드 홈: 최근 글 3개만 요약 노출"""
    try:
        posts, _ = fetch_wp_json('posts', {'_embed': True, 'per_page': 3}, cache_timeout=300)
    except Exception as e:
        print(f"Error fetching posts: {e}")
        posts = []
    return render(request, 'core/index.html', {'posts': posts})


def utility_home(request):
    return render(request, 'core/utility.html')

def blog_home(request):
    """블로그 메인: 카테고리 필터, 검색, 페이지네이션 지원"""
    page = request.GET.get('page', 1)
    category_id = request.GET.get('category')
    search_query = request.GET.get('search')

    # API 요청 파라미터 구성
    params = {
        'page': page,
        'per_page': 8,
        '_embed': True,
    }
    if category_id:
        params['categories'] = category_id
    if search_query:
        params['search'] = search_query

    try:
        # 1. 포스트 목록 가져오기
        posts, posts_headers = fetch_wp_json('posts', params, cache_timeout=300)
        
        # 2. 전체 페이지 수 파악
        total_pages = int(posts_headers.get('X-WP-TotalPages', 1))
        
        # 3. 카테고리 목록 가져오기
        categories, _ = fetch_wp_json('categories', cache_timeout=900)
    except Exception:
        posts, categories, total_pages = [], [], 1

    context = {
        'posts': posts,
        'categories': categories,
        'current_page': int(page),
        'total_pages': total_pages,
        'page_range': range(1, total_pages + 1),
        'current_category': category_id,
        'search_query': search_query,
    }
    return render(request, 'core/blog_home.html', context)

def post_detail(request, post_id):
    post = None
    category_name = "General"
    prev_post = None
    next_post = None

    try:
        post, _ = fetch_wp_json(f'posts/{post_id}', {'_embed': True}, cache_timeout=600)
        
        # 카테고리 이름 가공
        if '_embedded' in post and 'wp:term' in post['_embedded']:
            try:
                category_name = post['_embedded']['wp:term'][0][0]['name']
            except (IndexError, KeyError):
                pass

        category_id = post['categories'][0] if post.get('categories') else None

        if category_id:
            # 이전글/다음글 로직
            prev_posts, _ = fetch_wp_json('posts', {
                'categories': category_id, 'before': post['date'], 'per_page': 1, 'orderby': 'date', 'order': 'desc'
            }, cache_timeout=300)
            next_posts, _ = fetch_wp_json('posts', {
                'categories': category_id, 'after': post['date'], 'per_page': 1, 'orderby': 'date', 'order': 'asc'
            }, cache_timeout=300)
            if prev_posts:
                prev_post = prev_posts[0]
            if next_posts:
                next_post = next_posts[0]

    except Exception as e:
        print(f"Detail view error: {e}")

    status_code = 404 if post is None else 200

    return render(request, 'core/post_detail.html', {
        'post': post,
        'category_name': category_name,
        'prev_post': prev_post,
        'next_post': next_post,
    }, status=status_code)

def roulette(request):
    return render(request, 'core/roulette.html')

def ladder(request):
    return render(request, 'core/ladder.html')

def games_lobby(request):
    return render(request, 'core/games/lobby.html')


def policy_privacy(request):
    return render(request, 'core/policy/privacy.html')


def policy_terms(request):
    return render(request, 'core/policy/terms.html')


def policy_disclosure(request):
    return render(request, 'core/policy/disclosure.html')


def contact(request):
    return render(request, 'core/contact.html')

# --- 2048 게임 ---
def game_2048(request):
    return render(request, 'core/games/2048.html')

def api_2048_rank(request):
    period = resolve_rank_period(request)
    
    if request.method == 'POST':
        post_limit = getattr(settings, 'GAME_RANK_POST_RATE_LIMIT', 10)
        post_window = getattr(settings, 'GAME_RANK_POST_RATE_WINDOW', 60)
        if is_rate_limited(request, 'rank_2048', post_limit, post_window):
            return JsonResponse(
                {'status': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
                status=429
            )

        try:
            data = json.loads(request.body)
            name = normalize_player_name(data.get('player_name'))
            score = int(data.get('score', 0))
            
            max_score = getattr(settings, 'MAX_2048_SCORE', 2000000)
            if not (1 <= score <= max_score):
                return JsonResponse(
                    {'status': 'error', 'message': f'점수는 1~{max_score} 범위여야 합니다.'},
                    status=400
                )

            GameRecord.objects.create(
                game_type='2048',
                player_name=name,
                score=score
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    records = GameRecord.objects.filter(
        game_type='2048',
        **rank_date_filters(period),
    ).order_by('-score')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data, 'period': period})

# --- 반응속도 게임 ---
def game_reaction(request):
    return render(request, 'core/games/reaction.html')

def api_reaction_rank(request):
    period = resolve_rank_period(request)
    
    if request.method == 'POST':
        post_limit = getattr(settings, 'GAME_RANK_POST_RATE_LIMIT', 10)
        post_window = getattr(settings, 'GAME_RANK_POST_RATE_WINDOW', 60)
        if is_rate_limited(request, 'rank_reaction', post_limit, post_window):
            return JsonResponse(
                {'status': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
                status=429
            )

        try:
            data = json.loads(request.body)
            name = normalize_player_name(data.get('player_name'))
            score = int(data.get('score', 0))
            
            min_score = getattr(settings, 'MIN_REACTION_SCORE', 50)
            max_score = getattr(settings, 'MAX_REACTION_SCORE', 3000)
            if not (min_score <= score <= max_score):
                return JsonResponse(
                    {'status': 'error', 'message': f'기록은 {min_score}~{max_score}ms 범위여야 합니다.'},
                    status=400
                )

            GameRecord.objects.create(
                game_type='reaction',
                player_name=name,
                score=score
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # 반응속도는 낮은 점수가 1등 (오름차순)
    records = GameRecord.objects.filter(
        game_type='reaction',
        **rank_date_filters(period),
    ).order_by('score')[:10] 
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data, 'period': period})

# --- 워들(Wordle) ---
def game_wordle(request):
    return render(request, 'core/games/wordle.html')

def api_wordle_rank(request):
    period = resolve_rank_period(request)
    
    if request.method == 'POST':
        post_limit = getattr(settings, 'GAME_RANK_POST_RATE_LIMIT', 10)
        post_window = getattr(settings, 'GAME_RANK_POST_RATE_WINDOW', 60)
        if is_rate_limited(request, 'rank_wordle', post_limit, post_window):
            return JsonResponse(
                {'status': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
                status=429
            )

        try:
            data = json.loads(request.body)
            name = normalize_player_name(data.get('player_name'))
            score = int(data.get('score', 6))
            
            if not (1 <= score <= 6):
                return JsonResponse(
                    {'status': 'error', 'message': '워들은 1~6회 시도 기록만 등록할 수 있습니다.'},
                    status=400
                )

            GameRecord.objects.create(
                game_type='wordle',
                player_name=name,
                score=score
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # 시도 횟수가 적은 게 1등
    records = GameRecord.objects.filter(
        game_type='wordle',
        **rank_date_filters(period),
    ).order_by('score', '-created_at')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data, 'period': period})
