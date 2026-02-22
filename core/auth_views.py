import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import SignUpForm
from .models import SocialAccount

GOOGLE_AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_ENDPOINT = 'https://openidconnect.googleapis.com/v1/userinfo'


def _safe_next_url(request, default):
    target = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return default


def _google_redirect_uri(request):
    explicit = (getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '') or '').strip()
    if explicit:
        return explicit
    return request.build_absolute_uri(reverse('google_callback'))


def _build_unique_username(seed):
    user_model = get_user_model()
    username_field = user_model._meta.get_field(user_model.USERNAME_FIELD)
    max_length = getattr(username_field, 'max_length', 150)

    base = ''.join(ch for ch in seed.lower() if ch.isalnum() or ch in ('_', '-'))
    base = (base or 'googleuser')[:max_length]

    candidate = base
    seq = 1
    while user_model.objects.filter(**{user_model.USERNAME_FIELD: candidate}).exists():
        suffix = f"-{seq}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        seq += 1
    return candidate


def _google_configured():
    client_id = (getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or '').strip()
    client_secret = (getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or '').strip()
    return bool(client_id and client_secret)


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request, reverse('home')))

    form = AuthenticationForm(request, data=request.POST or None)
    next_url = _safe_next_url(request, reverse('home'))

    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, '로그인되었습니다.')
        return redirect(next_url)

    return render(
        request,
        'core/auth/login.html',
        {
            'form': form,
            'next': next_url,
            'google_login_enabled': _google_configured(),
        },
    )


@require_http_methods(['GET', 'POST'])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect(reverse('home'))

    form = SignUpForm(request.POST or None)
    next_url = _safe_next_url(request, reverse('home'))

    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, '회원가입이 완료되었습니다.')
        return redirect(next_url)

    return render(
        request,
        'core/auth/signup.html',
        {
            'form': form,
            'next': next_url,
            'google_login_enabled': _google_configured(),
        },
    )


@require_http_methods(['POST'])
def logout_view(request):
    logout(request)
    messages.info(request, '로그아웃되었습니다.')
    return redirect(reverse('home'))


@require_http_methods(['GET'])
def google_login_start(request):
    if not _google_configured():
        messages.error(request, 'Google 로그인이 아직 설정되지 않았습니다.')
        return redirect(reverse('login'))

    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '').strip()
    redirect_uri = _google_redirect_uri(request)
    state = secrets.token_urlsafe(24)

    request.session['google_oauth_state'] = state
    request.session['google_oauth_next'] = _safe_next_url(request, reverse('home'))

    params = {
        'client_id': client_id,
        'response_type': 'code',
        'scope': 'openid email profile',
        'redirect_uri': redirect_uri,
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}")


@require_http_methods(['GET'])
def google_callback(request):
    if not _google_configured():
        messages.error(request, 'Google 로그인이 아직 설정되지 않았습니다.')
        return redirect(reverse('login'))

    expected_state = request.session.pop('google_oauth_state', '')
    next_url = request.session.pop('google_oauth_next', reverse('home'))
    state = (request.GET.get('state') or '').strip()

    if not expected_state or expected_state != state:
        messages.error(request, 'Google 인증 상태값 검증에 실패했습니다.')
        return redirect(reverse('login'))

    if request.GET.get('error'):
        messages.error(request, 'Google 로그인 과정이 취소되었거나 실패했습니다.')
        return redirect(reverse('login'))

    code = (request.GET.get('code') or '').strip()
    if not code:
        messages.error(request, 'Google 인증 코드가 없습니다.')
        return redirect(reverse('login'))

    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '').strip()
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
    redirect_uri = _google_redirect_uri(request)
    timeout = int(getattr(settings, 'GOOGLE_OAUTH_TIMEOUT', 8))

    try:
        token_response = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
            timeout=timeout,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

        access_token = token_payload.get('access_token')
        if not access_token:
            raise ValueError('access_token missing')

        userinfo_response = requests.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=timeout,
        )
        userinfo_response.raise_for_status()
        profile = userinfo_response.json()
    except Exception:
        messages.error(request, 'Google 로그인 중 통신 오류가 발생했습니다.')
        return redirect(reverse('login'))

    provider_user_id = (profile.get('sub') or '').strip()
    email = (profile.get('email') or '').strip().lower()
    if not provider_user_id or not email:
        messages.error(request, 'Google 계정 정보 확인에 실패했습니다.')
        return redirect(reverse('login'))

    social = SocialAccount.objects.select_related('user').filter(
        provider=SocialAccount.PROVIDER_GOOGLE,
        provider_user_id=provider_user_id,
    ).first()

    if social:
        user = social.user
    else:
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=email).first()

        if user is None:
            seed = email.split('@')[0] or 'googleuser'
            username = _build_unique_username(seed)
            with transaction.atomic():
                user = user_model.objects.create_user(
                    username=username,
                    email=email,
                )
                SocialAccount.objects.get_or_create(
                    provider=SocialAccount.PROVIDER_GOOGLE,
                    provider_user_id=provider_user_id,
                    defaults={'user': user, 'email': email},
                )
        else:
            try:
                social, created = SocialAccount.objects.get_or_create(
                    provider=SocialAccount.PROVIDER_GOOGLE,
                    provider_user_id=provider_user_id,
                    defaults={'user': user, 'email': email},
                )
            except IntegrityError:
                social = SocialAccount.objects.select_related('user').get(
                    provider=SocialAccount.PROVIDER_GOOGLE,
                    provider_user_id=provider_user_id,
                )
                created = False

            if not created and social.user_id != user.id:
                messages.error(request, '이미 다른 계정에 연결된 Google 계정입니다.')
                return redirect(reverse('login'))

    login(request, user)
    messages.success(request, 'Google 계정으로 로그인되었습니다.')

    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse('home')
    return redirect(next_url)
