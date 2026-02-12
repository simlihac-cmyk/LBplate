import requests
import os
from django.conf import settings
from gensim.models import KeyedVectors
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import GameRecord
import json

# 워드프레스 API 기본 주소 설정
WP_BASE_URL = "http://localhost:4080/wp-json/wp/v2"

print("⏳ AI 모델 로딩 중... (잠시만 기다려주세요)")
MODEL_PATH = os.path.join(settings.BASE_DIR, 'models', 'cc.ko.300.vec')

try:
    # 1. FastText(.vec) 로딩 방식
    model = KeyedVectors.load_word2vec_format(MODEL_PATH, binary=False, limit=300000)
    
    # 2. Kyubyong(.bin) 로딩 방식 (바이너리면 binary=True)
    # model = KeyedVectors.load_word2vec_format(MODEL_PATH, binary=True)
    
    print("✅ 모델 로딩 완료!")
except Exception as e:
    print(f"❌ 모델 로딩 실패: {e}")
    model = None

@csrf_exempt
def api_kkomantle_guess(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            guess = data.get('word', '').strip()
            secret_word = "실험" # 오늘의 정답 (나중엔 DB에서 가져오기)

            if not model:
                return JsonResponse({'status': 'error', 'message': 'AI 모델이 로드되지 않았습니다.'}, status=500)

            # 1. 단어가 모델에 있는지 확인
            if guess not in model.key_to_index:
                return JsonResponse({'result': 'fail', 'message': '사전에 없는 단어입니다.'})

            # 2. 유사도 계산 (Cosine Similarity)
            # 결과는 0.0 ~ 1.0 사이 (1.0이 똑같음) -> 보기 좋게 100점 만점으로 변환
            similarity = model.similarity(secret_word, guess)
            score = round(similarity * 100, 2)
            
            # 3. 순위 구하기 (Rank)
            # 사실 매번 랭크를 계산하면 느립니다. 보통 정답 단어의 유사도 리스트를 미리 뽑아둡니다.
            # 여기서는 약식으로 '점수'만 줍니다. (랭크 구현은 심화 과정)
            
            result_type = 'success'
            if guess == secret_word:
                result_type = 'correct'

            return JsonResponse({
                'result': result_type,
                'score': score,
                'rank': None # 랭크는 계산 비용이 커서 일단 뺌
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

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
        'per_page': 8, # 한 페이지에 표시할 글 수
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
        
        # 2. 전체 페이지 수 파악 (헤더 정보 활용)
        total_pages = int(posts_res.headers.get('X-WP-TotalPages', 1))
        
        # 3. 카테고리 목록 가져오기 (필터 탭용)
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
        
        # --- 추가된 로직: 템플릿에서 쓸 수 있게 미리 가공 ---
        category_name = "General"  # 기본값
        if '_embedded' in post and 'wp:term' in post['_embedded']:
            try:
                # 첫 번째 카테고리의 이름을 가져옵니다.
                category_name = post['_embedded']['wp:term'][0][0]['name']
            except (IndexError, KeyError):
                pass
        # ----------------------------------------------

        category_id = post['categories'][0] if post.get('categories') else None
        prev_post = None
        next_post = None

        if category_id:
            # 이전글/다음글 로직 (기존과 동일)
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
        'category_name': category_name, # 가공된 카테고리 이름 전달
        'prev_post': prev_post,
        'next_post': next_post,
    })

def roulette(request):
    return render(request, 'core/roulette.html')

def ladder(request):
    return render(request, 'core/ladder.html')

def game_2048(request):
    return render(request, 'core/games/2048.html')

@csrf_exempt
def api_2048_rank(request):
    """
    GET: 오늘의 랭킹 TOP 10 조회
    POST: 게임 점수 저장
    """
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10] # 이름 길이 제한
            score = int(data.get('score', 0))
            
            # 간단한 어뷰징 방지 (점수가 너무 낮거나 비정상이면 저장 안 함)
            if score > 0:
                GameRecord.objects.create(
                    game_type='2048',
                    player_name=name,
                    score=score
                )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # GET 요청: 오늘의 랭킹 조회
    records = GameRecord.objects.filter(
        game_type='2048', 
        created_at__date=today
    ).order_by('-score')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})

def games_lobby(request):
    """게임 선택 로비 화면"""
    return render(request, 'core/games/lobby.html')

def game_reaction(request):
    return render(request, 'core/games/reaction.html')

@csrf_exempt
def api_reaction_rank(request):
    """
    GET: 오늘의 반응속도 랭킹 (낮은 시간 순서 = 오름차순)
    POST: 기록 저장
    """
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10]
            score = int(data.get('score', 0)) # ms 단위
            
            # 50ms 미만은 인간의 한계를 넘은 것이므로 저장 안 함 (어뷰징 방지)
            if score > 50:
                GameRecord.objects.create(
                    game_type='reaction',
                    player_name=name,
                    score=score
                )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # 반응속도는 '낮을수록' 좋은 기록이므로 score(오름차순) 정렬
    records = GameRecord.objects.filter(
        game_type='reaction', 
        created_at__date=today
    ).order_by('score')[:10] 
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})

def game_wordle(request):
    return render(request, 'core/games/wordle.html')

@csrf_exempt
def api_wordle_rank(request):
    """
    Wordle 랭킹: 시도 횟수(1~6)가 적을수록 1등
    """
    today = timezone.now().date()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('player_name', 'Anonymous')[:10]
            score = int(data.get('score', 6)) # 시도 횟수
            
            # 1~6회 사이의 성공만 저장
            if 1 <= score <= 6:
                GameRecord.objects.create(
                    game_type='wordle',
                    player_name=name,
                    score=score
                )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # 랭킹 조회: 점수(시도횟수) 오름차순 정렬 (1이 최고)
    records = GameRecord.objects.filter(
        game_type='wordle', 
        created_at__date=today
    ).order_by('score', '-created_at')[:10]
    
    data = [{'name': r.player_name, 'score': r.score} for r in records]
    return JsonResponse({'ranking': data})