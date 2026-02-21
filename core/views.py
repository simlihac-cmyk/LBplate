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
from django.db import IntegrityError
from .models import GameRecord, KkomantleDailySnapshot
from .kkomantle_filters import is_clean_korean_word

# 워드프레스 API 기본 주소 설정
WP_BASE_URL = getattr(settings, 'WP_BASE_URL', 'http://127.0.0.1:4080/wp-json/wp/v2')
WP_REQUEST_TIMEOUT = getattr(settings, 'WP_REQUEST_TIMEOUT', 5)
WP_CACHE_TIMEOUT = getattr(settings, 'WP_CACHE_TIMEOUT', 300)

# settings.py에서 설정 가져오기
MODEL_PATH = getattr(settings, 'WORD2VEC_MODEL_PATH', None)
LIMIT = getattr(settings, 'WORD2VEC_LIMIT', 300000)
WHITELIST_PATH = getattr(settings, 'KKOMANTLE_WHITELIST_PATH', None)
MODEL_CANDIDATE_TOPN = getattr(settings, 'KKOMANTLE_MODEL_CANDIDATE_TOPN', 5000)
MOST_SIMILAR_TOPN = getattr(settings, 'KKOMANTLE_MOST_SIMILAR_TOPN', 6000)
TOP_WORD_LIMIT = getattr(settings, 'KKOMANTLE_TOP_WORD_LIMIT', 3000)
MAX_WORD_LENGTH = getattr(settings, 'KKOMANTLE_MAX_WORD_LENGTH', 30)
VALID_WORD_PATTERN = re.compile(getattr(settings, 'KKOMANTLE_WORD_REGEX', r'^[0-9A-Za-z가-힣_]+$'))
KKOMANTLE_CHALLENGE_GAME_TYPE = 'kkomantle_challenge'
KKOMANTLE_CHALLENGE_SESSION_KEY = 'kkomantle_challenge_state'
KKOMANTLE_CHALLENGE_MAX_ATTEMPTS = max(1, int(getattr(settings, 'KKOMANTLE_CHALLENGE_MAX_ATTEMPTS', 10)))
KKOMANTLE_CHALLENGE_RANK_LIMIT = max(1, int(getattr(settings, 'KKOMANTLE_CHALLENGE_RANK_LIMIT', 10)))
_raw_hint_ranks = getattr(settings, 'KKOMANTLE_CHALLENGE_HINT_RANKS', '25,30,35')
if isinstance(_raw_hint_ranks, str):
    _parsed_hint_ranks = []
    for token in _raw_hint_ranks.split(','):
        token = token.strip()
        if token.isdigit():
            _parsed_hint_ranks.append(max(1, int(token)))
    KKOMANTLE_CHALLENGE_HINT_RANKS = tuple(_parsed_hint_ranks[:3]) if _parsed_hint_ranks else (25, 30, 35)
else:
    try:
        KKOMANTLE_CHALLENGE_HINT_RANKS = tuple(max(1, int(x)) for x in _raw_hint_ranks)[:3]
    except Exception:
        KKOMANTLE_CHALLENGE_HINT_RANKS = (25, 30, 35)

model = None
CANDIDATES = [] # 정답 후보 단어 리스트
WORD_WHITELIST = set()
MODEL_VOCABULARY = set()


def _load_kkomantle_whitelist(path, vocabulary):
    if not path:
        return set()
    if not os.path.exists(path):
        print(f"⚠️ 꼬맨틀 화이트리스트 파일이 없습니다: {path}")
        return set()

    raw_words = []
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            for line in fp:
                word = line.strip()
                if not word or word.startswith('#'):
                    continue
                raw_words.append(word)
    except Exception as e:
        print(f"⚠️ 꼬맨틀 화이트리스트 로딩 실패: {e}")
        return set()

    filtered = []
    seen = set()
    for word in raw_words:
        if word in seen:
            continue
        seen.add(word)
        if word not in vocabulary:
            continue
        if not is_clean_korean_word(word, vocabulary):
            continue
        filtered.append(word)

    print(f"✅ 꼬맨틀 화이트리스트 로딩 완료: 원본 {len(raw_words)}개 / 사용 {len(filtered)}개")
    return set(filtered)


