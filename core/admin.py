from django.contrib import admin

from .models import (
    DiscussionMessage,
    DiscussionTopic,
    FreeBoardComment,
    FreeBoardPost,
    GameRecord,
    KkomantleDailySnapshot,
    SocialAccount,
)


@admin.register(GameRecord)
class GameRecordAdmin(admin.ModelAdmin):
    list_display = ('game_type', 'player_name', 'score', 'created_at')
    list_filter = ('game_type',)
    search_fields = ('player_name',)


@admin.register(KkomantleDailySnapshot)
class KkomantleDailySnapshotAdmin(admin.ModelAdmin):
    list_display = ('date', 'answer', 'created_at')
    search_fields = ('answer',)
    ordering = ('-date',)


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('provider', 'provider_user_id', 'user', 'email', 'created_at')
    list_filter = ('provider',)
    search_fields = ('provider_user_id', 'email', 'user__username')


@admin.register(FreeBoardPost)
class FreeBoardPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_pinned', 'view_count', 'created_at')
    list_filter = ('is_pinned', 'created_at')
    search_fields = ('title', 'content', 'author__username')
    ordering = ('-is_pinned', '-created_at')


@admin.register(FreeBoardComment)
class FreeBoardCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'is_deleted', 'created_at')
    list_filter = ('is_deleted', 'created_at')
    search_fields = ('content', 'author__username', 'post__title')


class DiscussionMessageInline(admin.TabularInline):
    model = DiscussionMessage
    extra = 0
    fields = ('author', 'content', 'is_deleted', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(DiscussionTopic)
class DiscussionTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'is_locked', 'is_pinned', 'created_at')
    list_filter = ('is_active', 'is_locked', 'is_pinned')
    search_fields = ('title', 'description')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [DiscussionMessageInline]


@admin.register(DiscussionMessage)
class DiscussionMessageAdmin(admin.ModelAdmin):
    list_display = ('topic', 'author', 'is_deleted', 'created_at')
    list_filter = ('is_deleted', 'created_at')
    search_fields = ('content', 'author__username', 'topic__title')
