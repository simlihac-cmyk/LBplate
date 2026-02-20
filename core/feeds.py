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
            return posts
        except requests.RequestException:
            return []
        except ValueError:
            return []

    def item_title(self, item):
        rendered = item.get('title', {}).get('rendered', '')
        cleaned = unescape(strip_tags(rendered)).strip()
        return cleaned or f"Post {item.get('id', '')}".strip()

    def item_description(self, item):
        rendered = (
            item.get('excerpt', {}).get('rendered')
            or item.get('content', {}).get('rendered')
            or ''
        )
        cleaned = ' '.join(unescape(strip_tags(rendered)).split())
        return cleaned[:300]

    def item_link(self, item):
        return reverse('post_detail', kwargs={'post_id': item['id']})

    def item_pubdate(self, item):
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
