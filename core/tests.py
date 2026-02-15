import json
import datetime
import requests
from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import GameRecord


@override_settings(SECURE_SSL_REDIRECT=False)
class CoreViewTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('core.views.fetch_wp_json')
    def test_post_detail_returns_404_when_wp_fetch_fails(self, mock_fetch_wp_json):
        mock_fetch_wp_json.side_effect = requests.RequestException('wp down')

        response = self.client.get(reverse('post_detail', args=[9999]))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, '요청한 글을 찾을 수 없습니다.', status_code=404)

    def test_api_2048_rank_rejects_out_of_range_score(self):
        response = self.client.post(
            reverse('api_2048_rank'),
            data=json.dumps({'player_name': 'tester', 'score': 999999999}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(GameRecord.objects.filter(game_type='2048').count(), 0)

    def test_api_2048_rank_accepts_valid_score(self):
        response = self.client.post(
            reverse('api_2048_rank'),
            data=json.dumps({'player_name': 'abcdefghijk', 'score': 1024}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        record = GameRecord.objects.get(game_type='2048')
        self.assertEqual(record.score, 1024)
        self.assertEqual(record.player_name, 'abcdefghij')

    def test_api_reaction_rank_rejects_out_of_range_score(self):
        response = self.client.post(
            reverse('api_reaction_rank'),
            data=json.dumps({'player_name': 'tester', 'score': 20}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(GameRecord.objects.filter(game_type='reaction').count(), 0)

    def test_api_wordle_rank_rejects_invalid_attempt_count(self):
        response = self.client.post(
            reverse('api_wordle_rank'),
            data=json.dumps({'player_name': 'tester', 'score': 9}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(GameRecord.objects.filter(game_type='wordle').count(), 0)

    @override_settings(KKOMANTLE_POST_RATE_LIMIT=2, KKOMANTLE_POST_RATE_WINDOW=60)
    def test_kkomantle_api_rate_limit_blocks_excess_requests(self):
        url = reverse('api_kkomantle_guess')
        payload = json.dumps({'word': '세포'})

        first = self.client.post(url, data=payload, content_type='application/json')
        second = self.client.post(url, data=payload, content_type='application/json')
        third = self.client.post(url, data=payload, content_type='application/json')

        self.assertNotEqual(first.status_code, 429)
        self.assertNotEqual(second.status_code, 429)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()['result'], 'error')

    @override_settings(GAME_RANK_POST_RATE_LIMIT=1, GAME_RANK_POST_RATE_WINDOW=60)
    def test_rank_api_rate_limit_blocks_second_post(self):
        url = reverse('api_2048_rank')
        first = self.client.post(
            url,
            data=json.dumps({'player_name': 'tester', 'score': 128}),
            content_type='application/json'
        )
        second = self.client.post(
            url,
            data=json.dumps({'player_name': 'tester', 'score': 256}),
            content_type='application/json'
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(GameRecord.objects.filter(game_type='2048').count(), 1)

    def test_utility_and_policy_pages_are_available(self):
        urls = [
            reverse('utility_home'),
            reverse('policy_privacy'),
            reverse('policy_terms'),
            reverse('policy_disclosure'),
            reverse('contact'),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    @patch('core.sitemaps.fetch_wp_posts_for_sitemap')
    def test_sitemap_includes_wordpress_posts(self, mock_fetch_wp_posts):
        mock_fetch_wp_posts.return_value = [
            {'id': 42, 'modified_gmt': '2026-02-15T03:10:00'}
        ]

        response = self.client.get(reverse('django.contrib.sitemaps.views.sitemap'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/utility/')
        self.assertContains(response, '/post/42/')

    def test_api_2048_rank_weekly_filters_last_7_days(self):
        in_week = GameRecord.objects.create(game_type='2048', player_name='weekuser', score=2048)
        out_week = GameRecord.objects.create(game_type='2048', player_name='olduser', score=4096)

        GameRecord.objects.filter(pk=in_week.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=2)
        )
        GameRecord.objects.filter(pk=out_week.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=9)
        )

        response = self.client.get(reverse('api_2048_rank') + '?period=weekly')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['period'], 'weekly')
        names = [item['name'] for item in payload['ranking']]
        self.assertIn('weekuser', names)
        self.assertNotIn('olduser', names)

    def test_api_reaction_rank_weekly_keeps_ascending_order(self):
        high = GameRecord.objects.create(game_type='reaction', player_name='slowpoke', score=420)
        low = GameRecord.objects.create(game_type='reaction', player_name='quick', score=180)

        GameRecord.objects.filter(pk=high.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=3)
        )
        GameRecord.objects.filter(pk=low.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=1)
        )

        response = self.client.get(reverse('api_reaction_rank') + '?period=weekly')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['period'], 'weekly')
        self.assertGreaterEqual(len(payload['ranking']), 2)
        self.assertEqual(payload['ranking'][0]['name'], 'quick')
