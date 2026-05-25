import re
from collections import Counter

from .models import AnswerKey, PracticeResult


BAND_TABLES = {
    'listening': [
        (39, 40, 9.0),
        (37, 38, 8.5),
        (35, 36, 8.0),
        (32, 34, 7.5),
        (30, 31, 7.0),
        (26, 29, 6.5),
        (23, 25, 6.0),
        (18, 22, 5.5),
        (16, 17, 5.0),
        (13, 15, 4.5),
        (10, 12, 4.0),
    ],
    'reading': [
        (39, 40, 9.0),
        (37, 38, 8.5),
        (35, 36, 8.0),
        (33, 34, 7.5),
        (30, 32, 7.0),
        (27, 29, 6.5),
        (23, 26, 6.0),
        (19, 22, 5.5),
        (15, 18, 5.0),
        (13, 14, 4.5),
        (10, 12, 4.0),
    ],
}


def normalize_answer(value):
    value = str(value or '').strip().lower()
    value = value.replace('’', "'")
    value = value.replace('–', '-')
    value = value.replace('£', '')
    value = value.replace('$', '')
    value = re.sub(r'\s+', ' ', value)
    return value


def format_answer_for_display(value):
    value = str(value or '').strip()
    value = re.sub(r'\s*/\s*', ' / ', value)
    value = value.replace(' I ', ' / ')
    return re.sub(r'\s+', ' ', value)


def official_answer_for_display(answer_key, question_id):
    display_answers = answer_key.scoring_rules.get('display_answers', {})
    official = display_answers.get(str(question_id))
    if official:
        return official

    return format_answer_for_display((answer_key.answers or {}).get(str(question_id), ''))


def expand_optional_parentheses(value):
    value = str(value or '')
    variants = {value}

    if '(' in value and ')' in value:
        without_brackets = re.sub(r'[()]', '', value)
        without_optional = re.sub(r'\s*\([^)]*\)', '', value)
        variants.add(without_brackets)
        variants.add(without_optional)

    return variants


def alternatives_for(value):
    alternatives = set()
    if isinstance(value, list):
        values = value
    else:
        value = str(value or '')
        full_value = normalize_answer(value)
        if full_value:
            alternatives.add(full_value)
        value = value.replace(' I ', ' / ')
        values = [part.strip() for part in value.split('/')]
        if len(values) > 1:
            expanded_values = []
            previous_words = []
            for part in values:
                if part:
                    words = part.split()
                    if previous_words and len(words) < len(previous_words):
                        expanded_values.append(' '.join(previous_words[:-len(words)] + words))
                    expanded_values.append(part)
                    previous_words = words
            values = expanded_values

    for part in values:
        if not str(part).strip():
            continue
        for variant in expand_optional_parentheses(part):
            normalized = normalize_answer(variant)
            if normalized:
                alternatives.add(normalized)

    return list(alternatives)


def grade_answers(answer_key, submitted_answers):
    official = answer_key.answers or {}
    submitted = submitted_answers or {}
    either_order_groups = answer_key.scoring_rules.get('either_order_groups', [])
    grouped_questions = {
        str(question)
        for group in either_order_groups
        for question in group
    }

    details = {}
    score = 0

    for question in range(1, 41):
        q = str(question)
        if q in grouped_questions:
            continue

        user_answer = normalize_answer(submitted.get(q, ''))
        official_answers = alternatives_for(official.get(q, ''))
        is_correct = bool(user_answer and user_answer in official_answers)
        if is_correct:
            score += 1

        details[q] = {
            'submitted': submitted.get(q, ''),
            'official': official_answer_for_display(answer_key, q),
            'correct': is_correct,
        }

    for group in either_order_groups:
        question_ids = [str(question) for question in group]
        official_values = [
            normalize_answer(official.get(question_id, ''))
            for question_id in question_ids
        ]
        submitted_values = [
            normalize_answer(submitted.get(question_id, ''))
            for question_id in question_ids
        ]
        is_group_correct = Counter(submitted_values) == Counter(official_values)

        if is_group_correct:
            score += len(question_ids)

        for question_id in question_ids:
            details[question_id] = {
                'submitted': submitted.get(question_id, ''),
                'official': official_answer_for_display(answer_key, question_id),
                'correct': is_group_correct,
                'either_order_group': question_ids,
            }

    return score, details


def band_score_for(section, score):
    for low, high, band in BAND_TABLES.get(section, []):
        if low <= score <= high:
            return band

    return 0.0


def create_or_update_result(attempt):
    answer_key = AnswerKey.objects.filter(
        book_number=attempt.book_number,
        test_number=attempt.test_number,
        section=attempt.section,
        is_verified=True,
    ).first()

    if answer_key is None:
        return None

    score, details = grade_answers(answer_key, attempt.answers)
    band_score = band_score_for(attempt.section, score)

    result, _ = PracticeResult.objects.update_or_create(
        attempt=attempt,
        defaults={
            'answer_key': answer_key,
            'score': score,
            'band_score': band_score,
            'total_questions': 40,
            'submitted_answers': attempt.answers,
            'correct_answers': answer_key.answers,
            'details': details,
        },
    )
    return result
