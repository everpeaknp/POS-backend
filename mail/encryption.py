"""Encrypt sensitive mail settings at rest using Django's SECRET_KEY."""

import base64
import hashlib

from django.conf import settings
from django.core.signing import BadSignature, Signer

_SIGNER = Signer(salt='khata-mail-settings-v1')


def encrypt_value(value: str) -> str:
    if not value:
        return ''
    return _SIGNER.sign(value)


def decrypt_value(value: str) -> str:
    if not value:
        return ''
    try:
        return _SIGNER.unsign(value)
    except BadSignature:
        return ''
