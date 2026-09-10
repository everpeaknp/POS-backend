"""Google OAuth sign-in using ID tokens from Google Identity Services."""

import requests as http_requests
from django.contrib.auth import get_user_model
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import serializers

from setting.models import GoogleOAuthSettings

User = get_user_model()


def get_google_oauth_config():
    settings = GoogleOAuthSettings.get_solo()
    return {
        'enabled': bool(settings.enabled and settings.client_id),
        'client_id': settings.client_id or '',
    }


def exchange_code_for_id_token(code: str, client_id: str, client_secret: str) -> dict:
    """
    Exchange authorization code for tokens using Google's token endpoint.
    Returns the ID token claims after verification.
    """
    token_endpoint = 'https://oauth2.googleapis.com/token'
    
    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': 'postmessage',  # For popup flow
        'grant_type': 'authorization_code',
    }
    
    try:
        response = http_requests.post(token_endpoint, data=token_data, timeout=10)
        response.raise_for_status()
        tokens = response.json()
    except http_requests.RequestException as exc:
        raise serializers.ValidationError({
            'detail': f'Failed to exchange code for tokens: {exc}'
        }) from exc
    
    if 'id_token' not in tokens:
        raise serializers.ValidationError({
            'detail': 'No ID token received from Google'
        })
    
    # Verify the ID token
    try:
        idinfo = id_token.verify_oauth2_token(
            tokens['id_token'],
            google_requests.Request(),
            client_id,
        )
    except ValueError as exc:
        raise serializers.ValidationError({
            'detail': f'Invalid ID token: {exc}'
        }) from exc
    
    if idinfo.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise serializers.ValidationError({'detail': 'Invalid Google token issuer.'})
    
    return idinfo


def verify_google_id_token(token: str) -> dict:
    config = get_google_oauth_config()
    if not config['enabled']:
        raise serializers.ValidationError({'detail': 'Google sign-in is not enabled.'})

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            config['client_id'],
        )
    except ValueError as exc:
        raise serializers.ValidationError({'detail': f'Invalid Google token: {exc}'}) from exc

    if idinfo.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise serializers.ValidationError({'detail': 'Invalid Google token issuer.'})

    return idinfo


def _unique_username(base: str) -> str:
    username = base or 'user'
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f'{base}{counter}'
        counter += 1
    return username


def authenticate_or_create_google_user(idinfo: dict) -> User:
    google_id = idinfo.get('sub')
    email = (idinfo.get('email') or '').lower().strip()
    email_verified = idinfo.get('email_verified', False)

    if not google_id:
        raise serializers.ValidationError({'detail': 'Google account ID missing from token.'})
    if not email:
        raise serializers.ValidationError({'detail': 'Google account email missing from token.'})
    if not email_verified:
        raise serializers.ValidationError({'detail': 'Google email address is not verified.'})

    user = User.objects.filter(google_id=google_id).first()
    if user:
        if not user.is_active:
            raise serializers.ValidationError({'detail': 'This account has been deactivated.'})
        return user

    user = User.objects.filter(email__iexact=email).first()
    if user:
        if not user.is_active:
            raise serializers.ValidationError({'detail': 'This account has been deactivated.'})
        if user.google_id and user.google_id != google_id:
            raise serializers.ValidationError({
                'detail': 'This email is linked to a different Google account.',
            })
        user.google_id = google_id
        if not user.first_name and idinfo.get('given_name'):
            user.first_name = idinfo['given_name']
        if not user.last_name and idinfo.get('family_name'):
            user.last_name = idinfo['family_name']
        user.save(update_fields=['google_id', 'first_name', 'last_name'])
        return user

    first_name = idinfo.get('given_name', '')
    last_name = idinfo.get('family_name', '')
    username = _unique_username(email.split('@')[0] if email else 'user')

    user = User.objects.create(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        google_id=google_id,
        tenant=None,
        role='viewer',
        phone='',
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])

    try:
        from tenants.invitation_models import claim_pending_invitations_for_user
        claim_pending_invitations_for_user(user)
    except Exception:
        pass

    try:
        from mail.services import dispatch_welcome_email
        dispatch_welcome_email(user)
    except Exception:
        pass

    return user
