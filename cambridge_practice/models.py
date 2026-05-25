from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    is_pro = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} profile'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


class PracticeAttempt(models.Model):
    SECTION_LISTENING = 'listening'
    SECTION_READING = 'reading'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'

    SECTION_CHOICES = [
        (SECTION_LISTENING, 'Listening'),
        (SECTION_READING, 'Reading'),
    ]
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='practice_attempts',
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40, blank=True)
    book_number = models.PositiveSmallIntegerField()
    test_number = models.PositiveSmallIntegerField()
    section = models.CharField(max_length=20, choices=SECTION_CHOICES)
    answers = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
    )
    time_remaining_seconds = models.PositiveIntegerField(default=3600)
    review_remaining_seconds = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at',)

    def __str__(self):
        owner = self.user.username if self.user else self.session_key
        return f'{owner} - Cambridge {self.book_number} Test {self.test_number} {self.section}'


class AnswerKey(models.Model):
    book_number = models.PositiveSmallIntegerField()
    test_number = models.PositiveSmallIntegerField()
    section = models.CharField(max_length=20, choices=PracticeAttempt.SECTION_CHOICES)
    answers = models.JSONField(default=dict, blank=True)
    scoring_rules = models.JSONField(default=dict, blank=True)
    is_verified = models.BooleanField(default=False)
    source = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('book_number', 'test_number', 'section'),
                name='unique_answer_key_for_test_section',
            )
        ]
        ordering = ('book_number', 'test_number', 'section')

    def __str__(self):
        return f'Cambridge {self.book_number} Test {self.test_number} {self.get_section_display()}'


class PracticeResult(models.Model):
    attempt = models.OneToOneField(
        PracticeAttempt,
        on_delete=models.CASCADE,
        related_name='result',
    )
    answer_key = models.ForeignKey(
        AnswerKey,
        on_delete=models.SET_NULL,
        related_name='results',
        null=True,
        blank=True,
    )
    score = models.PositiveSmallIntegerField(default=0)
    band_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    total_questions = models.PositiveSmallIntegerField(default=40)
    submitted_answers = models.JSONField(default=dict, blank=True)
    correct_answers = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at',)

    def __str__(self):
        return f'{self.attempt} - {self.score}/{self.total_questions}'
