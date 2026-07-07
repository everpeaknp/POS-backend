"""Resolve eSewa configuration from database settings with env fallbacks."""

from dataclasses import dataclass

from django.conf import settings as django_settings

ESEWA_SANDBOX = {
    'payment_url': 'https://rc-epay.esewa.com.np/api/epay/main/v2/form',
    'status_url': 'https://rc.esewa.com.np/api/epay/transaction/status/',
}

ESEWA_PRODUCTION = {
    'payment_url': 'https://epay.esewa.com.np/api/epay/main/v2/form',
    'status_url': 'https://esewa.com.np/api/epay/transaction/status/',
}


@dataclass(frozen=True)
class EsewaConfig:
    enabled: bool
    use_sandbox: bool
    product_code: str
    secret_key: str
    frontend_url: str
    success_url: str
    failure_url: str
    payment_url: str
    status_url: str


def get_esewa_config() -> EsewaConfig:
    from setting.models import EsewaSettings

    solo = EsewaSettings.get_solo()
    endpoints = ESEWA_SANDBOX if solo.use_sandbox else ESEWA_PRODUCTION

    product_code = solo.product_code or getattr(django_settings, 'ESEWA_PRODUCT_CODE', '')
    secret_key = solo.secret_key or getattr(django_settings, 'ESEWA_SECRET_KEY', '')
    frontend_url = (solo.frontend_url or getattr(django_settings, 'FRONTEND_URL', '')).rstrip('/')

    payment_url = (
        solo.payment_url
        or getattr(django_settings, 'ESEWA_PAYMENT_URL', '')
        or endpoints['payment_url']
    )
    status_url = (
        solo.status_url
        or getattr(django_settings, 'ESEWA_STATUS_URL', '')
        or endpoints['status_url']
    )
    success_url = solo.resolved_success_url()
    failure_url = solo.resolved_failure_url()

    enabled = solo.enabled and bool(product_code and secret_key and frontend_url and success_url and failure_url)

    return EsewaConfig(
        enabled=enabled,
        use_sandbox=solo.use_sandbox,
        product_code=product_code,
        secret_key=secret_key,
        frontend_url=frontend_url,
        success_url=success_url,
        failure_url=failure_url,
        payment_url=payment_url,
        status_url=status_url,
    )
