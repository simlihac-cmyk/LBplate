import json
import requests
from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
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
