import datetime

import requests
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.core.cache import cache
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone


def fetch_wp_posts_for_sitemap():
    cache_timeout = getattr(settings, 'WP_SITEMAP_CACHE_TIMEOUT', 3600)
    cache_key = 'sitemap:wp:posts'
    cached_posts = cache.get(cache_key)
    if cached_posts is not None:
        return cached_posts

    wp_base_url = getattr(settings, 'WP_BASE_URL', 'http://127.0.0.1:4080/wp-json/wp/v2')
    wp_timeout = getattr(settings, 'WP_REQUEST_TIMEOUT', 5)
    posts = []
    page = 1
    per_page = 100

    while True:
        response = requests.get(
            f'{wp_base_url}/posts',
            params={'per_page': per_page, 'page': page, '_fields': 'id,modified_gmt,modified'},
            timeout=wp_timeout,
        )
        response.raise_for_status()
        posts.extend(response.json())

        total_pages = int(response.headers.get('X-WP-TotalPages', '1'))
        if page >= total_pages:
            break
        page += 1

    cache.set(cache_key, posts, timeout=cache_timeout)
    return posts


class StaticViewSitemap(Sitemap):
    protocol = 'https'
    priority = 0.8
    changefreq = 'daily'

    def items(self):
        return [
            'home',
            'blog_home',
            'utility_home',
            'games_lobby',
            'game_2048',
            'game_reaction',
            'game_wordle',
            'game_kkomantle',
            'ladder',
            'roulette',
            'policy_privacy',
            'policy_terms',
            'policy_disclosure',
            'contact',
        ]

    def location(self, item):
        return reverse(item)


class WordPressPostSitemap(Sitemap):
    protocol = 'https'
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        try:
            return fetch_wp_posts_for_sitemap()
        except (requests.RequestException, ValueError):
            return []

    def location(self, item):
        return reverse('post_detail', kwargs={'post_id': item['id']})

    def lastmod(self, item):
        raw_datetime = item.get('modified_gmt') or item.get('modified')
        parsed = parse_datetime(raw_datetime or '')
        if not parsed:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, datetime.timezone.utc)
        return parsed
