from django.test import SimpleTestCase

from .models import AnswerKey, PracticeAttempt
from .services import grade_answers
from .views import clean_submitted_answers


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
