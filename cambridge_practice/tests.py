import json
import re
import tempfile
from types import SimpleNamespace
from xml.etree import ElementTree

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AnswerKey, Feedback, PracticeAttempt, PracticeResult
from .services import grade_answers
from .views import clean_submitted_answers


class SeoEndpointTests(SimpleTestCase):
    def test_sitemap_lists_only_public_browse_pages(self):
        response = self.client.get(reverse('cambridge_practice:sitemap'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/xml'))
        root = ElementTree.fromstring(response.content)
        namespace = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locations = [
            element.text
            for element in root.findall('sitemap:url/sitemap:loc', namespace)
        ]
        self.assertEqual(locations, [
            'https://onlinefreemocktest.com/',
            'https://onlinefreemocktest.com/books/11/',
            'https://onlinefreemocktest.com/books/11/tests/1/',
        ])
        self.assertNotIn('/login/', response.content.decode())
        self.assertNotIn('/listening/', response.content.decode())
        self.assertEqual(response['Cache-Control'], 'public, max-age=3600')

    def test_robots_allows_public_pages_and_blocks_private_flows(self):
        response = self.client.get(reverse('cambridge_practice:robots'))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertIn('User-agent: *', content)
        self.assertIn('Allow: /', content)
        self.assertIn('Disallow: /admin/', content)
        self.assertIn('Disallow: /past-results/', content)
        self.assertIn('Disallow: /books/*/tests/*/listening/', content)
        self.assertIn('Disallow: /books/*/tests/*/reading/', content)
        self.assertIn(
            'Sitemap: https://onlinefreemocktest.com/sitemap.xml',
            content,
        )
        self.assertEqual(response['Cache-Control'], 'public, max-age=3600')


class AnswerNormalizationTests(SimpleTestCase):
    def test_grading_ignores_case_for_text_answers(self):
        answer_key = AnswerKey(
            section=PracticeAttempt.SECTION_LISTENING,
            answers={
                '1': 'hostel',
                '2': 'Buckleigh',
            },
        )

        score, details = grade_answers(answer_key, {
            '1': 'HOSTEL',
            '2': 'buckleigh',
        })

        self.assertEqual(score, 2)
        self.assertTrue(details['1']['correct'])
        self.assertTrue(details['2']['correct'])

    def test_grading_accepts_numeric_and_postcode_answers_without_spaces(self):
        answer_key = AnswerKey(
            section=PracticeAttempt.SECTION_LISTENING,
            answers={
                '3': 'PE9 7QT',
                '9': '4.30 (pm) / half past four',
                '10': '07788 136711',
            },
        )

        score, details = grade_answers(answer_key, {
            '3': 'pe97qt',
            '9': '4.30pm',
            '10': '07788136711',
        })

        self.assertEqual(score, 3)
        self.assertTrue(details['3']['correct'])
        self.assertTrue(details['9']['correct'])
        self.assertTrue(details['10']['correct'])

    def test_submitted_answers_are_saved_uppercase(self):
        answers = clean_submitted_answers({
            '1': 'hostel',
            '2': 'Buckleigh',
            '3': 'pe9 7qt',
        })

        self.assertEqual(answers['1'], 'HOSTEL')
        self.assertEqual(answers['2'], 'BUCKLEIGH')
        self.assertEqual(answers['3'], 'PE9 7QT')

    def test_either_order_groups_score_each_answer_individually(self):
        answer_key = AnswerKey(
            section=PracticeAttempt.SECTION_LISTENING,
            scoring_rules={'either_order_groups': [[11, 12]]},
            answers={
                '11': 'A',
                '12': 'B',
            },
        )

        score, details = grade_answers(answer_key, {
            '11': 'A',
            '12': 'C',
        })

        self.assertEqual(score, 1)
        self.assertTrue(details['11']['correct'])
        self.assertFalse(details['12']['correct'])

    def test_either_order_groups_still_accept_reversed_correct_answers(self):
        answer_key = AnswerKey(
            section=PracticeAttempt.SECTION_LISTENING,
            scoring_rules={'either_order_groups': [[11, 12]]},
            answers={
                '11': 'A',
                '12': 'B',
            },
        )

        score, details = grade_answers(answer_key, {
            '11': 'B',
            '12': 'A',
        })

        self.assertEqual(score, 2)
        self.assertTrue(details['11']['correct'])
        self.assertTrue(details['12']['correct'])


class PracticeContentIntegrityTests(SimpleTestCase):
    def test_answer_key_json_has_all_40_answers_for_every_section(self):
        data_path = settings.BASE_DIR / 'cambridge_practice' / 'data' / 'answer_keys.json'
        answer_keys = json.loads(data_path.read_text(encoding='utf-8'))

        self.assertEqual(len(answer_keys), 80)
        for answer_key in answer_keys:
            with self.subTest(
                book=answer_key['book_number'],
                test=answer_key['test_number'],
                section=answer_key['section'],
            ):
                expected_questions = {str(number) for number in range(1, 41)}
                self.assertEqual(set(answer_key['answers']), expected_questions)

    def test_each_section_template_has_answer_inputs_1_to_40(self):
        data_path = settings.BASE_DIR / 'cambridge_practice' / 'data' / 'answer_keys.json'
        answer_keys = json.loads(data_path.read_text(encoding='utf-8'))

        for answer_key in answer_keys:
            template_path = (
                settings.BASE_DIR
                / 'templates'
                / f"mock{answer_key['book_number']}_test{answer_key['test_number']}_{answer_key['section']}.html"
            )
            with self.subTest(template=template_path.name):
                self.assertTrue(template_path.exists())
                template = template_path.read_text(encoding='utf-8')
                inputs = set(re.findall(r'name=["\']answer_(\d+)["\']', template))
                expected_questions = {str(number) for number in range(1, 41)}
                self.assertEqual(inputs, expected_questions)

    def test_listening_parts_are_separate_papers(self):
        for template_path in sorted((settings.BASE_DIR / 'templates').glob('mock*_test*_listening.html')):
            with self.subTest(template=template_path.name):
                template = template_path.read_text(encoding='utf-8')
                section_count = len(re.findall(r'<section class="ielts-section(?:\s[^"]*)?">', template))
                paper_count = template.count('<article class="ielts-paper">')
                self.assertGreaterEqual(section_count, 4)
                self.assertEqual(paper_count, section_count)

    def test_reading_passages_and_question_sections_are_separate(self):
        for template_path in sorted((settings.BASE_DIR / 'templates').glob('mock*_test*_reading.html')):
            with self.subTest(template=template_path.name):
                template = template_path.read_text(encoding='utf-8')
                self.assertEqual(template.count('<article class="reading-passage-block"'), 3)
                self.assertEqual(template.count('<article class="reading-question-card"'), 3)

    def test_official_answer_keys_grade_to_full_score(self):
        data_path = settings.BASE_DIR / 'cambridge_practice' / 'data' / 'answer_keys.json'
        answer_keys = json.loads(data_path.read_text(encoding='utf-8'))

        for answer_key_data in answer_keys:
            answer_key = AnswerKey(
                book_number=answer_key_data['book_number'],
                test_number=answer_key_data['test_number'],
                section=answer_key_data['section'],
                answers=answer_key_data['answers'],
                scoring_rules=answer_key_data.get('scoring_rules', {}),
            )
            with self.subTest(
                book=answer_key.book_number,
                test=answer_key.test_number,
                section=answer_key.section,
            ):
                score, details = grade_answers(answer_key, answer_key.answers)
                self.assertEqual(score, 40, [
                    question
                    for question, detail in details.items()
                    if not detail['correct']
                ])

    def test_each_section_template_renders(self):
        data_path = settings.BASE_DIR / 'cambridge_practice' / 'data' / 'answer_keys.json'
        answer_keys = json.loads(data_path.read_text(encoding='utf-8'))
        request = RequestFactory().get('/')
        request.user = AnonymousUser()

        for answer_key in answer_keys:
            template_name = (
                f"mock{answer_key['book_number']}_test"
                f"{answer_key['test_number']}_{answer_key['section']}.html"
            )
            attempt = SimpleNamespace(
                status=PracticeAttempt.STATUS_IN_PROGRESS,
                time_remaining_seconds=3600,
                review_remaining_seconds=None,
                answers={},
            )
            context = {
                'attempt': attempt,
                'book': {
                    'number': answer_key['book_number'],
                    'title': f"IELTS Mock {answer_key['book_number']}",
                },
                'test': {
                    'number': answer_key['test_number'],
                    'title': f"Test {answer_key['test_number']}",
                },
                'section': answer_key['section'],
                'section_title': answer_key['section'].title(),
                'question_groups': [],
                'audio_path': (
                    f"{answer_key['book_number']}/audio/"
                    f"test{answer_key['test_number']}/merged.mp3"
                ),
                'duration_seconds': 3600,
                'review_seconds': 120,
                'has_pro_access': False,
                'result': None,
                'result_details': {},
                'is_preview': False,
            }

            with self.subTest(template=template_name):
                html = render_to_string(template_name, context, request=request)
                self.assertIn('practiceForm', html)


class PastResultsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='student',
            password='strong-pass-123',
        )
        self.attempt = PracticeAttempt.objects.create(
            user=self.user,
            book_number=11,
            test_number=2,
            section=PracticeAttempt.SECTION_READING,
            answers={
                str(number): ''
                for number in range(1, 41)
            } | {'11': 'STABILISING GUIDES'},
            status=PracticeAttempt.STATUS_COMPLETED,
            time_remaining_seconds=0,
            completed_at=timezone.now(),
        )
        self.result = PracticeResult.objects.create(
            attempt=self.attempt,
            score=35,
            band_score=8.0,
            total_questions=40,
            submitted_answers=self.attempt.answers,
            correct_answers={'11': 'stabilising guides'},
            details={
                '11': {
                    'submitted': 'STABILISING GUIDES',
                    'official': 'stabilising guides',
                    'correct': True,
                },
            },
        )

    def test_past_results_lists_saved_results(self):
        self.client.login(username='student', password='strong-pass-123')

        response = self.client.get(reverse('cambridge_practice:past_results'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IELTS Mock 11 – Test 2')
        self.assertContains(response, '35<small>/40</small>')
        self.assertContains(response, 'Band 8.0')
        self.assertContains(
            response,
            reverse('cambridge_practice:practice_result_detail', args=[self.result.id]),
        )

    def test_result_detail_renders_completed_attempt_for_review(self):
        self.client.login(username='student', password='strong-pass-123')

        response = self.client.get(
            reverse('cambridge_practice:practice_result_detail', args=[self.result.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-status="completed"')
        self.assertContains(response, 'data-existing-score="35"')
        self.assertContains(response, 'STABILISING GUIDES')

    def test_result_detail_does_not_show_another_users_result(self):
        other_user = get_user_model().objects.create_user(
            username='other',
            password='strong-pass-123',
        )
        self.client.force_login(other_user)

        response = self.client.get(
            reverse('cambridge_practice:practice_result_detail', args=[self.result.id])
        )

        self.assertEqual(response.status_code, 404)


class FeedbackViewTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)

    def test_feedback_page_renders_upload_controls(self):
        response = self.client.get(reverse('cambridge_practice:feedback'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Drop one image here')
        self.assertContains(response, 'Choose image')
        self.assertContains(response, 'Suggestion')
        self.assertContains(response, 'Problem report')

    def test_feedback_submission_saves_optional_image(self):
        image = SimpleUploadedFile(
            'problem.png',
            (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02'
                b'\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT'
                b'\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01'
                b'\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82'
            ),
            content_type='image/png',
        )

        with self.settings(MEDIA_ROOT=self.media_dir.name):
            response = self.client.post(reverse('cambridge_practice:feedback'), {
                'feedback_type': Feedback.TYPE_PROBLEM,
                'name': 'Student',
                'email': 'student@example.com',
                'page_url': 'https://onlinefreemocktest.com/books/11/tests/1/listening/',
                'message': 'The audio did not start.',
                'image': image,
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'submitted successfully')
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.feedback_type, Feedback.TYPE_PROBLEM)
        self.assertEqual(feedback.message, 'The audio did not start.')
        self.assertTrue(feedback.image.name.startswith('feedback/'))
