from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.shortcuts import redirect
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.utils import timezone
import json

from .forms import RegisterForm
from .models import AnswerKey, PracticeAttempt, PracticeResult
from .services import band_score_for, create_or_update_result, grade_answers


BOOKS = [
    {
        'number': 11,
        'title': 'Cambridge IELTS 11',
        'requires_pro': False,
    },
    {
        'number': 12,
        'title': 'Cambridge IELTS 12',
        'requires_pro': False,
    },
    {
        'number': 13,
        'title': 'Cambridge IELTS 13',
        'requires_pro': False,
    },
    {
        'number': 14,
        'title': 'Cambridge IELTS 14',
        'requires_pro': False,
    },
    {
        'number': 15,
        'title': 'Cambridge IELTS 15',
        'requires_pro': False,
    },
    {
        'number': 16,
        'title': 'Cambridge IELTS 16',
        'requires_pro': False,
    },
    {
        'number': 17,
        'title': 'Cambridge IELTS 17',
        'requires_pro': False,
    },
    {
        'number': 18,
        'title': 'Cambridge IELTS 18',
        'requires_pro': False,
    },
    {
        'number': 19,
        'title': 'Cambridge IELTS 19',
        'requires_pro': True,
    },
    {
        'number': 20,
        'title': 'Cambridge IELTS 20',
        'requires_pro': True,
    },
]

PRACTICE_TESTS = [
    {
        'number': 1,
        'title': 'Test 1',
        'description': 'Start the first reading and listening practice set for this book.',
    },
    {
        'number': 2,
        'title': 'Test 2',
        'description': 'Continue with the second full Cambridge practice test.',
    },
    {
        'number': 3,
        'title': 'Test 3',
        'description': 'Practice another full test and compare your timing.',
    },
    {
        'number': 4,
        'title': 'Test 4',
        'description': 'Complete the final practice test in this Cambridge book.',
    },
]

PRACTICE_BOOK_NUMBER = 11
PRACTICE_SECTIONS = [
    {
        'slug': PracticeAttempt.SECTION_LISTENING,
        'title': 'Listening',
        'description': 'Listen to the audio and answer questions 1-40.',
    },
    {
        'slug': PracticeAttempt.SECTION_READING,
        'title': 'Reading',
        'description': 'Read the passages and answer questions 1-40.',
    },
]

PREVIEW_BOOK_NUMBER = 11
PREVIEW_TEST_NUMBER = 1


def has_pro_access(user):
    if not user.is_authenticated:
        return False

    profile = getattr(user, 'profile', None)
    return bool(profile and profile.is_pro)


class UnsavedAttempt:
    status = PracticeAttempt.STATUS_IN_PROGRESS
    time_remaining_seconds = 3600
    review_remaining_seconds = None
    answers = {}


def normalize_submitted_answer(value):
    return str(value or '').strip().upper()


def clean_submitted_answers(raw_answers, field_prefix=''):
    return {
        str(number): normalize_submitted_answer(raw_answers.get(f'{field_prefix}{number}', ''))
        for number in range(1, 41)
    }


def user_can_access_book(user, book):
    if not user.is_authenticated:
        return book['number'] == PREVIEW_BOOK_NUMBER

    if book['requires_pro']:
        return has_pro_access(user)

    return True


def user_can_access_test(user, book_number, test_number):
    if not user.is_authenticated:
        return book_number == PREVIEW_BOOK_NUMBER and test_number == PREVIEW_TEST_NUMBER

    return True


def get_book_or_404(book_number, user):
    book = next((item for item in BOOKS if item['number'] == book_number), None)
    if book is None or not user_can_access_book(user, book):
        raise Http404('Book not found')

    return book


def home(request):
    user_is_pro = has_pro_access(request.user)
    books = [
        book for book in BOOKS
        if user_can_access_book(request.user, book)
    ]

    return render(request, 'main.html', {
        'books': books,
        'book_count': len(books),
        'has_pro_access': user_is_pro,
        'is_preview': not request.user.is_authenticated,
    })


