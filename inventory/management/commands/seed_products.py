"""
Django management command to seed random products for testing
Usage: python manage.py seed_products --workspace=ddc --count=50
"""
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from tenants.models import Tenant
from inventory.models import Product, Category, UnitOfMeasure, Warehouse, Stock


class Command(BaseCommand):
    help = 'Seeds random products for a given workspace'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace',
            type=str,
            required=True,
            help='Workspace name (e.g., ddc)'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=50,
            help='Number of products to create (default: 50)'
        )

    def handle(self, *args, **options):
        workspace_name = options['workspace']
        count = options['count']

        try:
            tenant = Tenant.objects.get(workspace_name=workspace_name)
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Workspace "{workspace_name}" not found!')
            )
            return

        self.stdout.write(f'Seeding {count} products for workspace: {workspace_name} ({tenant.name})')
        
        with transaction.atomic():
            # Create or get units of measure
            units = self._create_units(tenant)
            
            # Create or get categories
            categories = self._create_categories(tenant)
            
            # Create or get warehouse
            warehouse = self._create_warehouse(tenant)
            
            # Create products
            products_created = self._create_products(tenant, categories, units, warehouse, count)
            
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {products_created} products!')
        )

    def _create_units(self, tenant):
        """Create common units of measure"""
        units_data = [
            {'name': 'Piece', 'abbreviation': 'pcs', 'type': 'count'},
            {'name': 'Kilogram', 'abbreviation': 'kg', 'type': 'weight'},
            {'name': 'Litre', 'abbreviation': 'L', 'type': 'volume'},
            {'name': 'Meter', 'abbreviation': 'm', 'type': 'length'},
            {'name': 'Box', 'abbreviation': 'box', 'type': 'count'},
            {'name': 'Pack', 'abbreviation': 'pack', 'type': 'count'},
            {'name': 'Bag', 'abbreviation': 'bag', 'type': 'count'},
            {'name': 'Dozen', 'abbreviation': 'doz', 'type': 'count'},
        ]
        
        units = []
        for data in units_data:
            unit, created = UnitOfMeasure.objects.get_or_create(
                tenant=tenant,
                abbreviation=data['abbreviation'],
                defaults={
                    'name': data['name'],
                    'type': data['type']
                }
            )
            units.append(unit)
            if created:
                self.stdout.write(f'  Created unit: {unit.name}')
        
        return units

    def _create_categories(self, tenant):
        """Create product categories"""
        categories_data = [
            'Electronics',
            'Groceries',
            'Hardware',
            'Stationery',
            'Beverages',
            'Snacks',
            'Personal Care',
            'Household',
            'Sports & Fitness',
            'Books & Media',
        ]
        
        categories = []
        for name in categories_data:
            category, created = Category.objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={'description': f'{name} products'}
            )
            categories.append(category)
            if created:
                self.stdout.write(f'  Created category: {category.name}')
        
        return categories

    def _create_warehouse(self, tenant):
        """Create or get main warehouse"""
        warehouse, created = Warehouse.objects.get_or_create(
            tenant=tenant,
            name='Main Warehouse',
            defaults={
                'location': 'Main Store',
                'is_active': True
            }
        )
        if created:
            self.stdout.write(f'  Created warehouse: {warehouse.name}')
        return warehouse

    def _create_products(self, tenant, categories, units, warehouse, count):
        """Create random products"""
        # Sample product templates
        product_templates = [
            # Electronics
            {'names': ['LED TV', 'Smart TV', 'Android TV', 'Gaming Monitor', 'Laptop'], 'category': 'Electronics', 'price_range': (15000, 85000)},
            {'names': ['Wireless Mouse', 'Gaming Keyboard', 'USB Cable', 'Phone Charger', 'Power Bank'], 'category': 'Electronics', 'price_range': (200, 3500)},
            {'names': ['Bluetooth Speaker', 'Earphones', 'Headphones', 'Wireless Earbuds'], 'category': 'Electronics', 'price_range': (500, 8000)},
            
            # Groceries
            {'names': ['Basmati Rice', 'Brown Rice', 'Premium Rice', 'Organic Rice'], 'category': 'Groceries', 'price_range': (80, 250), 'unit': 'kg'},
            {'names': ['Sugar', 'Salt', 'Cooking Oil', 'Mustard Oil', 'Olive Oil'], 'category': 'Groceries', 'price_range': (50, 800), 'unit': 'kg'},
            {'names': ['Red Lentils', 'Green Lentils', 'Black Gram', 'Chickpeas'], 'category': 'Groceries', 'price_range': (100, 280), 'unit': 'kg'},
            
            # Hardware
            {'names': ['Hammer', 'Screwdriver Set', 'Wrench', 'Pliers', 'Drill Machine'], 'category': 'Hardware', 'price_range': (150, 5500)},
            {'names': ['Nails', 'Screws', 'Nuts & Bolts', 'Wall Anchors'], 'category': 'Hardware', 'price_range': (30, 350), 'unit': 'pack'},
            {'names': ['Paint Brush', 'Roller', 'Sandpaper', 'Measuring Tape'], 'category': 'Hardware', 'price_range': (45, 650)},
            
            # Stationery
            {'names': ['A4 Paper', 'Notebook', 'Diary', 'Register'], 'category': 'Stationery', 'price_range': (50, 450)},
            {'names': ['Pen', 'Pencil', 'Marker', 'Highlighter', 'Eraser'], 'category': 'Stationery', 'price_range': (10, 85)},
            {'names': ['Stapler', 'Punch Machine', 'Paper Clips', 'File Folder'], 'category': 'Stationery', 'price_range': (35, 550)},
            
            # Beverages
            {'names': ['Mineral Water', 'Sparkling Water', 'Juice', 'Energy Drink', 'Soft Drink'], 'category': 'Beverages', 'price_range': (20, 180), 'unit': 'L'},
            {'names': ['Coffee', 'Green Tea', 'Black Tea', 'Herbal Tea'], 'category': 'Beverages', 'price_range': (180, 850), 'unit': 'pack'},
            
            # Snacks
            {'names': ['Potato Chips', 'Corn Chips', 'Namkeen', 'Popcorn'], 'category': 'Snacks', 'price_range': (25, 220), 'unit': 'pack'},
            {'names': ['Chocolate', 'Candy', 'Biscuits', 'Cookies', 'Cake'], 'category': 'Snacks', 'price_range': (20, 450)},
            
            # Personal Care
            {'names': ['Shampoo', 'Conditioner', 'Body Wash', 'Face Wash', 'Soap'], 'category': 'Personal Care', 'price_range': (120, 850)},
            {'names': ['Toothpaste', 'Toothbrush', 'Mouthwash', 'Dental Floss'], 'category': 'Personal Care', 'price_range': (45, 380)},
            
            # Household
            {'names': ['Detergent Powder', 'Liquid Detergent', 'Dish Soap', 'Floor Cleaner'], 'category': 'Household', 'price_range': (85, 650)},
            {'names': ['Tissue Paper', 'Paper Towel', 'Garbage Bags', 'Foil Paper'], 'category': 'Household', 'price_range': (55, 350)},
        ]
        
        products_created = 0
        
        for i in range(count):
            # Pick random template
            template = random.choice(product_templates)
            
            # Generate product details
            base_name = random.choice(template['names'])
            brands = ['Premium', 'Standard', 'Economy', 'Deluxe', 'Pro', 'Max', 'Ultra', 'Plus']
            sizes = ['Small', 'Medium', 'Large', 'XL', '250ml', '500ml', '1L', '5kg', '10kg']
            
            # 60% chance to add brand/size
            if random.random() > 0.4:
                modifier = random.choice(brands + sizes)
                name = f"{modifier} {base_name}"
            else:
                name = base_name
            
            # Get category
            category = next((c for c in categories if c.name == template['category']), categories[0])
            
            # Get unit
            if 'unit' in template:
                unit = next((u for u in units if u.abbreviation == template['unit']), units[0])
            else:
                unit = random.choice(units)
            
            # Generate prices
            price_range = template['price_range']
            cost_price = Decimal(random.uniform(price_range[0], price_range[1]))
            # Selling price is 20-40% markup
            markup = Decimal(random.uniform(1.2, 1.4))
            selling_price = (cost_price * markup).quantize(Decimal('0.01'))
            
            # Generate SKU
            sku = f"PRD-{1000 + i}"
            
            # Generate stock quantity
            stock_qty = Decimal(random.randint(10, 500))
            
            try:
                # Create product
                product = Product.objects.create(
                    tenant=tenant,
                    name=name,
                    sku=sku,
                    description=f"{name} - High quality product",
                    category=category,
                    unit=unit,
                    cost_price=cost_price,
                    selling_price=selling_price,
                    reorder_level=Decimal(random.randint(5, 50)),
                    status='active'
                )
                
                # Create stock
                Stock.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=warehouse,
                    quantity=stock_qty
                )
                
                products_created += 1
                
                if products_created % 10 == 0:
                    self.stdout.write(f'  Created {products_created} products...')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'  Failed to create product: {name} - {str(e)}')
                )
        
        return products_created
