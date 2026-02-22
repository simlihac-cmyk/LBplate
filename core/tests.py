import json
import datetime
import os
import tempfile
import requests
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import (
    DiscussionMessage,
    DiscussionTopic,
    FreeBoardComment,
    FreeBoardPost,
    GameRecord,
    KkomantleDailySnapshot,
)
from . import views
from .management.commands.build_kkomantle_whitelist import (
    normalize_dict_word,
    payload_has_exact_word,
)


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

    def test_load_kkomantle_whitelist_filters_invalid_words(self):
        vocabulary = {'세포', '핵심', '있는', '으로부터'}
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as fp:
            fp.write('# comment\n')
            fp.write('세포\n')
            fp.write('핵심\n')
            fp.write('있는\n')
            fp.write('abc\n')
            fp.write('으로부터\n')
            fp.write('세포\n')
            whitelist_path = fp.name

        try:
            loaded = views._load_kkomantle_whitelist(whitelist_path, vocabulary)
        finally:
            os.unlink(whitelist_path)

        self.assertEqual(loaded, {'세포', '핵심'})

    @patch('core.views.get_daily_word', return_value='세포')
    @patch('core.views.get_top_words', return_value=['핵심'])
    def test_kkomantle_guess_accepts_words_outside_whitelist(self, _mock_top_words, _mock_daily_word):
        class DummyModel:
            key_to_index = {'세포': 0, '핵심': 1, '기호': 2}

            def similarity(self, _secret, _guess):
                return 0.42

        with patch('core.views.model', DummyModel()), patch('core.views.WORD_WHITELIST', {'세포', '핵심'}):
            response = self.client.post(
                reverse('api_kkomantle_guess'),
                data=json.dumps({'word': '기호'}),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['result'], 'success')
        self.assertEqual(payload['rank'], '3000+')
        self.assertEqual(payload['score'], 42.0)

    def test_get_top_words_is_not_limited_by_whitelist(self):
        class DummyModel:
            key_to_index = {'세포': 0, '핵심': 1, '기호': 2}

            def most_similar(self, _secret, topn=10):
                return [('기호', 0.9), ('핵심', 0.8)][:topn]

        with patch('core.views.model', DummyModel()), patch('core.views.WORD_WHITELIST', {'세포', '핵심'}):
            views.TODAY_CACHE['date'] = None
            views.TODAY_CACHE['secret'] = None
            views.TODAY_CACHE['top_words'] = []
            top_words = views.get_top_words('세포')

        self.assertIn('기호', top_words)
        self.assertIn('핵심', top_words)

    @override_settings(KKOMANTLE_HISTORY_START_DATE='2026-02-18')
    def test_kkomantle_history_api_excludes_today_and_older_than_start_date(self):
        today = timezone.localdate()
        yesterday = today - datetime.timedelta(days=1)
        two_days_ago = today - datetime.timedelta(days=2)
        old_day = datetime.date(2026, 2, 17)

        KkomantleDailySnapshot.objects.create(
            date=today,
            answer='오늘정답',
            top_words=[{'rank': 1, 'word': '오늘', 'score': 99.0}],
        )
        KkomantleDailySnapshot.objects.create(
            date=yesterday,
            answer='어제정답',
            top_words=[{'rank': 1, 'word': '어제', 'score': 88.0}],
        )
        KkomantleDailySnapshot.objects.create(
            date=two_days_ago,
            answer='이틀전정답',
            top_words=[{'rank': 1, 'word': '이틀전', 'score': 77.0}],
        )
        KkomantleDailySnapshot.objects.create(
            date=old_day,
            answer='옛정답',
            top_words=[{'rank': 1, 'word': '옛날', 'score': 66.0}],
        )

        response = self.client.get(reverse('api_kkomantle_history') + '?days=5')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['result'], 'success')
        self.assertEqual(payload['start_date'], '2026-02-18')
        dates = [item['date'] for item in payload['items']]

        self.assertNotIn(today.isoformat(), dates)
        self.assertIn(yesterday.isoformat(), dates)
        self.assertIn(two_days_ago.isoformat(), dates)
        self.assertNotIn(old_day.isoformat(), dates)

    def test_payload_has_exact_word_handles_word_and_word_info(self):
        payload_direct = {
            'channel': {
                'total': 1,
                'item': [{'word': '사과-나무'}]
            }
        }
        payload_info = {
            'channel': {
                'total': '1',
                'item': [{'word_info': {'word': '  사과 나무  '}}]
            }
        }

        self.assertTrue(payload_has_exact_word(payload_direct, '사과나무'))
        self.assertTrue(payload_has_exact_word(payload_info, '사과나무'))
        self.assertFalse(payload_has_exact_word(payload_info, '사과'))

    def test_normalize_dict_word_strips_separators(self):
        self.assertEqual(normalize_dict_word(' 사과-나무 '), '사과나무')
        self.assertEqual(normalize_dict_word('사과^나무'), '사과나무')
        self.assertEqual(normalize_dict_word(None), '')

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

    @patch('core.feeds.fetch_wp_json')
    def test_rss_feed_includes_wordpress_posts(self, mock_fetch_wp_json):
        mock_fetch_wp_json.return_value = (
            [
                {
                    'id': 77,
                    'title': {'rendered': '테스트 <b>포스트</b>'},
                    'excerpt': {'rendered': '<p>RSS 설명</p>'},
                    'date_gmt': '2026-02-15T03:10:00',
                }
            ],
            {},
        )

        response = self.client.get(reverse('rss_feed'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/post/77/')
        self.assertContains(response, '테스트 포스트')

    @patch('core.feeds.fetch_wp_json')
    def test_rss_feed_falls_back_when_wp_fetch_fails(self, mock_fetch_wp_json):
        mock_fetch_wp_json.side_effect = requests.RequestException('wp down')

        response = self.client.get(reverse('rss_feed'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LBPlate Home')
        self.assertContains(response, '/')

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

    @patch('core.views.CANDIDATES', ['정답'])
    @patch('core.views.MODEL_VOCABULARY', {'정답', '오답'})
    def test_kkomantle_challenge_start_returns_round_hint(self):
        class DummyModel:
            key_to_index = {'정답': 0, '오답': 1}

            def most_similar(self, _secret, topn=10):
                words = [f"단어{chr(0xAC00 + i)}" for i in range(120)]
                return [(w, 0.8) for w in words[:topn]]

            def similarity(self, first, second):
                if first == second:
                    return 1.0
                return 0.33

        with patch('core.views.model', DummyModel()):
            response = self.client.post(
                reverse('api_kkomantle_challenge_start'),
                data=json.dumps({'start': True}),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['result'], 'success')
        self.assertEqual(payload['round'], 1)
        self.assertEqual(payload['attempt_left'], 10)
        self.assertEqual([row['rank'] for row in payload['hint']], [25, 30, 35])

    @patch('core.views.CANDIDATES', ['정답'])
    @patch('core.views.MODEL_VOCABULARY', {'정답', '오답'})
    def test_kkomantle_challenge_guess_round_clear(self):
        class DummyModel:
            key_to_index = {'정답': 0, '오답': 1}

            def most_similar(self, _secret, topn=10):
                words = [f"단어{chr(0xAC00 + i)}" for i in range(120)]
                return [(w, 0.8) for w in words[:topn]]

            def similarity(self, first, second):
                if first == second:
                    return 1.0
                return 0.2

        with patch('core.views.model', DummyModel()):
            self.client.post(
                reverse('api_kkomantle_challenge_start'),
                data=json.dumps({'start': True}),
                content_type='application/json'
            )

            response = self.client.post(
                reverse('api_kkomantle_challenge_guess'),
                data=json.dumps({'word': '정답'}),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['result'], 'round_clear')
        self.assertEqual(payload['solved_rounds'], 1)
        self.assertEqual(payload['next_round'], 2)
        self.assertEqual(payload['attempt_left'], 10)

    @patch('core.views.CANDIDATES', ['정답'])
    def test_kkomantle_challenge_rank_submit_after_game_over(self):
        wrong_words = ['오답가', '오답나', '오답다', '오답라', '오답마', '오답바', '오답사', '오답아', '오답자', '오답차']
        vocab = {'정답', *wrong_words}

        class DummyModel:
            key_to_index = {word: idx for idx, word in enumerate(vocab)}

            def most_similar(self, _secret, topn=10):
                words = [f"단어{chr(0xAC00 + i)}" for i in range(120)]
                return [(w, 0.8) for w in words[:topn]]

            def similarity(self, first, second):
                if first == second:
                    return 1.0
                return 0.11

        with patch('core.views.model', DummyModel()), patch('core.views.MODEL_VOCABULARY', vocab):
            self.client.post(
                reverse('api_kkomantle_challenge_start'),
                data=json.dumps({'start': True}),
                content_type='application/json'
            )

            url_guess = reverse('api_kkomantle_challenge_guess')
            for wrong_word in wrong_words[:9]:
                guess_response = self.client.post(
                    url_guess,
                    data=json.dumps({'word': wrong_word}),
                    content_type='application/json'
                )
                self.assertEqual(guess_response.status_code, 200)
                self.assertEqual(guess_response.json()['result'], 'success')

            final_response = self.client.post(
                url_guess,
                data=json.dumps({'word': wrong_words[9]}),
                content_type='application/json'
            )
        self.assertEqual(final_response.status_code, 200)
        final_payload = final_response.json()
        self.assertEqual(final_payload['result'], 'game_over')
        self.assertEqual(final_payload['eligible_score'], 0)

        submit_response = self.client.post(
            reverse('api_kkomantle_challenge_rank'),
            data=json.dumps({'player_name': 'tester', 'score': 0}),
            content_type='application/json'
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.json()['status'], 'success')
        self.assertEqual(
            GameRecord.objects.filter(game_type='kkomantle_challenge', score=0).count(),
            1,
        )

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse('signup'),
            data={
                'username': 'newmember',
                'email': 'newmember@example.com',
                'password1': 'StrongPass!12345',
                'password2': 'StrongPass!12345',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(username='newmember').exists())
        self.assertIn('_auth_user_id', self.client.session)

    def test_free_board_list_is_public_read(self):
        user = get_user_model().objects.create_user('reader', password='ReadPass!123')
        FreeBoardPost.objects.create(
            title='첫 자유글',
            content='로그인 없이도 읽을 수 있어야 합니다.',
            author=user,
        )

        response = self.client.get(reverse('free_board_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '첫 자유글')

    def test_free_board_create_requires_login(self):
        response = self.client.get(reverse('free_board_create'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_logged_in_user_can_create_post_and_comment(self):
        user = get_user_model().objects.create_user('writer', password='WritePass!123')
        self.client.force_login(user)

        create_response = self.client.post(
            reverse('free_board_create'),
            data={'title': '작성 테스트', 'content': '본문 테스트 내용'},
        )
        self.assertEqual(create_response.status_code, 302)

        post = FreeBoardPost.objects.get(title='작성 테스트')
        comment_response = self.client.post(
            reverse('free_board_comment_create', args=[post.pk]),
            data={'content': '첫 댓글'},
        )

        self.assertEqual(comment_response.status_code, 302)
        self.assertEqual(FreeBoardComment.objects.filter(post=post).count(), 1)

    def test_discussion_list_requires_login(self):
        response = self.client.get(reverse('discussion_topic_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_logged_in_user_can_write_discussion_message(self):
        user = get_user_model().objects.create_user('debater', password='DebatePass!123')
        topic = DiscussionTopic.objects.create(
            title='항생제 내성 문제',
            description='예방 전략에 대해 토론해봅시다.',
            created_by=user,
        )

        self.client.force_login(user)
        response = self.client.post(
            reverse('discussion_message_create', args=[topic.slug]),
            data={'content': '병원 내 감염 관리와 처방 최적화가 중요합니다.'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DiscussionMessage.objects.filter(topic=topic, author=user).count(),
            1,
        )