def book_detail(request, number):
    book = get_book_or_404(number, request.user)
    tests = [
        test for test in PRACTICE_TESTS
        if user_can_access_test(request.user, number, test['number'])
    ]

    return render(request, 'book_detail.html', {
        'book': book,
        'tests': tests,
        'has_pro_access': has_pro_access(request.user),
        'is_preview': not request.user.is_authenticated,
    })


def get_practice_book_or_404(book_number, user):
    return get_book_or_404(book_number, user)


def get_test_or_404(test_number):
    test = next((item for item in PRACTICE_TESTS if item['number'] == test_number), None)
    if test is None:
        raise Http404('Test not found')

    return test


def ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()

    return request.session.session_key


def get_attempt(request, book_number, test_number, section, create=True):
    session_key = ensure_session_key(request)
    lookup = {
        'book_number': book_number,
        'test_number': test_number,
        'section': section,
    }

    if request.user.is_authenticated:
        lookup['user'] = request.user
    else:
        lookup['user__isnull'] = True
        lookup['session_key'] = session_key

    attempt = PracticeAttempt.objects.filter(**lookup).first()
    if attempt is None and create:
        attempt = PracticeAttempt.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=session_key,
            book_number=book_number,
            test_number=test_number,
            section=section,
        )

    return attempt


def create_attempt(request, book_number, test_number, section):
    session_key = ensure_session_key(request)
    return PracticeAttempt.objects.create(
        user=request.user if request.user.is_authenticated else None,
        session_key='' if request.user.is_authenticated else session_key,
        book_number=book_number,
        test_number=test_number,
        section=section,
    )


def build_question_groups(section, answers):
    if section == PracticeAttempt.SECTION_LISTENING:
        ranges = [
            ('Part 1', range(1, 11), 'Questions 1-10'),
            ('Part 2', range(11, 21), 'Questions 11-20'),
            ('Part 3', range(21, 31), 'Questions 21-30'),
            ('Part 4', range(31, 41), 'Questions 31-40'),
        ]
    else:
        ranges = [
            ('Reading Passage 1', range(1, 14), 'Questions 1-13'),
            ('Reading Passage 2', range(14, 27), 'Questions 14-26'),
            ('Reading Passage 3', range(27, 41), 'Questions 27-40'),
        ]

    return [
        {
            'title': title,
            'label': label,
            'questions': [
                {
                    'number': number,
                    'name': f'answer_{number}',
                    'value': answers.get(str(number), ''),
                }
                for number in numbers
            ],
        }
        for title, numbers, label in ranges
    ]


def practice_template_name(book_number, test_number, section):
    template_name = f'cambridge{book_number}_test{test_number}_{section}.html'
    try:
        get_template(template_name)
    except TemplateDoesNotExist:
        return 'practice_section.html'

    return template_name


def test_detail(request, book_number, test_number):
    book = get_practice_book_or_404(book_number, request.user)
    test = get_test_or_404(test_number)
    if not user_can_access_test(request.user, book_number, test_number):
        raise Http404('Test not found')

    return render(request, 'test_detail.html', {
        'book': book,
        'test': test,
        'sections': PRACTICE_SECTIONS,
        'has_pro_access': has_pro_access(request.user),
        'is_preview': not request.user.is_authenticated,
    })


@login_required
def past_results(request):
    results = (
        PracticeResult.objects
        .select_related('attempt', 'answer_key')
        .filter(attempt__user=request.user)
        .order_by('-attempt__completed_at', '-created_at')[:50]
    )

    return render(request, 'past_results.html', {
        'results': results,
        'has_pro_access': has_pro_access(request.user),
    })


