from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import DiscussionMessageForm, FreeBoardCommentForm, FreeBoardPostForm
from .models import DiscussionTopic, FreeBoardComment, FreeBoardPost


def _can_edit(user, owner):
    return user.is_authenticated and (user.is_staff or user == owner)


@require_http_methods(['GET'])
def community_hub(request):
    return redirect(reverse('free_board_list'))


@require_http_methods(['GET'])
def free_board_list(request):
    query = (request.GET.get('q') or '').strip()
    sort = (request.GET.get('sort') or 'latest').strip().lower()

    posts = FreeBoardPost.objects.select_related('author').annotate(
        comment_count=Count('comments', filter=Q(comments__is_deleted=False))
    )

    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(author__username__icontains=query)
        )

    if sort == 'popular':
        posts = posts.order_by('-view_count', '-created_at')
    elif sort == 'comments':
        posts = posts.order_by('-comment_count', '-created_at')
    else:
        sort = 'latest'
        posts = posts.order_by('-is_pinned', '-created_at')

    paginator = Paginator(posts, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(
        request,
        'core/community/free_board_list.html',
        {
            'page_obj': page_obj,
            'query': query,
            'sort': sort,
        },
    )


@require_http_methods(['GET'])
def free_board_detail(request, post_id):
    post = get_object_or_404(FreeBoardPost.objects.select_related('author'), pk=post_id)

    session_key = f'free-board-viewed-{post.pk}'
    if not request.session.get(session_key):
        FreeBoardPost.objects.filter(pk=post.pk).update(view_count=F('view_count') + 1)
        post.refresh_from_db(fields=['view_count'])
        request.session[session_key] = True

    root_comments = post.comments.filter(parent__isnull=True).select_related('author').prefetch_related(
        'children__author'
    ).order_by('created_at')

    return render(
        request,
        'core/community/free_board_detail.html',
        {
            'post': post,
            'root_comments': root_comments,
            'comment_form': FreeBoardCommentForm(),
            'can_write': request.user.is_authenticated,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def free_board_create(request):
    form = FreeBoardPostForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, '게시글이 등록되었습니다.')
        return redirect(reverse('free_board_detail', args=[post.pk]))

    return render(
        request,
        'core/community/free_board_form.html',
        {
            'form': form,
            'page_title': '자유게시판 글쓰기',
            'submit_label': '등록하기',
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def free_board_edit(request, post_id):
    post = get_object_or_404(FreeBoardPost, pk=post_id)
    if not _can_edit(request.user, post.author):
        return HttpResponseForbidden('수정 권한이 없습니다.')

    form = FreeBoardPostForm(request.POST or None, instance=post)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '게시글이 수정되었습니다.')
        return redirect(reverse('free_board_detail', args=[post.pk]))

    return render(
        request,
        'core/community/free_board_form.html',
        {
            'form': form,
            'page_title': '자유게시판 글수정',
            'submit_label': '수정하기',
        },
    )


@login_required
@require_http_methods(['POST'])
def free_board_delete(request, post_id):
    post = get_object_or_404(FreeBoardPost, pk=post_id)
    if not _can_edit(request.user, post.author):
        return HttpResponseForbidden('삭제 권한이 없습니다.')

    post.delete()
    messages.info(request, '게시글이 삭제되었습니다.')
    return redirect(reverse('free_board_list'))


@login_required
@require_http_methods(['POST'])
def free_board_comment_create(request, post_id):
    post = get_object_or_404(FreeBoardPost, pk=post_id)
    form = FreeBoardCommentForm(request.POST)

    parent = None
    parent_id = (request.POST.get('parent_id') or '').strip()
    if parent_id:
        parent = get_object_or_404(FreeBoardComment, pk=parent_id, post=post)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.parent = parent
        comment.save()
        messages.success(request, '댓글이 등록되었습니다.')
    else:
        messages.error(request, '댓글 등록에 실패했습니다. 내용을 확인해주세요.')

    return redirect(f"{reverse('free_board_detail', args=[post.pk])}#comments")


@login_required
@require_http_methods(['POST'])
def free_board_comment_edit(request, comment_id):
    comment = get_object_or_404(FreeBoardComment.objects.select_related('post', 'author'), pk=comment_id)
    if not _can_edit(request.user, comment.author):
        return HttpResponseForbidden('수정 권한이 없습니다.')
    if comment.is_deleted:
        messages.error(request, '삭제된 댓글은 수정할 수 없습니다.')
        return redirect(f"{reverse('free_board_detail', args=[comment.post_id])}#comments")

    form = FreeBoardCommentForm(request.POST, instance=comment)
    if form.is_valid():
        form.save()
        messages.success(request, '댓글이 수정되었습니다.')
    else:
        messages.error(request, '댓글 수정에 실패했습니다.')

    return redirect(f"{reverse('free_board_detail', args=[comment.post_id])}#comment-{comment.pk}")


@login_required
@require_http_methods(['POST'])
def free_board_comment_delete(request, comment_id):
    comment = get_object_or_404(FreeBoardComment.objects.select_related('post', 'author'), pk=comment_id)
    if not _can_edit(request.user, comment.author):
        return HttpResponseForbidden('삭제 권한이 없습니다.')

    has_child = comment.children.filter(is_deleted=False).exists()
    if has_child:
        comment.content = ''
        comment.is_deleted = True
        comment.save(update_fields=['content', 'is_deleted', 'updated_at'])
    else:
        comment.delete()

    messages.info(request, '댓글이 삭제되었습니다.')
    return redirect(f"{reverse('free_board_detail', args=[comment.post_id])}#comments")


@login_required
@require_http_methods(['GET'])
def discussion_topic_list(request):
    topics = DiscussionTopic.objects.filter(is_active=True).annotate(
        message_count=Count('messages', filter=Q(messages__is_deleted=False))
    )

    return render(
        request,
        'core/community/discussion_list.html',
        {
            'topics': topics,
        },
    )


@login_required
@require_http_methods(['GET'])
def discussion_topic_detail(request, slug):
    topic = get_object_or_404(DiscussionTopic, slug=slug, is_active=True)
    messages_qs = topic.messages.filter(is_deleted=False).select_related('author')

    return render(
        request,
        'core/community/discussion_detail.html',
        {
            'topic': topic,
            'messages_qs': messages_qs,
            'message_form': DiscussionMessageForm(),
        },
    )


@login_required
@require_http_methods(['POST'])
def discussion_message_create(request, slug):
    topic = get_object_or_404(DiscussionTopic, slug=slug, is_active=True)

    if topic.is_locked and not request.user.is_staff:
        messages.error(request, '현재 이 토론 주제는 잠겨 있습니다.')
        return redirect(reverse('discussion_topic_detail', args=[topic.slug]))

    form = DiscussionMessageForm(request.POST)
    if form.is_valid():
        message = form.save(commit=False)
        message.topic = topic
        message.author = request.user
        message.save()
        messages.success(request, '의견이 등록되었습니다.')
    else:
        messages.error(request, '의견 등록에 실패했습니다.')

    return redirect(f"{reverse('discussion_topic_detail', args=[topic.slug])}#discussion-messages")
