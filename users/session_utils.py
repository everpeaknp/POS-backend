from rest_framework_simplejwt.tokens import RefreshToken

from .session_models import UserSession


def get_client_ip(request) -> str:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def parse_device(user_agent: str) -> str:
    ua = user_agent or ''

    if 'Edg' in ua:
        browser = 'Edge'
    elif 'Chrome' in ua:
        browser = 'Chrome'
    elif 'Firefox' in ua:
        browser = 'Firefox'
    elif 'Safari' in ua:
        browser = 'Safari'
    elif 'Opera' in ua or 'OPR' in ua:
        browser = 'Opera'
    else:
        browser = 'Browser'

    if 'Windows NT 10' in ua:
        os_name = 'Windows 10'
    elif 'Windows NT 11' in ua:
        os_name = 'Windows 11'
    elif 'Windows' in ua:
        os_name = 'Windows'
    elif 'Mac OS X' in ua:
        os_name = 'macOS'
    elif 'Android' in ua:
        os_name = 'Android'
    elif 'iPhone' in ua or 'iPad' in ua:
        os_name = 'iOS'
    elif 'Linux' in ua:
        os_name = 'Linux'
    else:
        os_name = 'Unknown OS'

    return f'{browser} on {os_name}'


def resolve_location(ip_address: str) -> str:
    if ip_address in ('127.0.0.1', '::1') or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
        return 'Local Network'
    return 'Remote Location'


def get_refresh_jti(refresh_token: str) -> str:
    token = RefreshToken(refresh_token)
    return str(token['jti'])


def record_user_session(user, request, refresh_token: str) -> UserSession:
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip_address = get_client_ip(request)
    refresh_jti = get_refresh_jti(refresh_token)

    session, _ = UserSession.objects.update_or_create(
        refresh_jti=refresh_jti,
        defaults={
            'user': user,
            'device': parse_device(user_agent),
            'ip_address': ip_address,
            'location': resolve_location(ip_address),
            'user_agent': user_agent,
            'is_revoked': False,
        },
    )
    return session


def touch_user_session(refresh_jti: str) -> None:
    from django.utils import timezone
    UserSession.objects.filter(refresh_jti=refresh_jti, is_revoked=False).update(last_active=timezone.now())


def revoke_user_session(session: UserSession) -> None:
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

    outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti).first()
    if outstanding and not BlacklistedToken.objects.filter(token=outstanding).exists():
        BlacklistedToken.objects.create(token=outstanding)

    session.is_revoked = True
    session.save(update_fields=['is_revoked'])
