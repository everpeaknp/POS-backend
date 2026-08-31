#!/usr/bin/env python
"""Enable POS module for all tenants"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
django.setup()

from tenants.models import Tenant

tenants = Tenant.objects.all()
updated = 0

for tenant in tenants:
    if 'pos' not in tenant.active_modules:
        tenant.active_modules.append('pos')
        tenant.save()
        updated += 1
        print(f"✓ Enabled POS for: {tenant.name} ({tenant.slug})")

print(f"\n✓ Updated {updated} tenants. Total with POS: {Tenant.objects.filter(active_modules__contains=['pos']).count()}/{tenants.count()}")