def _is_allowed_kkomantle_word(word, vocabulary):
    if not is_clean_korean_word(word, vocabulary):
        return False
    if WORD_WHITELIST and word not in WORD_WHITELIST:
        return False
    return True


def _is_rankable_kkomantle_word(word, vocabulary):
    return is_clean_korean_word(word, vocabulary)


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


def _get_kkomantle_history_start_date():
    raw = getattr(settings, 'KKOMANTLE_HISTORY_START_DATE', '2026-02-18')
    try:
        return datetime.date.fromisoformat(str(raw))
    except Exception:
        return datetime.date(2026, 2, 18)


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


def _parse_json_body(request):
    try:
        data = json.loads(request.body)
        if isinstance(data, dict):
            return data, None
        return None, JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except json.JSONDecodeError:
        return None, JsonResponse({'result': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception:
        return None, JsonResponse({'result': 'error', 'message': '서버 오류가 발생했습니다.'}, status=500)


def _validate_kkomantle_guess_word(guess):
    if not guess:
        return JsonResponse({'result': 'fail', 'message': '단어를 입력해주세요.'}, status=400)

    if len(guess) > MAX_WORD_LENGTH:
        return JsonResponse(
            {'result': 'fail', 'message': f'단어 길이는 최대 {MAX_WORD_LENGTH}자입니다.'},
            status=400
        )

    if not VALID_WORD_PATTERN.fullmatch(guess):
        return JsonResponse(
            {'result': 'fail', 'message': '한글/영문/숫자/밑줄(_)만 입력할 수 있어요.'},
            status=400
        )

    return None


def _compute_kkomantle_rank(guess, secret_word, top_list):
    if guess == secret_word:
        return 1
    if guess in top_list:
        return top_list.index(guess) + 1
    return f"{TOP_WORD_LIMIT}+"


def _build_guess_result(secret_word, guess, top_list):
    similarity = model.similarity(secret_word, guess)
    score = round(float(similarity) * 100, 2)
    rank = _compute_kkomantle_rank(guess, secret_word, top_list)
    return score, rank


def get_top_words_for_secret(secret_word):
    """특정 정답 단어의 유사도 상위 단어를 캐시 기반으로 반환."""
    if not model:
        return []

    cache_key = f'kkomantle:top:{secret_word}'
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        raw_list = model.most_similar(secret_word, topn=MOST_SIMILAR_TOPN)
    except Exception:
        return []

    top_list = []
    for word, _score in raw_list:
        if _is_rankable_kkomantle_word(word, MODEL_VOCABULARY):
            top_list.append(word)
        if len(top_list) >= TOP_WORD_LIMIT:
            break

    cache.set(cache_key, top_list, timeout=86400)
    return top_list


def _pick_kkomantle_challenge_secret(exclude_words=None):
    if not model or not CANDIDATES:
        return '세포'

    exclude = set(exclude_words or [])
    available = [word for word in CANDIDATES if word not in exclude]
    pool = available if available else CANDIDATES
    return random.SystemRandom().choice(pool)


def _build_challenge_hint(secret_word):
    top_list = get_top_words_for_secret(secret_word)
    if not top_list:
        return None

    hints = []
    for rank in KKOMANTLE_CHALLENGE_HINT_RANKS:
        target_rank = min(rank, len(top_list))
        hint_word = top_list[target_rank - 1]
        hint_score = round(float(model.similarity(secret_word, hint_word)) * 100, 2)
        hints.append({
            'rank': target_rank,
            'word': hint_word,
            'score': hint_score,
        })
    return hints


def _start_new_challenge_round(state, round_number, solved_rounds):
    used_words = set(state.get('used_words') or [])
    secret_word = _pick_kkomantle_challenge_secret(used_words)
    used_words.add(secret_word)

    hint = _build_challenge_hint(secret_word)
    state.update({
        'active': True,
        'round': round_number,
        'solved_rounds': solved_rounds,
        'secret_word': secret_word,
        'attempt_used': 0,
        'max_attempts': KKOMANTLE_CHALLENGE_MAX_ATTEMPTS,
        'round_guesses': [],
        'used_words': list(used_words),
    })
    if hint:
        state['hint'] = hint
    else:
        state['hint'] = []
    return state


def _get_challenge_state(request):
    state = request.session.get(KKOMANTLE_CHALLENGE_SESSION_KEY)
    if isinstance(state, dict):
        return state
    return None


def _set_challenge_state(request, state):
    request.session[KKOMANTLE_CHALLENGE_SESSION_KEY] = state
    request.session.modified = True


def _get_challenge_ranking(limit=KKOMANTLE_CHALLENGE_RANK_LIMIT):
    records = GameRecord.objects.filter(
        game_type=KKOMANTLE_CHALLENGE_GAME_TYPE,
    ).order_by('-score', '-created_at')[:limit]
    return [{'name': row.player_name, 'score': row.score} for row in records]

# ==========================================
# 1. AI 모델 로딩 (서버 시작 시 1회 실행)
# ==========================================
if MODEL_PATH and os.path.exists(MODEL_PATH):
    print("⏳ AI 모델 로딩 중... (잠시만 기다려주세요)")
    try:
        model = KeyedVectors.load_word2vec_format(MODEL_PATH, binary=False, limit=LIMIT)
        print("✅ 모델 로딩 완료!")
        
        MODEL_VOCABULARY = set(model.key_to_index)
        WORD_WHITELIST = _load_kkomantle_whitelist(WHITELIST_PATH, MODEL_VOCABULARY)

        # [오늘의 단어 후보군 만들기]
        # 화이트리스트가 있으면 우선 사용하고, 없으면 모델 상위 빈도 후보에서 필터링
        if WORD_WHITELIST:
            CANDIDATES = []
            for word in model.index_to_key:
                if word in WORD_WHITELIST:
                    CANDIDATES.append(word)
                if len(CANDIDATES) >= MODEL_CANDIDATE_TOPN:
                    break
            print(f"✅ 화이트리스트 기반 후보군 생성: {len(CANDIDATES)}개")
        else:
            raw_candidates = model.index_to_key[:MODEL_CANDIDATE_TOPN]
            CANDIDATES = [w for w in raw_candidates if _is_allowed_kkomantle_word(w, MODEL_VOCABULARY)]
            print(f"✅ 모델 기반 후보군 생성: {len(CANDIDATES)}개")
        
    except Exception as e:
        print(f"❌ 모델 로딩 실패: {e}")
else:
    print("🚀 개발 모드 또는 모델 파일 없음: AI 기능을 제한적으로 실행합니다.")


# ==========================================
# 2. 오늘의 정답 뽑기 함수 (핵심!)
# ==========================================
def get_daily_word_for_date(target_date):
    """
    지정 날짜를 기준으로 정답 단어를 결정합니다.
    같은 날짜에는 누가 접속해도 항상 같은 단어가 나옵니다.
    """
    # 모델이나 후보군이 없으면 테스트용 단어 리턴
    if not model or not CANDIDATES:
        return "세포"

    day_str = target_date.isoformat()

    # 날짜를 '랜덤 시드'로 설정
    # 이렇게 하면 오늘 하루 동안은 random이 항상 같은 순서로 작동합니다.
    rng = random.Random(day_str)

    # 후보군에서 하나 뽑기
    secret_word = rng.choice(CANDIDATES)
    return secret_word


def get_daily_word():
    return get_daily_word_for_date(timezone.localdate())

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
    
    top_list = get_top_words_for_secret(secret_word)
    TODAY_CACHE['date'] = today_str
    TODAY_CACHE['secret'] = secret_word
    TODAY_CACHE['top_words'] = top_list
    return top_list


def get_or_create_kkomantle_snapshot(target_date):
    snapshot = KkomantleDailySnapshot.objects.filter(date=target_date).first()
    if snapshot:
        return snapshot

    answer = get_daily_word_for_date(target_date)
    top_words = get_top_words(answer)
    related_words = _build_related_words(answer, top_words, limit=20)

    try:
        snapshot = KkomantleDailySnapshot.objects.create(
            date=target_date,
            answer=answer,
            top_words=related_words,
        )
    except IntegrityError:
        snapshot = KkomantleDailySnapshot.objects.get(date=target_date)

    return snapshot


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

    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response
    guess = (data.get('word') or '').strip()

    # 개발용 치트 키는 입력 검증보다 우선 허용
    if guess == "!b1023582":
        secret_word = get_daily_word()
        return JsonResponse({'result': 'fail', 'message': f"🤫 쉿! 오늘의 정답은 '{secret_word}' 입니다."})

    validation_error = _validate_kkomantle_guess_word(guess)
    if validation_error:
        return validation_error

    # 모델 로딩 체크
    if not model:
        # 개발 모드일 때 임시 응답
        return JsonResponse({'result': 'success', 'score': 0, 'rank': 'Unknown'})
    
    # 오늘의 정답 가져오기
    secret_word = get_daily_word()
    
    # 단어가 사전에 있는지 체크
    if guess not in MODEL_VOCABULARY:
        return JsonResponse({'result': 'fail', 'message': f"'{guess}'은(는) 제가 모르는 단어예요."})
    
    try:
        top_list = get_top_words(secret_word)
        score, rank = _build_guess_result(secret_word, guess, top_list)

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

    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    try:
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


def api_kkomantle_history(request):
    if request.method != 'GET':
        return JsonResponse({'result': 'error'}, status=400)

    rate_limit = getattr(settings, 'KKOMANTLE_HISTORY_RATE_LIMIT', 20)
    rate_window = getattr(settings, 'KKOMANTLE_HISTORY_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_history', rate_limit, rate_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    max_days = max(1, getattr(settings, 'KKOMANTLE_HISTORY_MAX_DAYS', 30))
    try:
        days = int((request.GET.get('days') or '7').strip())
    except Exception:
        days = 7
    days = max(1, min(days, max_days))

    start_date = _get_kkomantle_history_start_date()
    today = timezone.localdate()
    cursor = today - datetime.timedelta(days=1)

    items = []
    while len(items) < days and cursor >= start_date:
        snapshot = get_or_create_kkomantle_snapshot(cursor)
        words = snapshot.top_words if isinstance(snapshot.top_words, list) else []
        items.append({
            'date': snapshot.date.isoformat(),
            'answer': snapshot.answer,
            'top_words': words[:20],
        })
        cursor -= datetime.timedelta(days=1)

    return JsonResponse({
        'result': 'success',
        'start_date': start_date.isoformat(),
        'items': items,
    })


def game_kkomantle_challenge(request):
    return render(request, 'core/games/kkomantle_challenge.html')


def api_kkomantle_challenge_start(request):
    if request.method != 'POST':
        return JsonResponse({'result': 'error'}, status=400)

    post_limit = getattr(settings, 'KKOMANTLE_CHALLENGE_POST_RATE_LIMIT', 45)
    post_window = getattr(settings, 'KKOMANTLE_CHALLENGE_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_challenge_start', post_limit, post_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    if not model:
        return JsonResponse({'result': 'error', 'message': 'AI 모델을 불러오지 못했습니다.'}, status=503)

    state = {}
    _start_new_challenge_round(state, round_number=1, solved_rounds=0)
    state['eligible_score'] = None
    state['rank_submitted'] = False
    _set_challenge_state(request, state)

    return JsonResponse({
        'result': 'success',
        'round': state['round'],
        'solved_rounds': state['solved_rounds'],
        'attempt_used': state['attempt_used'],
        'attempt_left': state['max_attempts'] - state['attempt_used'],
        'hint': state['hint'],
        'ranking': _get_challenge_ranking(),
    })


def api_kkomantle_challenge_guess(request):
    if request.method != 'POST':
        return JsonResponse({'result': 'error'}, status=400)

    post_limit = getattr(settings, 'KKOMANTLE_CHALLENGE_POST_RATE_LIMIT', 45)
    post_window = getattr(settings, 'KKOMANTLE_CHALLENGE_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'kkomantle_challenge_guess', post_limit, post_window):
        return JsonResponse(
            {'result': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    if not model:
        return JsonResponse({'result': 'error', 'message': 'AI 모델을 불러오지 못했습니다.'}, status=503)

    state = _get_challenge_state(request)
    if not state or not state.get('active'):
        return JsonResponse(
            {'result': 'fail', 'message': '먼저 챌린지 시작 버튼을 눌러주세요.'},
            status=400
        )

    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response
    guess = (data.get('word') or '').strip()

    validation_error = _validate_kkomantle_guess_word(guess)
    if validation_error:
        return validation_error

    if guess not in MODEL_VOCABULARY:
        return JsonResponse({'result': 'fail', 'message': f"'{guess}'은(는) 제가 모르는 단어예요."})

    round_guesses = set(state.get('round_guesses') or [])
    if guess in round_guesses:
        return JsonResponse({'result': 'fail', 'message': '이번 라운드에서 이미 입력한 단어입니다.'})

    secret_word = state.get('secret_word') or _pick_kkomantle_challenge_secret()
    top_list = get_top_words_for_secret(secret_word)
    score, rank = _build_guess_result(secret_word, guess, top_list)

    attempt_used = int(state.get('attempt_used') or 0) + 1
    max_attempts = int(state.get('max_attempts') or KKOMANTLE_CHALLENGE_MAX_ATTEMPTS)
    round_guesses.add(guess)
    state['attempt_used'] = attempt_used
    state['round_guesses'] = list(round_guesses)

    if guess == secret_word:
        solved_rounds = int(state.get('solved_rounds') or 0) + 1
        round_number = int(state.get('round') or 1)
        _start_new_challenge_round(state, round_number=round_number + 1, solved_rounds=solved_rounds)
        _set_challenge_state(request, state)
        return JsonResponse({
            'result': 'round_clear',
            'score': score,
            'rank': rank,
            'answer': secret_word,
            'solved_rounds': state['solved_rounds'],
            'next_round': state['round'],
            'attempt_used': state['attempt_used'],
            'attempt_left': state['max_attempts'] - state['attempt_used'],
            'hint': state['hint'],
        })

    attempt_left = max(0, max_attempts - attempt_used)
    if attempt_left == 0:
        solved_rounds = int(state.get('solved_rounds') or 0)
        state['active'] = False
        state['eligible_score'] = solved_rounds
        state['rank_submitted'] = False
        _set_challenge_state(request, state)
        return JsonResponse({
            'result': 'game_over',
            'score': score,
            'rank': rank,
            'answer': secret_word,
            'solved_rounds': solved_rounds,
            'eligible_score': solved_rounds,
            'similar_words': _build_related_words(secret_word, top_list, limit=12),
        })

    _set_challenge_state(request, state)
    return JsonResponse({
        'result': 'success',
        'score': score,
        'rank': rank,
        'round': state.get('round', 1),
        'solved_rounds': state.get('solved_rounds', 0),
        'attempt_used': attempt_used,
        'attempt_left': attempt_left,
    })


def api_kkomantle_challenge_rank(request):
    if request.method == 'GET':
        state = _get_challenge_state(request) or {}
        can_submit = state.get('eligible_score') is not None and not state.get('rank_submitted')
        return JsonResponse({
            'status': 'success',
            'ranking': _get_challenge_ranking(),
            'can_submit': can_submit,
            'eligible_score': state.get('eligible_score'),
        })

    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=400)

    post_limit = getattr(settings, 'GAME_RANK_POST_RATE_LIMIT', 10)
    post_window = getattr(settings, 'GAME_RANK_POST_RATE_WINDOW', 60)
    if is_rate_limited(request, 'rank_kkomantle_challenge', post_limit, post_window):
        return JsonResponse(
            {'status': 'error', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'},
            status=429
        )

    state = _get_challenge_state(request) or {}
    eligible_score = state.get('eligible_score')
    if eligible_score is None or state.get('rank_submitted'):
        return JsonResponse(
            {'status': 'error', 'message': '등록 가능한 챌린지 기록이 없습니다.'},
            status=400
        )

    data, error_response = _parse_json_body(request)
    if error_response:
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)

    try:
        submitted_score = int(data.get('score', eligible_score))
    except Exception:
        return JsonResponse({'status': 'error', 'message': '점수 형식이 올바르지 않습니다.'}, status=400)

    eligible_score = int(eligible_score)
    if submitted_score != eligible_score:
        return JsonResponse({'status': 'error', 'message': '기록 검증에 실패했습니다.'}, status=400)

    player_name = normalize_player_name(data.get('player_name'))
    GameRecord.objects.create(
        game_type=KKOMANTLE_CHALLENGE_GAME_TYPE,
        player_name=player_name,
        score=eligible_score,
    )

    state['eligible_score'] = None
    state['rank_submitted'] = True
    _set_challenge_state(request, state)
    return JsonResponse({'status': 'success', 'ranking': _get_challenge_ranking()})


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
