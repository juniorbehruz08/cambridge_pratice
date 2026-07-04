from xml.etree import ElementTree

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.shortcuts import redirect
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json

from .forms import FeedbackForm, RegisterForm
from .models import AnswerKey, PracticeAttempt, PracticeResult
from .services import band_score_for, create_or_update_result, grade_answers


BOOKS = [
    {
        'number': 11,
        'title': 'IELTS Mock 11',
        'requires_pro': False,
    },
    {
        'number': 12,
        'title': 'IELTS Mock 12',
        'requires_pro': False,
    },
    {
        'number': 13,
        'title': 'IELTS Mock 13',
        'requires_pro': False,
    },
    {
        'number': 14,
        'title': 'IELTS Mock 14',
        'requires_pro': False,
    },
    {
        'number': 15,
        'title': 'IELTS Mock 15',
        'requires_pro': False,
    },
    {
        'number': 16,
        'title': 'IELTS Mock 16',
        'requires_pro': False,
    },
    {
        'number': 17,
        'title': 'IELTS Mock 17',
        'requires_pro': False,
    },
    {
        'number': 18,
        'title': 'IELTS Mock 18',
        'requires_pro': False,
    },
    {
        'number': 19,
        'title': 'IELTS Mock 19',
        'requires_pro': True,
    },
    {
        'number': 20,
        'title': 'IELTS Mock 20',
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
        'description': 'Continue with the second full mock practice test.',
    },
    {
        'number': 3,
        'title': 'Test 3',
        'description': 'Practice another full test and compare your timing.',
    },
    {
        'number': 4,
        'title': 'Test 4',
        'description': 'Complete the final practice test in this mock book.',
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


def public_site_url(path):
    return f"{settings.PUBLIC_SITE_URL}{path}"


def sitemap_xml(request):
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ElementTree.register_namespace('', namespace)
    urlset = ElementTree.Element(ElementTree.QName(namespace, 'urlset'))
    public_urls = [
        (reverse('cambridge_practice:home'), 'daily', '1.0'),
        (
            reverse('cambridge_practice:book_detail', args=[PREVIEW_BOOK_NUMBER]),
            'weekly',
            '0.8',
        ),
        (
            reverse(
                'cambridge_practice:test_detail',
                args=[PREVIEW_BOOK_NUMBER, PREVIEW_TEST_NUMBER],
            ),
            'weekly',
            '0.7',
        ),
    ]

    for path, change_frequency, priority in public_urls:
        url = ElementTree.SubElement(urlset, ElementTree.QName(namespace, 'url'))
        ElementTree.SubElement(url, ElementTree.QName(namespace, 'loc')).text = public_site_url(path)
        ElementTree.SubElement(url, ElementTree.QName(namespace, 'changefreq')).text = change_frequency
        ElementTree.SubElement(url, ElementTree.QName(namespace, 'priority')).text = priority

    response = HttpResponse(
        ElementTree.tostring(urlset, encoding='utf-8', xml_declaration=True),
        content_type='application/xml; charset=utf-8',
    )
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def robots_txt(request):
    rules = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /login/',
        'Disallow: /register/',
        'Disallow: /logout/',
        'Disallow: /past-results/',
        'Disallow: /practice/save/',
        'Disallow: /feedback/',
        'Disallow: /media/feedback/',
        '',
        f'Sitemap: {public_site_url(reverse("cambridge_practice:sitemap"))}',
        '',
    ]
    response = HttpResponse('\n'.join(rules), content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def custom_404(request, exception=None, unmatched_path=''):
    return render(request, '404.html', status=404)


def feedback(request):
    initial = {}
    next_url = request.GET.get('next', '').strip()
    if next_url:
        initial['page_url'] = request.build_absolute_uri(next_url)
    elif request.META.get('HTTP_REFERER'):
        initial['page_url'] = request.META['HTTP_REFERER']

    if request.method == 'POST':
        form = FeedbackForm(request.POST, request.FILES)
        if form.is_valid():
            feedback_item = form.save(commit=False)
            if request.user.is_authenticated:
                feedback_item.user = request.user
                if not feedback_item.name:
                    feedback_item.name = request.user.get_username()
                if not feedback_item.email:
                    feedback_item.email = request.user.email
            feedback_item.user_agent = request.META.get('HTTP_USER_AGENT', '')
            feedback_item.save()
            return render(request, 'feedback.html', {
                'form': FeedbackForm(),
                'submitted': True,
                'has_pro_access': has_pro_access(request.user),
            })
    else:
        form = FeedbackForm(initial=initial)

    return render(request, 'feedback.html', {
        'form': form,
        'submitted': False,
        'has_pro_access': has_pro_access(request.user),
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
    template_name = f'mock{book_number}_test{test_number}_{section}.html'
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
    section_filter = request.GET.get('section', 'all')
    range_filter = request.GET.get('range', 'all')
    valid_sections = {PracticeAttempt.SECTION_LISTENING, PracticeAttempt.SECTION_READING}
    date_ranges = {
        '7': ('Last week', 7),
        '15': ('Last 15 days', 15),
        '30': ('Last month', 30),
        '90': ('Last 3 months', 90),
        'all': ('All time', None),
    }

    if section_filter not in valid_sections and section_filter != 'all':
        section_filter = 'all'
    if range_filter not in date_ranges:
        range_filter = 'all'

    results_query = (
        PracticeResult.objects
        .select_related('attempt', 'answer_key')
        .filter(attempt__user=request.user)
    )

    if section_filter != 'all':
        results_query = results_query.filter(attempt__section=section_filter)

    days = date_ranges[range_filter][1]
    if days is not None:
        since = timezone.now() - timedelta(days=days)
        results_query = results_query.filter(attempt__completed_at__gte=since)

    results = list(results_query.order_by('-attempt__completed_at', '-created_at')[:50])
    chart_results = list(reversed(results))
    chart_sections = [
        (PracticeAttempt.SECTION_LISTENING, 'Listening'),
        (PracticeAttempt.SECTION_READING, 'Reading'),
    ]
    if section_filter != 'all':
        chart_sections = [
            (slug, label)
            for slug, label in chart_sections
            if slug == section_filter
        ]

    def build_line_series(points, max_value):
        if not points:
            return {
                'points': [],
                'polyline': '',
                'area': '',
                'latest': '-',
                'average': '-',
            }

        plot_left = 10
        plot_right = 94
        plot_top = 8
        plot_bottom = 50
        plot_height = plot_bottom - plot_top
        step = 0 if len(points) == 1 else (plot_right - plot_left) / (len(points) - 1)
        plotted_points = []

        for index, point in enumerate(points):
            ratio = 0 if max_value == 0 else min(max(point['value'] / max_value, 0), 1)
            x = 50 if len(points) == 1 else plot_left + (step * index)
            y = plot_bottom - (ratio * plot_height)
            plotted_points.append({
                **point,
                'x': f'{x:.2f}',
                'y': f'{y:.2f}',
            })

        polyline = ' '.join(f"{point['x']},{point['y']}" for point in plotted_points)
        area = (
            f"{plotted_points[0]['x']},{plot_bottom} "
            f"{polyline} "
            f"{plotted_points[-1]['x']},{plot_bottom}"
        )
        average_value = sum(point['value'] for point in points) / len(points)
        return {
            'points': plotted_points,
            'polyline': polyline,
            'area': area,
            'latest': points[-1]['display'],
            'average': f'{average_value:g}',
        }

    chart_panels = []
    for section_slug, section_label in chart_sections:
        section_results = [
            result for result in chart_results
            if result.attempt.section == section_slug
        ][-20:]

        band_points = []
        score_points = []
        for result in section_results:
            date = result.attempt.completed_at or result.created_at
            label = f'T{result.attempt.test_number} - {date.strftime("%b %d")}'
            band_value = float(result.band_score or 0)
            score_value = int(result.score or 0)
            band_points.append({
                'label': label,
                'value': band_value,
                'display': f'{band_value:g}',
            })
            score_points.append({
                'label': label,
                'value': score_value,
                'display': str(score_value),
            })

        band_series = build_line_series(band_points, 9)
        score_series = build_line_series(score_points, 40)
        chart_panels.append({
            'section': section_slug,
            'section_label': section_label,
            'band': {
                'title': f'{section_label} band score',
                'max_label': '9',
                'series': band_series,
            },
            'score': {
                'title': f'{section_label} correct answers',
                'max_label': '40',
                'series': score_series,
            },
            'count': len(section_results),
        })

    section_options = [
        ('all', 'All sections'),
        (PracticeAttempt.SECTION_LISTENING, 'Listening'),
        (PracticeAttempt.SECTION_READING, 'Reading'),
    ]
    range_options = [
        ('all', 'All time'),
        ('7', 'Last week'),
        ('15', 'Last 15 days'),
        ('30', 'Last month'),
        ('90', 'Last 3 months'),
    ]

    return render(request, 'past_results.html', {
        'results': results,
        'chart_panels': chart_panels,
        'section_options': section_options,
        'range_options': range_options,
        'selected_section': section_filter,
        'selected_range': range_filter,
        'result_count': len(results),
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
        'audio_path': f'{book_number}/audio/test{test_number}/merged.mp3',
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
        template_name = 'mock11_test1_listening.html'
    elif (
        book_number == 11
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock11_test2_listening.html'
    elif (
        book_number == 11
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock11_test3_listening.html'
    elif (
        book_number == 11
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock11_test4_listening.html'
    elif (
        book_number == 12
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock12_test1_listening.html'
    elif (
        book_number == 12
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock12_test2_listening.html'
    elif (
        book_number == 12
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock12_test3_listening.html'
    elif (
        book_number == 12
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock12_test4_listening.html'
    elif (
        book_number == 13
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock13_test1_listening.html'
    elif (
        book_number == 13
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock13_test2_listening.html'
    elif (
        book_number == 13
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock13_test3_listening.html'
    elif (
        book_number == 13
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock13_test4_listening.html'
    elif (
        book_number == 14
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock14_test1_listening.html'
    elif (
        book_number == 14
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock14_test2_listening.html'
    elif (
        book_number == 14
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock14_test3_listening.html'
    elif (
        book_number == 14
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock14_test4_listening.html'
    elif (
        book_number == 15
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock15_test1_listening.html'
    elif (
        book_number == 15
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock15_test2_listening.html'
    elif (
        book_number == 15
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock15_test3_listening.html'
    elif (
        book_number == 15
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock15_test4_listening.html'
    elif (
        book_number == 16
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock16_test1_listening.html'
    elif (
        book_number == 16
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock16_test2_listening.html'
    elif (
        book_number == 16
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock16_test3_listening.html'
    elif (
        book_number == 16
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock16_test4_listening.html'
    elif (
        book_number == 17
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock17_test1_listening.html'
    elif (
        book_number == 17
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock17_test2_listening.html'
    elif (
        book_number == 17
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock17_test3_listening.html'
    elif (
        book_number == 17
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock17_test4_listening.html'
    elif (
        book_number == 18
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock18_test1_listening.html'
    elif (
        book_number == 18
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock18_test2_listening.html'
    elif (
        book_number == 18
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock18_test3_listening.html'
    elif (
        book_number == 18
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock18_test4_listening.html'
    elif (
        book_number == 19
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock19_test1_listening.html'
    elif (
        book_number == 19
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock19_test2_listening.html'
    elif (
        book_number == 19
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock19_test3_listening.html'
    elif (
        book_number == 19
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock19_test4_listening.html'
    elif (
        book_number == 20
        and test_number == 1
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock20_test1_listening.html'
    elif (
        book_number == 20
        and test_number == 2
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock20_test2_listening.html'
    elif (
        book_number == 20
        and test_number == 3
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock20_test3_listening.html'
    elif (
        book_number == 20
        and test_number == 4
        and section == PracticeAttempt.SECTION_LISTENING
    ):
        template_name = 'mock20_test4_listening.html'
    elif (
        book_number == 11
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock11_test1_reading.html'
    elif (
        book_number == 11
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock11_test2_reading.html'
    elif (
        book_number == 11
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock11_test3_reading.html'
    elif (
        book_number == 11
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock11_test4_reading.html'
    elif (
        book_number == 12
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock12_test1_reading.html'
    elif (
        book_number == 12
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock12_test2_reading.html'
    elif (
        book_number == 12
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock12_test3_reading.html'
    elif (
        book_number == 12
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock12_test4_reading.html'
    elif (
        book_number == 13
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock13_test1_reading.html'
    elif (
        book_number == 13
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock13_test2_reading.html'
    elif (
        book_number == 13
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock13_test3_reading.html'
    elif (
        book_number == 13
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock13_test4_reading.html'
    elif (
        book_number == 14
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock14_test1_reading.html'
    elif (
        book_number == 14
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock14_test2_reading.html'
    elif (
        book_number == 14
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock14_test3_reading.html'
    elif (
        book_number == 14
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock14_test4_reading.html'
    elif (
        book_number == 15
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock15_test1_reading.html'
    elif (
        book_number == 15
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock15_test2_reading.html'
    elif (
        book_number == 15
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock15_test3_reading.html'
    elif (
        book_number == 15
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock15_test4_reading.html'
    elif (
        book_number == 16
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock16_test1_reading.html'
    elif (
        book_number == 16
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock16_test2_reading.html'
    elif (
        book_number == 16
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock16_test3_reading.html'
    elif (
        book_number == 16
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock16_test4_reading.html'
    elif (
        book_number == 17
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock17_test1_reading.html'
    elif (
        book_number == 17
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock17_test2_reading.html'
    elif (
        book_number == 17
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock17_test3_reading.html'
    elif (
        book_number == 17
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock17_test4_reading.html'
    elif (
        book_number == 18
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock18_test1_reading.html'
    elif (
        book_number == 18
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock18_test2_reading.html'
    elif (
        book_number == 18
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock18_test3_reading.html'
    elif (
        book_number == 18
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock18_test4_reading.html'
    elif (
        book_number == 19
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock19_test1_reading.html'
    elif (
        book_number == 19
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock19_test2_reading.html'
    elif (
        book_number == 19
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock19_test3_reading.html'
    elif (
        book_number == 19
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock19_test4_reading.html'
    elif (
        book_number == 20
        and test_number == 1
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock20_test1_reading.html'
    elif (
        book_number == 20
        and test_number == 2
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock20_test2_reading.html'
    elif (
        book_number == 20
        and test_number == 3
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock20_test3_reading.html'
    elif (
        book_number == 20
        and test_number == 4
        and section == PracticeAttempt.SECTION_READING
    ):
        template_name = 'mock20_test4_reading.html'

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
