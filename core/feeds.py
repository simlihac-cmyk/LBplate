import datetime
from html import unescape

import requests
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags

from .views import fetch_wp_json


class WordPressPostFeed(Feed):
    title = 'LBPlate Blog'
    description = 'LBPlate 최신 포스트 RSS'
    link = '/blog/'
    feed_url = '/rss.xml'
    language = 'ko'

    def _fallback_items(self):
        now = timezone.now()
        return [
            {
                'title': 'LBPlate Home',
                'description': 'LBPlate 메인 페이지',
                'link': reverse('home'),
                'pubdate': now,
            },
            {
                'title': 'LBPlate Blog',
                'description': 'LBPlate 블로그',
                'link': reverse('blog_home'),
                'pubdate': now,
            },
        ]

    def items(self):
        try:
            posts, _ = fetch_wp_json(
                'posts',
                {
                    'per_page': 20,
                    '_embed': True,
                    'orderby': 'date',
                    'order': 'desc',
                },
                cache_timeout=300,
            )
            return posts if posts else self._fallback_items()
        except requests.RequestException:
            return self._fallback_items()
        except ValueError:
            return self._fallback_items()

    def item_title(self, item):
        title = item.get('title', '')
        if isinstance(title, dict):
            rendered = title.get('rendered', '')
        else:
            rendered = str(title)
        cleaned = unescape(strip_tags(rendered)).strip()
        return cleaned or f"Post {item.get('id', '')}".strip() or 'LBPlate'

    def item_description(self, item):
        fallback_description = item.get('description', '')
        if isinstance(fallback_description, str) and fallback_description.strip():
            return fallback_description.strip()

        rendered = (
            item.get('excerpt', {}).get('rendered')
            or item.get('content', {}).get('rendered')
            or ''
        )
        cleaned = ' '.join(unescape(strip_tags(rendered)).split())
        return cleaned[:300]

    def item_link(self, item):
        if item.get('id') is not None:
            return reverse('post_detail', kwargs={'post_id': item['id']})
        return item.get('link', reverse('home'))

    def item_pubdate(self, item):
        pubdate = item.get('pubdate')
        if pubdate is not None:
            return pubdate

        raw_datetime = (
            item.get('date_gmt')
            or item.get('modified_gmt')
            or item.get('date')
            or item.get('modified')
        )
        parsed = parse_datetime(raw_datetime or '')
        if not parsed:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, datetime.timezone.utc)
        return parsed
