from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.contrib.sitemaps.views import sitemap
from core.feeds import WordPressPostFeed
from core.sitemaps import StaticViewSitemap, WordPressPostSitemap
from core.views import (
    home, blog_home, roulette, post_detail, ladder, utility_home,
    game_2048, api_2048_rank, games_lobby,
    game_reaction, api_reaction_rank, game_wordle, api_wordle_rank, game_kkomantle,
    game_kkomantle_challenge, api_kkomantle_guess, api_kkomantle_hint, api_kkomantle_surrender,
    api_kkomantle_history, api_kkomantle_challenge_start, api_kkomantle_challenge_guess,
    api_kkomantle_challenge_rank,
    policy_privacy, policy_terms, policy_disclosure, contact,
)

# 1. robots.txt 설정
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://monosaccharide180.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")

sitemaps_dict = {
    'static': StaticViewSitemap,
    'posts': WordPressPostSitemap,
}

# 3. URL 패턴
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('blog/', blog_home, name='blog_home'),
    path('utility/', utility_home, name='utility_home'),
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
    path('games/kkomantle/', game_kkomantle, name='game_kkomantle'),
    path('games/kkomantle/challenge/', game_kkomantle_challenge, name='game_kkomantle_challenge'),
    path('api/guess/kkomantle/', api_kkomantle_guess, name='api_kkomantle_guess'),
    path('api/hint/kkomantle/', api_kkomantle_hint, name='api_kkomantle_hint'),
    path('api/surrender/kkomantle/', api_kkomantle_surrender, name='api_kkomantle_surrender'),
    path('api/history/kkomantle/', api_kkomantle_history, name='api_kkomantle_history'),
    path('api/challenge/kkomantle/start/', api_kkomantle_challenge_start, name='api_kkomantle_challenge_start'),
    path('api/challenge/kkomantle/guess/', api_kkomantle_challenge_guess, name='api_kkomantle_challenge_guess'),
    path('api/challenge/kkomantle/rank/', api_kkomantle_challenge_rank, name='api_kkomantle_challenge_rank'),
    path('policy/privacy/', policy_privacy, name='policy_privacy'),
    path('policy/terms/', policy_terms, name='policy_terms'),
    path('policy/disclosure/', policy_disclosure, name='policy_disclosure'),
    path('contact/', contact, name='contact'),
    
    # robots.txt와 sitemap.xml 경로 추가
    path("robots.txt", robots_txt),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps_dict}, name='django.contrib.sitemaps.views.sitemap'),
    path('rss.xml', WordPressPostFeed(), name='rss_feed'),
    
]
