#!/usr/bin/env python
"""Check POS module status for tenants"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
django.setup()

from tenants.models import Tenant

# Check specific tenant
tenant = Tenant.objects.filter(slug='ddc').first()
if tenant:
    print(f"Tenant: {tenant.name} ({tenant.slug})")
    print(f"active_modules: {tenant.active_modules}")
    print(f"Has POS: {'pos' in tenant.active_modules}")
    print()

# Count all tenants with POS
all_tenants = Tenant.objects.all()
with_pos = sum(1 for t in all_tenants if 'pos' in t.active_modules)
print(f"Tenants with POS: {with_pos}/{all_tenants.count()}")
