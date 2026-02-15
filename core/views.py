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

# ==========================================
# 1. AI 모델 로딩 (서버 시작 시 1회 실행)
# ==========================================
if MODEL_PATH and os.path.exists(MODEL_PATH):
    print("⏳ AI 모델 로딩 중... (잠시만 기다려주세요)")
    try:
        model = KeyedVectors.load_word2vec_format(MODEL_PATH, binary=False, limit=LIMIT)
        print("✅ 모델 로딩 완료!")
        
        # [오늘의 단어 후보군 만들기]
        # 상위 3000개 중 2글자 이상, 한글로만 된 단어 필터링
        raw_candidates = model.index_to_key[:3000]
        CANDIDATES = [w for w in raw_candidates if len(w) >= 2 and w.replace('_', '').isalpha()]
        
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
    'top1000': []
}

def get_top1000(secret_word):
    """정답 단어의 유사도 순위표를 구하거나 캐시에서 가져옴"""
    today_str = datetime.date.today().isoformat()
    
    # 이미 구해놓은 게 오늘 거라면 그거 사용
    if TODAY_CACHE['date'] == today_str and TODAY_CACHE['secret'] == secret_word:
        return TODAY_CACHE['top1000']
    
    # 아니면 새로 계산 (하루에 한 번만 실행됨)
    if model:
        try:
            # most_similar는 (단어, 점수) 튜플 리스트를 줌
            top_list = [w[0] for w in model.most_similar(secret_word, topn=3000)]
            
            # 캐시 업데이트
            TODAY_CACHE['date'] = today_str
            TODAY_CACHE['secret'] = secret_word
            TODAY_CACHE['top1000'] = top_list
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
        top_list = get_top1000(secret_word)

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

        return JsonResponse({
            'result': result_type,
            'score': score,
            'rank': rank
        })
    except Exception as e:
        print(f"Error: {e}") # 터미널에 에러 로그 출력
        return JsonResponse({'result': 'error', 'message': '서버 오류가 발생했습니다.'}, status=500)


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
    today = timezone.now().date()
    
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
        created_at__date=today
    ).order_by('-score')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})

# --- 반응속도 게임 ---
def game_reaction(request):
    return render(request, 'core/games/reaction.html')

def api_reaction_rank(request):
    today = timezone.now().date()
    
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
        created_at__date=today
    ).order_by('score')[:10] 
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})

# --- 워들(Wordle) ---
def game_wordle(request):
    return render(request, 'core/games/wordle.html')

def api_wordle_rank(request):
    today = timezone.now().date()
    
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
        created_at__date=today
    ).order_by('score', '-created_at')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})
