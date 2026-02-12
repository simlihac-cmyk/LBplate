from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, reverse # reverse 추가
from django.contrib.sitemaps.views import sitemap # 사이트맵 뷰
from django.contrib import sitemaps
from core.views import (
    home, blog_home, roulette, post_detail, ladder, 
    game_2048, api_2048_rank, games_lobby, 
    game_reaction, api_reaction_rank, game_wordle, api_wordle_rank
)

# 1. robots.txt 설정
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://monosaccharide180.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")

# 2. 사이트맵 설정 (검색 엔진이 읽어갈 페이지들)
class StaticViewSitemap(sitemaps.Sitemap):
    protocol = 'https'
    priority = 0.8  # 중요도 (0.0 ~ 1.0)
    changefreq = 'daily' # 갱신 빈도

    def items(self):
        # 검색 결과에 노출하고 싶은 페이지의 name을 넣으세요.
        # API 관련 경로(rank 등)는 제외하는 것이 좋습니다.
        return [
            'home', 'blog_home', 'games_lobby', 
            'game_2048', 'game_reaction', 'game_wordle', 
            'ladder', 'roulette'
        ]

    def location(self, item):
        return reverse(item)

sitemaps_dict = {
    'static': StaticViewSitemap,
}

# 3. URL 패턴
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('blog/', blog_home, name='blog_home'),
    path('roulette/', roulette, name='roulette'),
    path('post/<int:post_id>/', post_detail, name='post_detail'),
    path('ladder/', ladder, name='ladder'),
    path('games/', games_lobby, name='games_lobby'),
    path('games/2048/', game_2048, name='game_2048'),
    path('api/rank/2048/', api_2048_rank, name='api_2048_rank'),
    path('games/reaction/', game_reaction, name='game_reaction'),
    path('api/rank/reaction/', api_reaction_rank, name='api_reaction_rank'),
    path('games/wordle/', game_wordle, name='game_wordle'),
    path('api/rank/wordle/', api_wordle_rank, name='api_wordle_rank'),
    
    # robots.txt와 sitemap.xml 경로 추가
    path("robots.txt", robots_txt),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps_dict}, name='django.contrib.sitemaps.views.sitemap'),
]