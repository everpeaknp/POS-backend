#!/usr/bin/env python
"""Update subscription status to active"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
django.setup()

from django.db import connection

# Update using raw SQL to bypass tenant filtering
with connection.cursor() as cursor:
    cursor.execute(
        "UPDATE billing_subscriptions SET status = 'active' WHERE id = %s",
        [51]
    )
    print(f"✓ Updated subscription 51 to active status")
    print(f"  Rows affected: {cursor.rowcount}")