@login_required
def practice_result_detail(request, result_id):
    result = get_object_or_404(
        PracticeResult.objects.select_related('attempt', 'answer_key'),
        pk=result_id,
        attempt__user=request.user,
    )
    attempt = result.attempt
    book = get_practice_book_or_404(attempt.book_number, request.user)
    test = get_test_or_404(attempt.test_number)
    groups = build_question_groups(attempt.section, attempt.answers)
    section_title = dict(PracticeAttempt.SECTION_CHOICES)[attempt.section]

    return render(request, practice_template_name(
        attempt.book_number,
        attempt.test_number,
        attempt.section,
    ), {
        'attempt': attempt,
        'book': book,
        'test': test,
        'section': attempt.section,
        'section_title': section_title,
        'question_groups': groups,
        'audio_path': f'{attempt.book_number}/audio/test{attempt.test_number}/merged.mp3',
        'duration_seconds': 3600,
        'review_seconds': 120,
        'has_pro_access': has_pro_access(request.user),
        'result': result,
        'result_details': result.details,
        'is_preview': False,
    })


def practice_start(request, book_number, test_number, section):
    book = get_practice_book_or_404(book_number, request.user)
    test = get_test_or_404(test_number)
    if not user_can_access_test(request.user, book_number, test_number):
        raise Http404('Test not found')

    if section not in dict(PracticeAttempt.SECTION_CHOICES):
        raise Http404('Practice section not found')

    return render(request, 'practice_start.html', {
        'book': book,
        'test': test,
        'section': section,
        'section_title': dict(PracticeAttempt.SECTION_CHOICES)[section],
        'has_pro_access': has_pro_access(request.user),
        'is_preview': not request.user.is_authenticated,
    })


def warning_session_key(book_number, test_number, section):
    return f'practice_warning_seen:{book_number}:{test_number}:{section}'


