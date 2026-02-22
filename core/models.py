from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


def _unique_slug_for_topic(title, current_pk=None):
    base_slug = slugify(title, allow_unicode=True)[:120] or 'discussion-topic'
    slug = base_slug
    suffix = 2

    qs = DiscussionTopic.objects.all()
    if current_pk:
        qs = qs.exclude(pk=current_pk)

    while qs.filter(slug=slug).exists():
        suffix_str = str(suffix)
        trimmed = base_slug[: max(1, 120 - len(suffix_str) - 1)]
        slug = f"{trimmed}-{suffix_str}"
        suffix += 1

    return slug


class GameRecord(models.Model):
    GAME_CHOICES = [
        ('2048', '2048'),
        ('wordle', 'Wordle'),
        ('reaction', 'Reaction Speed'),
        ('kkomantle_challenge', 'Kkomantle Challenge'),
    ]

    game_type = models.CharField(max_length=20, choices=GAME_CHOICES, default='2048')
    player_name = models.CharField(max_length=10)
    score = models.IntegerField()  # 2048은 점수, 반응속도는 ms
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-score', '-created_at']  # 기본은 점수 높은 순

    def __str__(self):
        return f"{self.game_type} - {self.player_name}: {self.score}"


class KkomantleDailySnapshot(models.Model):
    date = models.DateField(unique=True, db_index=True)
    answer = models.CharField(max_length=50)
    top_words = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"kkomantle:{self.date} ({self.answer})"


class SocialAccount(models.Model):
    PROVIDER_GOOGLE = 'google'
    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE, 'Google'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_accounts')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'provider_user_id'],
                name='unique_social_provider_user',
            )
        ]
        indexes = [
            models.Index(fields=['provider', 'email']),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or '').strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.provider}:{self.provider_user_id} -> {self.user_id}"


class FreeBoardPost(models.Model):
    title = models.CharField(max_length=120)
    content = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='free_board_posts')
    view_count = models.PositiveIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['-view_count']),
        ]

    def __str__(self):
        return f"{self.title} ({self.author_id})"


class FreeBoardComment(models.Model):
    post = models.ForeignKey(FreeBoardPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='free_board_comments')
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='children',
    )
    content = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
        ]

    def clean(self):
        if self.parent and self.parent.post_id != self.post_id:
            raise ValidationError('답글의 원본 댓글과 게시글이 일치하지 않습니다.')
        if self.parent and self.parent.parent_id:
            raise ValidationError('대댓글까지만 작성할 수 있습니다.')

    @property
    def display_content(self):
        if self.is_deleted:
            return '삭제된 댓글입니다.'
        return self.content

    def __str__(self):
        return f"comment:{self.pk} post:{self.post_id}"


class DiscussionTopic(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True, blank=True, allow_unicode=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='discussion_topics_created',
    )
    is_active = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug_for_topic(self.title, current_pk=self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class DiscussionMessage(models.Model):
    topic = models.ForeignKey(DiscussionTopic, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discussion_messages')
    content = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['topic', 'created_at']),
        ]

    @property
    def display_content(self):
        if self.is_deleted:
            return '삭제된 메시지입니다.'
        return self.content

    def __str__(self):
        return f"topic:{self.topic_id} msg:{self.pk}"
