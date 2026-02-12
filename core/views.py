import requests
import os
import json
import random  # [추가됨] 데일리 단어 뽑기에 필수
import datetime # [추가됨] 날짜 처리에 필수
from django.conf import settings
from gensim.models import KeyedVectors
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import GameRecord

# 워드프레스 API 기본 주소 설정
WP_BASE_URL = "http://localhost:4080/wp-json/wp/v2"

# settings.py에서 설정 가져오기
MODEL_PATH = getattr(settings, 'WORD2VEC_MODEL_PATH', None)
LIMIT = getattr(settings, 'WORD2VEC_LIMIT', 300000)

model = None
CANDIDATES = [] # 정답 후보 단어 리스트

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

@csrf_exempt
def api_kkomantle_guess(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            guess = data.get('word', '').strip()

            # 모델 로딩 체크
            if not model:
                # 개발 모드일 때 임시 응답
                return JsonResponse({'result': 'success', 'score': 0, 'rank': 'Unknown'})
            
                # 오늘의 정답 가져오기
            secret_word = get_daily_word()
            
            if guess == "!b1023582":
                return JsonResponse({'result': 'fail', 'message': f"🤫 쉿! 오늘의 정답은 '{secret_word}' 입니다."})
            
            # 단어가 사전에 있는지 체크
            if guess not in model.key_to_index:
                return JsonResponse({'result': 'fail', 'message': f"'{guess}'은(는) 제가 모르는 단어예요."})
            
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
            return JsonResponse({'result': 'error', 'message': '서버 오류가 발생했습니다.'})

    return JsonResponse({'result': 'error'}, status=400)


# ==========================================
# 4. 기타 뷰 함수 (블로그, 로비, 다른 게임)
# ==========================================

def home(request):
    """대시보드 홈: 최근 글 3개만 요약 노출"""
    api_url = f"{WP_BASE_URL}/posts?_embed&per_page=3"
    try:
        response = requests.get(api_url)
        posts = response.json()
    except Exception as e:
        print(f"Error fetching posts: {e}")
        posts = []
    return render(request, 'core/index.html', {'posts': posts})

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
        posts_res = requests.get(f"{WP_BASE_URL}/posts", params=params)
        posts = posts_res.json()
        
        # 2. 전체 페이지 수 파악
        total_pages = int(posts_res.headers.get('X-WP-TotalPages', 1))
        
        # 3. 카테고리 목록 가져오기
        categories_res = requests.get(f"{WP_BASE_URL}/categories")
        categories = categories_res.json()
    except:
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
    try:
        res = requests.get(f"{WP_BASE_URL}/posts/{post_id}?_embed")
        post = res.json()
        
        # 카테고리 이름 가공
        category_name = "General"
        if '_embedded' in post and 'wp:term' in post['_embedded']:
            try:
                category_name = post['_embedded']['wp:term'][0][0]['name']
            except (IndexError, KeyError):
                pass

        category_id = post['categories'][0] if post.get('categories') else None
        prev_post = None
        next_post = None

        if category_id:
            # 이전글/다음글 로직
            prev_res = requests.get(f"{WP_BASE_URL}/posts", params={
                'categories': category_id, 'before': post['date'], 'per_page': 1, 'orderby': 'date', 'order': 'desc'
            })
            next_res = requests.get(f"{WP_BASE_URL}/posts", params={
                'categories': category_id, 'after': post['date'], 'per_page': 1, 'orderby': 'date', 'order': 'asc'
            })
            if prev_res.status_code == 200 and prev_res.json(): prev_post = prev_res.json()[0]
            if next_res.status_code == 200 and next_res.json(): next_post = next_res.json()[0]

    except Exception as e:
        print(f"Detail view error: {e}")
        post = None

    return render(request, 'core/post_detail.html', {
        'post': post,
        'category_name': category_name,
        'prev_post': prev_post,
        'next_post': next_post,
    })

def roulette(request):
    return render(request, 'core/roulette.html')

def ladder(request):
    return render(request, 'core/ladder.html')

def games_lobby(request):
    return render(request, 'core/games/lobby.html')

# --- 2048 게임 ---
def game_2048(request):
    return render(request, 'core/games/2048.html')

@csrf_exempt
def api_2048_rank(request):
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10]
            score = int(data.get('score', 0))
            
            if score > 0:
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

@csrf_exempt
def api_reaction_rank(request):
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10]
            score = int(data.get('score', 0))
            
            if score > 50:
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

@csrf_exempt
def api_wordle_rank(request):
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10]
            score = int(data.get('score', 6))
            
            if 1 <= score <= 6:
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