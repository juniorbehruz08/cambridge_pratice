import json
from pathlib import Path

from django.core.management.base import BaseCommand

from cambridge_practice.models import AnswerKey, PracticeAttempt


BOOK_NUMBERS = range(11, 21)
TEST_NUMBERS = range(1, 5)
SECTIONS = [
    PracticeAttempt.SECTION_LISTENING,
    PracticeAttempt.SECTION_READING,
]


def empty_answers():
    return {str(number): '' for number in range(1, 41)}


class Command(BaseCommand):
    help = 'Create placeholder answer keys for all books and import verified answer-key data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default='cambridge_practice/data/answer_keys.json',
            help='Path to the JSON answer-key seed file.',
        )

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for book_number in BOOK_NUMBERS:
            for test_number in TEST_NUMBERS:
                for section in SECTIONS:
                    _, was_created = AnswerKey.objects.get_or_create(
                        book_number=book_number,
                        test_number=test_number,
                        section=section,
                        defaults={
                            'answers': empty_answers(),
                            'source': 'Placeholder for admin editing',
                        },
                    )
                    if was_created:
                        created += 1

        seed_path = Path(options['file'])
        if not seed_path.is_absolute():
            seed_path = Path.cwd() / seed_path

        if seed_path.exists():
            data = json.loads(seed_path.read_text(encoding='utf-8'))
            for item in data:
                answers = {
                    str(number): item.get('answers', {}).get(str(number), '')
                    for number in range(1, 41)
                }
                _, was_created = AnswerKey.objects.update_or_create(
                    book_number=item['book_number'],
                    test_number=item['test_number'],
                    section=item['section'],
                    defaults={
                        'answers': answers,
                        'scoring_rules': item.get('scoring_rules', {}),
                        'is_verified': item.get('is_verified', False),
                        'source': item.get('source', ''),
                        'notes': item.get('notes', ''),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Answer keys ready. Created {created}, updated {updated}. '
            f'Total records: {AnswerKey.objects.count()}.'
        ))
