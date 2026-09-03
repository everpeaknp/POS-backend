#!/usr/bin/env python
"""Fix hardware tenant subscriptions to enable inventory module"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
django.setup()

from tenants.models import Tenant
from billing.models import Subscription, SubscriptionPlan
from django.db import connection

# Get the free plan
free_plan = SubscriptionPlan.objects.get(code='free')
print(f"Free plan modules: {free_plan.modules}")

# Find all hardware tenants
hardware_tenants = Tenant.objects.filter(account_type='hardware')
print(f"\nFound {hardware_tenants.count()} hardware tenants:")

for tenant in hardware_tenants:
    print(f"\nProcessing {tenant.name} (ID: {tenant.id}):")
    
    # Check for existing subscription using raw query to bypass any tenant filtering
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, plan_code, status FROM billing_subscriptions WHERE tenant_id = %s",
            [tenant.id]
        )
        existing = cursor.fetchone()
    
    if existing:
        sub_id, plan_code, status = existing
        print(f"  Found existing subscription (ID: {sub_id}): Plan={plan_code}, Status={status}")
        
        # Update to free plan if needed
        if plan_code != 'free':
            Subscription.objects.filter(id=sub_id).update(plan_code='free', status='active')
            print(f"  Updated to free plan")
        else:
            print(f"  Already on free plan")
    else:
        # Create new subscription
        try:
            sub = Subscription.objects.create(
                tenant=tenant,
                plan_code='free',
                status='active'
            )
            print(f"  Created new subscription (ID: {sub.id})")
        except Exception as e:
            print(f"  Error creating subscription: {e}")

print("\n✓ Done!")
