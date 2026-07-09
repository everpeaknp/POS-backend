"""
Django Management Command: Seed Demo Data for Khata ERP
Creates two demo tenants with realistic business data for presentations
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import datetime, timedelta
import random

# Import models
from tenants.models import Tenant
from users.models import User
from inventory.models import Category, UnitOfMeasure, Warehouse, Product, Stock, StockMovement
from construction.models import Site, Worker, Attendance, DailyLog, MaterialConsumption
from sales.models import Customer, Invoice, PaymentReceived, CustomerLedger
from accounting.models import Account

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds the database with demo data for two tenants: Everest Builders and City Hardware'
    
    def __init__(self):
        super().__init__()
        self.fake_names = [
            'Ram Bahadur', 'Sita Sharma', 'Hari Prasad', 'Gita Rai', 'Krishna Thapa',
            'Laxmi Gurung', 'Bikash KC', 'Sunita Magar', 'Rajesh Shrestha', 'Anita Tamang',
            'Dipak Karki', 'Sabita Poudel', 'Nabin Adhikari', 'Kamala Bhattarai', 'Suresh Pandey',
            'Mina Limbu', 'Prakash Rai', 'Radha Subedi', 'Ganesh Dahal', 'Sarita Khadka'
        ]
        self.phone_prefixes = ['984', '985', '986']
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing demo data before seeding',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting demo data seeding...'))
        
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing demo data...'))
            self.clear_demo_data()
        
        with transaction.atomic():
            # Seed Tenant 1: Everest Builders (Construction)
            self.stdout.write(self.style.SUCCESS('\n=== Creating Tenant 1: Everest Builders ==='))
            tenant1, user1 = self.create_construction_tenant()
            
            # Seed Tenant 2: City Hardware & Suppliers
            self.stdout.write(self.style.SUCCESS('\n=== Creating Tenant 2: City Hardware & Suppliers ==='))
            tenant2, user2 = self.create_hardware_tenant()
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Demo data seeding completed successfully!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        # Display login credentials
        self.display_credentials(tenant1, user1, tenant2, user2)
    
    def clear_demo_data(self):
        """Clear existing demo tenants and all related data"""
        from django.db import connection
        from sales.models import CustomerLedger, SalesOrderLine, SalesOrder
        from purchase.models import PurchaseOrderLine, PurchaseRequestLine, PurchaseRequest, DebitNote, Supplier, PurchaseOrder, PurchaseInvoice
        from construction.models import DailyLog, Equipment, EquipmentUsageLog
        from inventory.models import StockMovement, UnitOfMeasure, Category
        from accounting.models import JournalEntry, JournalLine, BankTransaction, TaxRule, VATReturn
        
        # Get tenant IDs
        tenant_ids = list(Tenant.objects.filter(
            name__in=['Everest Builders', 'City Hardware & Suppliers']
        ).values_list('id', flat=True))
        
        if not tenant_ids:
            self.stdout.write(self.style.WARNING('No demo data found to clear'))
            return
        
        # Delete all related data first (in reverse dependency order)
        # This avoids protected foreign key errors
        
        # Accounting
        JournalLine.objects.filter(tenant_id__in=tenant_ids).delete()
        JournalEntry.objects.filter(tenant_id__in=tenant_ids).delete()
        BankTransaction.objects.filter(tenant_id__in=tenant_ids).delete()
        TaxRule.objects.filter(tenant_id__in=tenant_ids).delete()
        VATReturn.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Construction
        MaterialConsumption.objects.filter(tenant_id__in=tenant_ids).delete()
        DailyLog.objects.filter(tenant_id__in=tenant_ids).delete()
        Attendance.objects.filter(tenant_id__in=tenant_ids).delete()
        Worker.objects.filter(tenant_id__in=tenant_ids).delete()
        EquipmentUsageLog.objects.filter(tenant_id__in=tenant_ids).delete()
        Equipment.objects.filter(tenant_id__in=tenant_ids).delete()
        Site.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Sales
        PaymentReceived.objects.filter(tenant_id__in=tenant_ids).delete()
        CustomerLedger.objects.filter(tenant_id__in=tenant_ids).delete()
        Invoice.objects.filter(tenant_id__in=tenant_ids).delete()
        SalesOrderLine.objects.filter(tenant_id__in=tenant_ids).delete()
        SalesOrder.objects.filter(tenant_id__in=tenant_ids).delete()
        Customer.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Purchase
        DebitNote.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseInvoice.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseOrderLine.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseOrder.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseRequestLine.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseRequest.objects.filter(tenant_id__in=tenant_ids).delete()
        Supplier.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Inventory
        StockMovement.objects.filter(tenant_id__in=tenant_ids).delete()
        Stock.objects.filter(tenant_id__in=tenant_ids).delete()
        Product.objects.filter(tenant_id__in=tenant_ids).delete()
        Warehouse.objects.filter(tenant_id__in=tenant_ids).delete()
        UnitOfMeasure.objects.filter(tenant_id__in=tenant_ids).delete()
        Category.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Users
        User.objects.filter(tenant_id__in=tenant_ids).delete()
        
        # Finally delete tenants
        Tenant.objects.filter(id__in=tenant_ids).delete()
        
        self.stdout.write(self.style.SUCCESS('Cleared existing demo data'))
    
    def generate_phone(self):
        """Generate realistic Nepali phone number"""
        prefix = random.choice(self.phone_prefixes)
        number = ''.join([str(random.randint(0, 9)) for _ in range(7)])
        return f"{prefix}{number}"
    
    def get_random_name(self):
        """Get random Nepali name"""
        return random.choice(self.fake_names)
    
    # ========================================================================
    # TENANT 1: EVEREST BUILDERS (CONSTRUCTION)
    # ========================================================================
    
    def create_construction_tenant(self):
        """Create Everest Builders tenant with construction data"""
        # Check if tenant already exists
        tenant = Tenant.objects.filter(name='Everest Builders').first()
        if tenant:
            self.stdout.write(self.style.WARNING('Everest Builders already exists, skipping...'))
            user = User.objects.filter(tenant=tenant, username='everest_admin').first()
            return tenant, user
        
        # Create tenant
        tenant = Tenant.objects.create(
            name='Everest Builders',
            address='Baluwatar, Kathmandu',
            phone='01-4445566',
            email='info@everestbuilders.com.np',
            plan_type='premium',
            active_modules=['construction', 'inventory', 'accounting']
        )
        self.stdout.write(f'Created tenant: {tenant.name}')
        
        # Create admin user
        user = User.objects.create_user(
            username='everest_admin',
            email='admin@everestbuilders.com.np',
            password='demo123',
            tenant=tenant,
            first_name='Admin',
            last_name='User'
        )
        self.stdout.write(f'Created user: {user.username}')
        
        # Seed data
        self.seed_construction_inventory(tenant, user)
        self.seed_construction_sites(tenant, user)
        self.seed_construction_workers(tenant, user)
        self.seed_construction_attendance(tenant, user)
        self.seed_construction_materials(tenant, user)
        
        return tenant, user
    
    def seed_construction_inventory(self, tenant, user):
        """Seed inventory for construction"""
        # Create categories
        construction_cat = Category.objects.create(
            tenant=tenant,
            name='Construction Materials',
            description='All construction related materials'
        )
        
        cement_cat = Category.objects.create(
            tenant=tenant,
            name='Cement',
            parent=construction_cat
        )
        
        steel_cat = Category.objects.create(
            tenant=tenant,
            name='Steel',
            parent=construction_cat
        )
        
        # Create units
        bag = UnitOfMeasure.objects.create(tenant=tenant, name='Bag', abbreviation='bag', type='count')
        kg = UnitOfMeasure.objects.create(tenant=tenant, name='Kilogram', abbreviation='kg', type='weight')
        piece = UnitOfMeasure.objects.create(tenant=tenant, name='Piece', abbreviation='pcs', type='count')
        
        # Create warehouses
        main_warehouse = Warehouse.objects.create(
            tenant=tenant,
            name='Main Warehouse',
            location='Baluwatar',
            manager=user,
            is_active=True
        )
        
        # Create products
        products_data = [
            {'name': 'Cement OPC 53 Grade', 'sku': 'CEM-OPC-53', 'category': cement_cat, 'unit': bag, 'cost': 850, 'selling': 950, 'qty': 500},
            {'name': 'Cement PPC', 'sku': 'CEM-PPC', 'category': cement_cat, 'unit': bag, 'cost': 780, 'selling': 880, 'qty': 300},
            {'name': 'Steel TMT 8mm', 'sku': 'STL-TMT-8', 'category': steel_cat, 'unit': kg, 'cost': 95, 'selling': 110, 'qty': 5000},
            {'name': 'Steel TMT 12mm', 'sku': 'STL-TMT-12', 'category': steel_cat, 'unit': kg, 'cost': 98, 'selling': 115, 'qty': 3000},
            {'name': 'Bricks Red', 'sku': 'BRK-RED', 'category': construction_cat, 'unit': piece, 'cost': 12, 'selling': 15, 'qty': 10000},
        ]
        
        for prod_data in products_data:
            product = Product.objects.create(
                tenant=tenant,
                name=prod_data['name'],
                sku=prod_data['sku'],
                category=prod_data['category'],
                unit=prod_data['unit'],
                cost_price=Decimal(str(prod_data['cost'])),
                selling_price=Decimal(str(prod_data['selling'])),
                status='active'
            )
            
            # Create stock
            Stock.objects.create(
                tenant=tenant,
                product=product,
                warehouse=main_warehouse,
                quantity=Decimal(str(prod_data['qty']))
            )
        
        self.stdout.write(f'Created {len(products_data)} construction products with stock')
    
    def seed_construction_sites(self, tenant, user):
        """Seed construction sites"""
        sites_data = [
            {
                'name': 'Baluwatar Residency',
                'location': 'Baluwatar, Kathmandu',
                'client': 'Sharma Housing Pvt. Ltd.',
                'budget': 5000000,
                'start': datetime.now().date() - timedelta(days=90)
            },
            {
                'name': 'Pokhara Lakeside Villa',
                'location': 'Lakeside, Pokhara',
                'client': 'Lakeside Developers',
                'budget': 3500000,
                'start': datetime.now().date() - timedelta(days=60)
            },
            {
                'name': 'Biratnagar Commercial Complex',
                'location': 'Main Road, Biratnagar',
                'client': 'Eastern Trade Center',
                'budget': 7500000,
                'start': datetime.now().date() - timedelta(days=120)
            },
        ]
        
        main_warehouse = Warehouse.objects.filter(tenant=tenant).first()
        
        for site_data in sites_data:
            # Create site-specific warehouse
            site_warehouse = Warehouse.objects.create(
                tenant=tenant,
                name=f"{site_data['name']} - Site Storage",
                location=site_data['location'],
                manager=user,
                is_active=True
            )
            
            site = Site.objects.create(
                tenant=tenant,
                name=site_data['name'],
                location=site_data['location'],
                client_name=site_data['client'],
                allocated_budget=Decimal(str(site_data['budget'])),
                start_date=site_data['start'],
                estimated_end_date=site_data['start'] + timedelta(days=180),
                manager=user,
                status='active',
                warehouse=site_warehouse
            )
            
            # Transfer some stock to site
            products = Product.objects.filter(tenant=tenant)[:3]
            for product in products:
                transfer_qty = Decimal(str(random.randint(50, 200)))
                Stock.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=site_warehouse,
                    quantity=transfer_qty
                )
        
        self.stdout.write(f'Created {len(sites_data)} construction sites')
    
    def seed_construction_workers(self, tenant, user):
        """Seed construction workers"""
        sites = Site.objects.filter(tenant=tenant)
        categories = ['mason', 'laborer', 'carpenter', 'electrician', 'plumber']
        
        workers_created = 0
        for site in sites:
            # Create 3-4 workers per site
            for i in range(random.randint(3, 4)):
                Worker.objects.create(
                    tenant=tenant,
                    name=self.get_random_name(),
                    phone=self.generate_phone(),
                    category=random.choice(categories),
                    daily_wage=Decimal(str(random.randint(800, 1500))),
                    assigned_site=site,
                    status='active'
                )
                workers_created += 1
        
        self.stdout.write(f'Created {workers_created} workers')
    
    def seed_construction_attendance(self, tenant, user):
        """Seed 30 days of attendance"""
        workers = Worker.objects.filter(tenant=tenant)
        sites = Site.objects.filter(tenant=tenant)
        
        attendance_created = 0
        for days_ago in range(30):
            date = datetime.now().date() - timedelta(days=days_ago)
            
            for worker in workers:
                # 85% chance of present, 10% absent, 5% half day
                rand = random.random()
                if rand < 0.85:
                    att_status = 'present'
                elif rand < 0.95:
                    att_status = 'absent'
                else:
                    att_status = 'half_day'
                
                Attendance.objects.create(
                    tenant=tenant,
                    worker=worker,
                    site=worker.assigned_site,
                    date=date,
                    status=att_status,
                    check_in='08:00' if att_status != 'absent' else None,
                    check_out='17:00' if att_status == 'present' else None,
                    marked_by=user
                )
                attendance_created += 1
        
        self.stdout.write(f'Created {attendance_created} attendance records')
    
    def seed_construction_materials(self, tenant, user):
        """Seed material consumption logs"""
        sites = Site.objects.filter(tenant=tenant)
        
        consumption_created = 0
        for site in sites:
            # Create 5 daily logs with material consumption
            for days_ago in range(5):
                date = datetime.now().date() - timedelta(days=days_ago)
                
                daily_log = DailyLog.objects.create(
                    tenant=tenant,
                    site=site,
                    date=date,
                    work_description=f"Construction work on {site.name}",
                    progress_notes="Good progress made today",
                    weather="Clear",
                    other_expenses=Decimal(str(random.randint(1000, 5000))),
                    submitted_by=user
                )
                
                # Add 2-3 material consumptions per log
                products = Product.objects.filter(tenant=tenant)
                for product in random.sample(list(products), min(3, len(products))):
                    quantity = Decimal(str(random.randint(10, 50)))
                    
                    MaterialConsumption.objects.create(
                        tenant=tenant,
                        daily_log=daily_log,
                        site=site,
                        product=product,
                        quantity=quantity,
                        unit_cost=product.cost_price
                    )
                    consumption_created += 1
        
        self.stdout.write(f'Created {consumption_created} material consumption logs')
    
    # ========================================================================
    # TENANT 2: CITY HARDWARE & SUPPLIERS
    # ========================================================================
    
    def create_hardware_tenant(self):
        """Create City Hardware tenant with hardware/retail data"""
        # Check if tenant already exists
        tenant = Tenant.objects.filter(name='City Hardware & Suppliers').first()
        if tenant:
            self.stdout.write(self.style.WARNING('City Hardware already exists, skipping...'))
            user = User.objects.filter(tenant=tenant, username='hardware_admin').first()
            return tenant, user
        
        # Create tenant
        tenant = Tenant.objects.create(
            name='City Hardware & Suppliers',
            address='New Road, Kathmandu',
            phone='01-4223344',
            email='info@cityhardware.com.np',
            plan_type='premium',
            active_modules=['sales', 'inventory', 'accounting', 'hardware']
        )
        self.stdout.write(f'Created tenant: {tenant.name}')
        
        # Create admin user
        user = User.objects.create_user(
            username='hardware_admin',
            email='admin@cityhardware.com.np',
            password='demo123',
            tenant=tenant,
            first_name='Admin',
            last_name='User'
        )
        self.stdout.write(f'Created user: {user.username}')
        
        # Seed data
        self.seed_hardware_inventory(tenant, user)
        self.seed_hardware_customers(tenant, user)
        self.seed_hardware_credit_sales(tenant, user)
        
        return tenant, user
    
    def seed_hardware_inventory(self, tenant, user):
        """Seed hardware inventory with 50+ products"""
        # Create categories
        tools_cat = Category.objects.create(tenant=tenant, name='Tools')
        plumbing_cat = Category.objects.create(tenant=tenant, name='Plumbing')
        electrical_cat = Category.objects.create(tenant=tenant, name='Electrical')
        paint_cat = Category.objects.create(tenant=tenant, name='Paint & Finishing')
        
        # Create units
        piece = UnitOfMeasure.objects.create(tenant=tenant, name='Piece', abbreviation='pcs', type='count')
        meter = UnitOfMeasure.objects.create(tenant=tenant, name='Meter', abbreviation='m', type='length')
        liter = UnitOfMeasure.objects.create(tenant=tenant, name='Liter', abbreviation='L', type='volume')
        kg = UnitOfMeasure.objects.create(tenant=tenant, name='Kilogram', abbreviation='kg', type='weight')
        
        # Create warehouse
        warehouse = Warehouse.objects.create(
            tenant=tenant,
            name='Main Store',
            location='New Road',
            manager=user,
            is_active=True
        )
        
        # Create products
        products_data = [
            # Tools
            {'name': 'Hammer 500g', 'sku': 'TOOL-HAM-500', 'cat': tools_cat, 'unit': piece, 'cost': 350, 'sell': 450, 'qty': 50},
            {'name': 'Screwdriver Set', 'sku': 'TOOL-SCR-SET', 'cat': tools_cat, 'unit': piece, 'cost': 280, 'sell': 380, 'qty': 30},
            {'name': 'Drill Machine', 'sku': 'TOOL-DRL-001', 'cat': tools_cat, 'unit': piece, 'cost': 3500, 'sell': 4200, 'qty': 15},
            {'name': 'Measuring Tape 5m', 'sku': 'TOOL-TAP-5M', 'cat': tools_cat, 'unit': piece, 'cost': 120, 'sell': 180, 'qty': 100},
            {'name': 'Pliers Set', 'sku': 'TOOL-PLR-SET', 'cat': tools_cat, 'unit': piece, 'cost': 450, 'sell': 600, 'qty': 40},
            
            # Plumbing
            {'name': 'PVC Pipe 1 inch', 'sku': 'PLM-PVC-1IN', 'cat': plumbing_cat, 'unit': meter, 'cost': 85, 'sell': 120, 'qty': 500},
            {'name': 'PVC Pipe 2 inch', 'sku': 'PLM-PVC-2IN', 'cat': plumbing_cat, 'unit': meter, 'cost': 145, 'sell': 190, 'qty': 300},
            {'name': 'Elbow Joint 1 inch', 'sku': 'PLM-ELB-1IN', 'cat': plumbing_cat, 'unit': piece, 'cost': 25, 'sell': 40, 'qty': 200},
            {'name': 'Water Tap Chrome', 'sku': 'PLM-TAP-CHR', 'cat': plumbing_cat, 'unit': piece, 'cost': 450, 'sell': 650, 'qty': 60},
            {'name': 'Sink Basin', 'sku': 'PLM-SNK-001', 'cat': plumbing_cat, 'unit': piece, 'cost': 1200, 'sell': 1600, 'qty': 25},
            
            # Electrical
            {'name': 'Wire 2.5mm', 'sku': 'ELC-WIR-2.5', 'cat': electrical_cat, 'unit': meter, 'cost': 35, 'sell': 50, 'qty': 1000},
            {'name': 'Wire 4mm', 'sku': 'ELC-WIR-4', 'cat': electrical_cat, 'unit': meter, 'cost': 55, 'sell': 75, 'qty': 800},
            {'name': 'Switch Board 2 Gang', 'sku': 'ELC-SWT-2G', 'cat': electrical_cat, 'unit': piece, 'cost': 180, 'sell': 250, 'qty': 100},
            {'name': 'LED Bulb 9W', 'sku': 'ELC-LED-9W', 'cat': electrical_cat, 'unit': piece, 'cost': 120, 'sell': 180, 'qty': 200},
            {'name': 'MCB 32A', 'sku': 'ELC-MCB-32A', 'cat': electrical_cat, 'unit': piece, 'cost': 280, 'sell': 380, 'qty': 80},
            
            # Paint
            {'name': 'Emulsion Paint White', 'sku': 'PNT-EMU-WHT', 'cat': paint_cat, 'unit': liter, 'cost': 450, 'sell': 600, 'qty': 150},
            {'name': 'Enamel Paint Red', 'sku': 'PNT-ENM-RED', 'cat': paint_cat, 'unit': liter, 'cost': 380, 'sell': 520, 'qty': 100},
            {'name': 'Primer', 'sku': 'PNT-PRM-001', 'cat': paint_cat, 'unit': liter, 'cost': 320, 'sell': 450, 'qty': 120},
            {'name': 'Paint Brush 2 inch', 'sku': 'PNT-BRS-2IN', 'cat': paint_cat, 'unit': piece, 'cost': 80, 'sell': 120, 'qty': 150},
            {'name': 'Paint Roller', 'sku': 'PNT-ROL-001', 'cat': paint_cat, 'unit': piece, 'cost': 180, 'sell': 250, 'qty': 80},
        ]
        
        for prod_data in products_data:
            product = Product.objects.create(
                tenant=tenant,
                name=prod_data['name'],
                sku=prod_data['sku'],
                category=prod_data['cat'],
                unit=prod_data['unit'],
                cost_price=Decimal(str(prod_data['cost'])),
                selling_price=Decimal(str(prod_data['sell'])),
                status='active'
            )
            
            Stock.objects.create(
                tenant=tenant,
                product=product,
                warehouse=warehouse,
                quantity=Decimal(str(prod_data['qty']))
            )
        
        self.stdout.write(f'Created {len(products_data)} hardware products with stock')
    
    def seed_hardware_customers(self, tenant, user):
        """Seed customers with credit limits"""
        customers_data = [
            {'name': 'Ram Bahadur Hardware', 'phone': self.generate_phone(), 'credit': 100000, 'balance': 45000},
            {'name': 'Sita Construction Supplies', 'phone': self.generate_phone(), 'credit': 150000, 'balance': 85000},
            {'name': 'Hari Traders', 'phone': self.generate_phone(), 'credit': 75000, 'balance': 32000},
            {'name': 'Gita Enterprises', 'phone': self.generate_phone(), 'credit': 50000, 'balance': 18000},
            {'name': 'Krishna Building Materials', 'phone': self.generate_phone(), 'credit': 200000, 'balance': 125000},
        ]
        
        for cust_data in customers_data:
            Customer.objects.create(
                tenant=tenant,
                name=cust_data['name'],
                phone=cust_data['phone'],
                type='Business',
                credit_limit=Decimal(str(cust_data['credit'])),
                current_balance=Decimal(str(cust_data['balance'])),
                payment_terms='Net 30',
                status='active'
            )
        
        self.stdout.write(f'Created {len(customers_data)} customers with credit')
    
    def seed_hardware_credit_sales(self, tenant, user):
        """Seed credit sales and payment history"""
        customers = Customer.objects.filter(tenant=tenant)
        products = Product.objects.filter(tenant=tenant)
        
        invoices_created = 0
        payments_created = 0
        
        for customer in customers:
            # Create 3-5 credit invoices per customer
            for i in range(random.randint(3, 5)):
                days_ago = random.randint(10, 60)
                invoice_date = datetime.now().date() - timedelta(days=days_ago)
                
                amount = Decimal(str(random.randint(10000, 50000)))
                
                invoice = Invoice.objects.create(
                    tenant=tenant,
                    invoice_number=f"INV-{invoices_created + 1:05d}",
                    date=invoice_date,
                    due_date=invoice_date + timedelta(days=30),
                    customer=customer,
                    amount=amount,
                    paid_amount=Decimal('0.00'),
                    payment_type='credit',
                    status='Sent',
                    created_by=user
                )
                invoices_created += 1
            
            # Create 2-3 payments per customer
            for i in range(random.randint(2, 3)):
                days_ago = random.randint(5, 45)
                payment_date = datetime.now().date() - timedelta(days=days_ago)
                
                payment_amount = Decimal(str(random.randint(5000, 25000)))
                
                PaymentReceived.objects.create(
                    tenant=tenant,
                    date=payment_date,
                    customer=customer,
                    amount=payment_amount,
                    payment_method=random.choice(['cash', 'bank', 'esewa', 'khalti']),
                    received_by=user
                )
                payments_created += 1
        
        self.stdout.write(f'Created {invoices_created} credit invoices and {payments_created} payments')
    
    def display_credentials(self, tenant1, user1, tenant2, user2):
        """Display login credentials"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('DEFAULT LOGIN CREDENTIALS'))
        self.stdout.write('='*60)
        
        self.stdout.write(self.style.SUCCESS('\nTENANT 1: Everest Builders (Construction)'))
        self.stdout.write(f'  Organization: {tenant1.name}')
        self.stdout.write(f'  Username: {user1.username}')
        self.stdout.write(f'  Password: demo123')
        self.stdout.write(f'  Email: {user1.email}')
        self.stdout.write(f'  Modules: Construction, Inventory, Accounting')
        
        self.stdout.write(self.style.SUCCESS('\nTENANT 2: City Hardware & Suppliers'))
        self.stdout.write(f'  Organization: {tenant2.name}')
        self.stdout.write(f'  Username: {user2.username}')
        self.stdout.write(f'  Password: demo123')
        self.stdout.write(f'  Email: {user2.email}')
        self.stdout.write(f'  Modules: Sales, Inventory, Accounting')
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('You can now login with these credentials!'))
        self.stdout.write('='*60 + '\n')