def practice_section(request, book_number, test_number, section):
    book = get_practice_book_or_404(book_number, request.user)
    test = get_test_or_404(test_number)
    if not user_can_access_test(request.user, book_number, test_number):
        raise Http404('Test not found')

    if section not in dict(PracticeAttempt.SECTION_CHOICES):
        raise Http404('Practice section not found')

    warning_key = warning_session_key(book_number, test_number, section)
    if request.GET.get('start') == '1':
        request.session[warning_key] = True
    elif not request.session.get(warning_key):
        return redirect('cambridge_practice:practice_start', book_number, test_number, section)

    is_preview = not request.user.is_authenticated
    attempt = UnsavedAttempt()
    groups = build_question_groups(section, attempt.answers)
    result = None

    if request.method == 'POST':
        answers = clean_submitted_answers(request.POST, field_prefix='answer_')
        if is_preview:
            return redirect('cambridge_practice:practice_section', book_number, test_number, section)

        attempt = create_attempt(request, book_number, test_number, section)
        attempt.answers = answers
        attempt.status = PracticeAttempt.STATUS_COMPLETED
        attempt.time_remaining_seconds = 0
        attempt.completed_at = timezone.now()
        attempt.save()
        create_or_update_result(attempt)
        return redirect('cambridge_practice:practice_section', book_number, test_number, section)

    template_name = 'practice_section.html'
    if (
        book_number == 11
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge11_test1_listening.html'
    elif (
        book_number == 11
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge11_test2_listening.html'
    elif (
        book_number == 11
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge11_test3_listening.html'
    elif (
        book_number == 11
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge11_test4_listening.html'
    elif (
        book_number == 12
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge12_test1_listening.html'
    elif (
        book_number == 12
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge12_test2_listening.html'
    elif (
        book_number == 12
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge12_test3_listening.html'
    elif (
        book_number == 12
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge12_test4_listening.html'
    elif (
        book_number == 13
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge13_test1_listening.html'
    elif (
        book_number == 13
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge13_test2_listening.html'
    elif (
        book_number == 13
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge13_test3_listening.html'
    elif (
        book_number == 13
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge13_test4_listening.html'
    elif (
        book_number == 14
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge14_test1_listening.html'
    elif (
        book_number == 14
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge14_test2_listening.html'
    elif (
        book_number == 14
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge14_test3_listening.html'
    elif (
        book_number == 14
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge14_test4_listening.html'
    elif (
        book_number == 15
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge15_test1_listening.html'
    elif (
        book_number == 15
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge15_test2_listening.html'
    elif (
        book_number == 15
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge15_test3_listening.html'
    elif (
        book_number == 15
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge15_test4_listening.html'
    elif (
        book_number == 16
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge16_test1_listening.html'
    elif (
        book_number == 16
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge16_test2_listening.html'
    elif (
        book_number == 16
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge16_test3_listening.html'
    elif (
        book_number == 16
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge16_test4_listening.html'
    elif (
        book_number == 17
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge17_test1_listening.html'
    elif (
        book_number == 17
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge17_test2_listening.html'
    elif (
        book_number == 17
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge17_test3_listening.html'
    elif (
        book_number == 17
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge17_test4_listening.html'
    elif (
        book_number == 18
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge18_test1_listening.html'
    elif (
        book_number == 18
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge18_test2_listening.html'
    elif (
        book_number == 18
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge18_test3_listening.html'
    elif (
        book_number == 18
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge18_test4_listening.html'
    elif (
        book_number == 19
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge19_test1_listening.html'
    elif (
        book_number == 19
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge19_test2_listening.html'
    elif (
        book_number == 19
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge19_test3_listening.html'
    elif (
        book_number == 19
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge19_test4_listening.html'
    elif (
        book_number == 20
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge20_test1_listening.html'
    elif (
        book_number == 20
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge20_test2_listening.html'
    elif (
        book_number == 20
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge20_test3_listening.html'
    elif (
        book_number == 20
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'cambridge20_test4_listening.html'
    elif (
        book_number == 11
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge11_test1_reading.html'
    elif (
        book_number == 11
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge11_test2_reading.html'
    elif (
        book_number == 11
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge11_test3_reading.html'
    elif (
        book_number == 11
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge11_test4_reading.html'
    elif (
        book_number == 12
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge12_test1_reading.html'
    elif (
        book_number == 12
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge12_test2_reading.html'
    elif (
        book_number == 12
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge12_test3_reading.html'
    elif (
        book_number == 12
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge12_test4_reading.html'
    elif (
        book_number == 13
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge13_test1_reading.html'
    elif (
        book_number == 13
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge13_test2_reading.html'
    elif (
        book_number == 13
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge13_test3_reading.html'
    elif (
        book_number == 13
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge13_test4_reading.html'
    elif (
        book_number == 14
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge14_test1_reading.html'
    elif (
        book_number == 14
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge14_test2_reading.html'
    elif (
        book_number == 14
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge14_test3_reading.html'
    elif (
        book_number == 14
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge14_test4_reading.html'
    elif (
        book_number == 15
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge15_test1_reading.html'
    elif (
        book_number == 15
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge15_test2_reading.html'
    elif (
        book_number == 15
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge15_test3_reading.html'
    elif (
        book_number == 15
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge15_test4_reading.html'
    elif (
        book_number == 16
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge16_test1_reading.html'
    elif (
        book_number == 16
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge16_test2_reading.html'
    elif (
        book_number == 16
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge16_test3_reading.html'
    elif (
        book_number == 16
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge16_test4_reading.html'
    elif (
        book_number == 17
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge17_test1_reading.html'
    elif (
        book_number == 17
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge17_test2_reading.html'
    elif (
        book_number == 17
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge17_test3_reading.html'
    elif (
        book_number == 17
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge17_test4_reading.html'
    elif (
        book_number == 18
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge18_test1_reading.html'
    elif (
        book_number == 18
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge18_test2_reading.html'
    elif (
        book_number == 18
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge18_test3_reading.html'
    elif (
        book_number == 18
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge18_test4_reading.html'
    elif (
        book_number == 19
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge19_test1_reading.html'
    elif (
        book_number == 19
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge19_test2_reading.html'
    elif (
        book_number == 19
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge19_test3_reading.html'
    elif (
        book_number == 19
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge19_test4_reading.html'
    elif (
        book_number == 20
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge20_test1_reading.html'
    elif (
        book_number == 20
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge20_test2_reading.html'
    elif (
        book_number == 20
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge20_test3_reading.html'
    elif (
        book_number == 20
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'cambridge20_test4_reading.html'

    return render(request, template_name, {
        'attempt': attempt,
        'book': book,
        'test': test,
        'section': section,
        'section_title': dict(PracticeAttempt.SECTION_CHOICES)[section],
        'question_groups': groups,
        'audio_path': f'{book_number}/audio/test{test_number}/merged.mp3',
        'duration_seconds': 3600,
        'review_seconds': 120,
        'has_pro_access': has_pro_access(request.user),
        'result': result,
        'result_details': result.details if result else {},
        'is_preview': is_preview,
    })


def save_practice_answers(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    book_number = int(payload.get('book_number', 0))
    test_number = int(payload.get('test_number', 0))
    section = payload.get('section')

    get_practice_book_or_404(book_number, request.user)
    get_test_or_404(test_number)
    if not user_can_access_test(request.user, book_number, test_number):
        raise Http404('Test not found')

    if section not in dict(PracticeAttempt.SECTION_CHOICES):
        return JsonResponse({'error': 'Invalid section'}, status=400)

    answers = payload.get('answers', {})
    if not isinstance(answers, dict):
        answers = {}

    cleaned_answers = clean_submitted_answers(answers)

    if not request.user.is_authenticated:
        answer_key = AnswerKey.objects.filter(
            book_number=book_number,
            test_number=test_number,
            section=section,
            is_verified=True,
        ).first()
        score = None
        band_score = None
        details = {}
        if answer_key and payload.get('status') == PracticeAttempt.STATUS_COMPLETED:
            score, details = grade_answers(answer_key, cleaned_answers)
            band_score = band_score_for(section, score)

        return JsonResponse({
            'ok': True,
            'preview': True,
            'status': payload.get('status', PracticeAttempt.STATUS_IN_PROGRESS),
            'score': score,
            'band_score': band_score,
            'total_questions': 40 if score is not None else None,
            'details': details,
        })

    if payload.get('status') != PracticeAttempt.STATUS_COMPLETED:
        return JsonResponse({
            'ok': True,
            'status': PracticeAttempt.STATUS_IN_PROGRESS,
            'score': None,
            'total_questions': None,
        })

    attempt = create_attempt(request, book_number, test_number, section)
    attempt.answers = cleaned_answers
    attempt.time_remaining_seconds = max(int(payload.get('time_remaining_seconds', 0)), 0)
    review_remaining = payload.get('review_remaining_seconds')
    attempt.review_remaining_seconds = (
        max(int(review_remaining), 0)
        if review_remaining is not None
        else None
    )

    if payload.get('status') == PracticeAttempt.STATUS_COMPLETED:
        attempt.status = PracticeAttempt.STATUS_COMPLETED
        attempt.completed_at = timezone.now()

    attempt.save()
    result = None
    if attempt.status == PracticeAttempt.STATUS_COMPLETED:
        result = create_or_update_result(attempt)

    return JsonResponse({
        'ok': True,
        'status': attempt.status,
        'score': result.score if result else None,
        'band_score': float(result.band_score) if result and result.band_score is not None else None,
        'total_questions': result.total_questions if result else None,
        'details': result.details if result else {},
        'updated_at': attempt.updated_at.isoformat(),
    })


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('cambridge_practice:home')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})


def sign_out(request):
    logout(request)
    return redirect('cambridge_practice:home')
