"""eSewa ePay v2 helpers for subscription billing."""

import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from urllib.parse import urlencode

import requests

from billing.esewa_config import get_esewa_config


def _format_amount(amount) -> str:
    return f'{Decimal(str(amount)):.2f}'


def generate_signature(total_amount: str, transaction_uuid: str, product_code: str, secret_key: str) -> str:
    data = f'total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}'
    digest = hmac.new(
        secret_key.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode('utf-8')


def verify_callback_signature(payload: dict, secret_key: str) -> bool:
    signed_field_names = payload.get('signed_field_names', '')
    if not signed_field_names:
        return False
    parts = [f'{field}={payload[field]}' for field in signed_field_names.split(',') if field in payload]
    data = ','.join(parts)
    expected = hmac.new(
        secret_key.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.b64encode(expected).decode('utf-8')
    return expected_b64 == payload.get('signature')


def decode_callback_data(encoded_data: str) -> dict:
    decoded = base64.b64decode(encoded_data)
    return json.loads(decoded)


def new_transaction_uuid(tenant_id: int) -> str:
    return f'KHATA-{tenant_id}-{uuid.uuid4().hex[:12]}'


def build_payment_form(plan_price: Decimal, transaction_uuid: str, plan_name: str) -> dict:
    config = get_esewa_config()
    if not config.enabled:
        raise ValueError('eSewa integration is disabled or not configured')

    amount = _format_amount(plan_price)
    tax_amount = '0'
    service_charge = '0'
    delivery_charge = '0'
    total_amount = amount

    signature = generate_signature(
        total_amount,
        transaction_uuid,
        config.product_code,
        config.secret_key,
    )

    success_url = config.success_url
    failure_url = config.failure_url

    return {
        'action_url': config.payment_url,
        'method': 'POST',
        'fields': {
            'amount': amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'transaction_uuid': transaction_uuid,
            'product_code': config.product_code,
            'product_service_charge': service_charge,
            'product_delivery_charge': delivery_charge,
            'success_url': success_url,
            'failure_url': failure_url,
            'signed_field_names': 'total_amount,transaction_uuid,product_code',
            'signature': signature,
        },
        'transaction_uuid': transaction_uuid,
        'total_amount': total_amount,
        'plan_name': plan_name,
    }


def check_transaction_status(transaction_uuid: str, total_amount: str) -> dict:
    config = get_esewa_config()
    params = urlencode({
        'product_code': config.product_code,
        'total_amount': total_amount,
        'transaction_uuid': transaction_uuid,
    })
    url = f'{config.status_url}?{params}'
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()
