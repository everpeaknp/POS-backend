"""
Management command to seed inventory master data (categories and units) for all tenants.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from tenants.models import Tenant
from inventory.models import Category, UnitOfMeasure


class Command(BaseCommand):
    help = 'Seed inventory master data (categories and units) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Seed data for a specific tenant ID',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        
        if tenant_id:
            tenants = Tenant.objects.filter(id=tenant_id)
            if not tenants.exists():
                self.stdout.write(self.style.ERROR(f'Tenant with ID {tenant_id} not found'))
                return
        else:
            tenants = Tenant.objects.all()

        for tenant in tenants:
            self.stdout.write(f'\nSeeding data for tenant: {tenant.name}')
            self.seed_categories(tenant)
            self.seed_units(tenant)

    def seed_categories(self, tenant):
        """Seed product categories for a tenant"""
        categories_data = [
            {'name': 'Construction Materials', 'parent': None, 'description': 'Building and construction materials'},
            {'name': 'Cement', 'parent': 'Construction Materials', 'description': 'Cement and binding materials'},
            {'name': 'Steel', 'parent': 'Construction Materials', 'description': 'Steel and metal products'},
            {'name': 'Aggregates', 'parent': 'Construction Materials', 'description': 'Sand, gravel, and aggregates'},
            {'name': 'Bricks & Blocks', 'parent': 'Construction Materials', 'description': 'Bricks, blocks, and masonry'},
            {'name': 'Tools & Equipment', 'parent': None, 'description': 'Tools and equipment'},
            {'name': 'Hand Tools', 'parent': 'Tools & Equipment', 'description': 'Hand tools and implements'},
            {'name': 'Power Tools', 'parent': 'Tools & Equipment', 'description': 'Power tools and machinery'},
            {'name': 'Safety Equipment', 'parent': 'Tools & Equipment', 'description': 'Safety gear and equipment'},
            {'name': 'Electrical', 'parent': None, 'description': 'Electrical materials and supplies'},
            {'name': 'Wiring & Cables', 'parent': 'Electrical', 'description': 'Electrical wiring and cables'},
            {'name': 'Switches & Outlets', 'parent': 'Electrical', 'description': 'Electrical switches and outlets'},
            {'name': 'Plumbing', 'parent': None, 'description': 'Plumbing materials and supplies'},
            {'name': 'Pipes & Fittings', 'parent': 'Plumbing', 'description': 'Pipes and plumbing fittings'},
            {'name': 'Fixtures', 'parent': 'Plumbing', 'description': 'Plumbing fixtures and accessories'},
        ]

        parent_map = {}
        created_count = 0

        for cat_data in categories_data:
            parent_name = cat_data['parent']
            parent_obj = None

            if parent_name:
                if parent_name in parent_map:
                    parent_obj = parent_map[parent_name]
                else:
                    parent_obj = Category.objects.filter(
                        tenant=tenant,
                        name=parent_name
                    ).first()

            # Check if category already exists
            existing = Category.objects.filter(
                tenant=tenant,
                name=cat_data['name'],
                parent=parent_obj
            ).first()

            if not existing:
                category = Category.objects.create(
                    tenant=tenant,
                    name=cat_data['name'],
                    parent=parent_obj,
                    description=cat_data['description']
                )
                parent_map[cat_data['name']] = category
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created category: {cat_data["name"]}')
                )
            else:
                parent_map[cat_data['name']] = existing

        self.stdout.write(
            self.style.SUCCESS(f'Categories: {created_count} created')
        )

    def seed_units(self, tenant):
        """Seed units of measure for a tenant"""
        units_data = [
            # Count
            {'name': 'Piece', 'abbreviation': 'pc', 'type': 'count'},
            {'name': 'Dozen', 'abbreviation': 'dz', 'type': 'count'},
            {'name': 'Box', 'abbreviation': 'box', 'type': 'count'},
            {'name': 'Bundle', 'abbreviation': 'bnd', 'type': 'count'},
            {'name': 'Set', 'abbreviation': 'set', 'type': 'count'},
            
            # Weight
            {'name': 'Kilogram', 'abbreviation': 'kg', 'type': 'weight'},
            {'name': 'Gram', 'abbreviation': 'g', 'type': 'weight'},
            {'name': 'Metric Ton', 'abbreviation': 'MT', 'type': 'weight'},
            {'name': 'Pound', 'abbreviation': 'lb', 'type': 'weight'},
            
            # Length
            {'name': 'Meter', 'abbreviation': 'm', 'type': 'length'},
            {'name': 'Centimeter', 'abbreviation': 'cm', 'type': 'length'},
            {'name': 'Millimeter', 'abbreviation': 'mm', 'type': 'length'},
            {'name': 'Foot', 'abbreviation': 'ft', 'type': 'length'},
            {'name': 'Inch', 'abbreviation': 'in', 'type': 'length'},
            
            # Volume
            {'name': 'Liter', 'abbreviation': 'L', 'type': 'volume'},
            {'name': 'Milliliter', 'abbreviation': 'ml', 'type': 'volume'},
            {'name': 'Cubic Meter', 'abbreviation': 'm³', 'type': 'volume'},
            {'name': 'Gallon', 'abbreviation': 'gal', 'type': 'volume'},
            
            # Area
            {'name': 'Square Meter', 'abbreviation': 'm²', 'type': 'area'},
            {'name': 'Square Foot', 'abbreviation': 'ft²', 'type': 'area'},
            {'name': 'Square Centimeter', 'abbreviation': 'cm²', 'type': 'area'},
        ]

        created_count = 0

        for unit_data in units_data:
            existing = UnitOfMeasure.objects.filter(
                tenant=tenant,
                name=unit_data['name']
            ).first()

            if not existing:
                UnitOfMeasure.objects.create(
                    tenant=tenant,
                    name=unit_data['name'],
                    abbreviation=unit_data['abbreviation'],
                    type=unit_data['type']
                )
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created unit: {unit_data["name"]} ({unit_data["abbreviation"]})')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Units: {created_count} created')
        )
