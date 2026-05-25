from django.contrib import admin

from .models import AnswerKey, PracticeAttempt, PracticeResult, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_pro', 'created_at')
    list_filter = ('is_pro',)
    search_fields = ('user__username', 'user__email')


@admin.register(PracticeAttempt)
class PracticeAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'session_key',
        'book_number',
        'test_number',
        'section',
        'status',
        'updated_at',
    )
    list_filter = ('book_number', 'test_number', 'section', 'status')
    search_fields = ('user__username', 'session_key')


@admin.register(AnswerKey)
class AnswerKeyAdmin(admin.ModelAdmin):
    list_display = (
        'book_number',
        'test_number',
        'section',
        'is_verified',
        'updated_at',
    )
    list_filter = ('book_number', 'test_number', 'section', 'is_verified')
    search_fields = ('source', 'notes')


@admin.register(PracticeResult)
class PracticeResultAdmin(admin.ModelAdmin):
    list_display = (
        'attempt',
        'answer_key',
        'score',
        'band_score',
        'total_questions',
        'updated_at',
    )
    list_filter = (
        'attempt__book_number',
        'attempt__test_number',
        'attempt__section',
        'score',
        'band_score',
    )
    search_fields = ('attempt__user__username', 'attempt__session_key')
