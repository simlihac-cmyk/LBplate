from django.contrib import admin
from django.conf import settings
from django.http import HttpResponse
from django.urls import path
from django.contrib.sitemaps.views import sitemap
from core.feeds import WordPressPostFeed
from core.sitemaps import StaticViewSitemap, WordPressPostSitemap
from core.auth_views import (
    google_callback,
    google_login_start,
    login_view,
    logout_view,
    signup_view,
)
from core.community_views import (
    community_hub,
    discussion_message_create,
    discussion_topic_detail,
    discussion_topic_list,
    free_board_comment_create,
    free_board_comment_delete,
    free_board_comment_edit,
    free_board_create,
    free_board_delete,
    free_board_detail,
    free_board_edit,
    free_board_list,
)
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


def ads_txt(request):
    line = getattr(settings, 'ADSENSE_ADS_TXT_ENTRY', '').strip()
    if not line:
        publisher_id = getattr(settings, 'ADSENSE_PUBLISHER_ID', '').strip()
        if publisher_id:
            line = f"google.com, {publisher_id}, DIRECT, f08c47fec0942fa0"
    if not line:
        line = "# ads.txt is not configured yet"
    return HttpResponse(f"{line}\n", content_type="text/plain")


sitemaps_dict = {
    'static': StaticViewSitemap,
    'posts': WordPressPostSitemap,
}

# 3. URL 패턴
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('auth/login/', login_view, name='login'),
    path('auth/signup/', signup_view, name='signup'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/google/start/', google_login_start, name='google_login_start'),
    path('auth/google/callback/', google_callback, name='google_callback'),
    path('blog/', blog_home, name='blog_home'),
    path('community/', community_hub, name='community_hub'),
    path('community/free/', free_board_list, name='free_board_list'),
    path('community/free/new/', free_board_create, name='free_board_create'),
    path('community/free/<int:post_id>/', free_board_detail, name='free_board_detail'),
    path('community/free/<int:post_id>/edit/', free_board_edit, name='free_board_edit'),
    path('community/free/<int:post_id>/delete/', free_board_delete, name='free_board_delete'),
    path('community/free/<int:post_id>/comments/', free_board_comment_create, name='free_board_comment_create'),
    path('community/comments/<int:comment_id>/edit/', free_board_comment_edit, name='free_board_comment_edit'),
    path('community/comments/<int:comment_id>/delete/', free_board_comment_delete, name='free_board_comment_delete'),
    path('community/discussion/', discussion_topic_list, name='discussion_topic_list'),
    path('community/discussion/<str:slug>/', discussion_topic_detail, name='discussion_topic_detail'),
    path('community/discussion/<str:slug>/messages/', discussion_message_create, name='discussion_message_create'),
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
    path("ads.txt", ads_txt),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps_dict}, name='django.contrib.sitemaps.views.sitemap'),
    path('rss.xml', WordPressPostFeed(), name='rss_feed'),
    
]
