"""
Seed realistic demo data for an existing tenant (by user email or tenant name/slug).
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounting.chart_seed import seed_default_chart_of_accounts
from accounting.fiscal_services import ensure_fiscal_year
from accounting.fiscal_utils import bs_fiscal_year_ad_range, current_bs_fiscal_start_year
from accounting.models import (
    Account,
    BankAccount,
    BankTransaction,
    JournalEntry,
    JournalLine,
    TaxRule,
    VATReturn,
)
from accounting.services import create_journal_entry
from accounting.utils import generate_entry_number
from construction.models import (
    Attendance as ConstructionAttendance,
    DailyLog,
    Equipment,
    EquipmentUsageLog,
    MaterialConsumption,
    Site as ConstructionSite,
    Worker as ConstructionWorker,
)
from hr.models import Attendance, Department, Employee, LeaveRequest, LeaveType, Payroll
from hr.utils import NEPALI_MONTHS, calculate_employee_payroll_amounts, current_bs_year
from inventory.bulk_pricing_models import BulkPricing
from inventory.models import Category, Product, Stock, StockMovement, UnitOfMeasure, Warehouse
from inventory.pricing_models import CustomerSpecificPrice
from pos.models import (
    POSDailySalesReport,
    POSDiscount,
    POSSession,
    POSTransaction,
    POSTransactionLine,
)
from pos.utils import compute_pos_amounts, quantize_money
from purchase.models import (
    DebitNote,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
    Supplier,
)
from sales.models import (
    CreditNote,
    Customer,
    CustomerLedger,
    Invoice,
    PaymentReceived,
    Quotation,
    QuotationLine,
    SalesOrder,
    SalesOrderLine,
)
from tenants.middleware import set_current_tenant
from tenants.models import Tenant

User = get_user_model()

NEPALI_NAMES = [
    ('Ram', 'Shrestha'), ('Sita', 'Tamang'), ('Hari', 'Gurung'), ('Gita', 'Rai'),
    ('Krishna', 'Thapa'), ('Laxmi', 'Magar'), ('Bikash', 'KC'), ('Sunita', 'Poudel'),
    ('Rajesh', 'Karki'), ('Anita', 'Limbu'), ('Dipak', 'Adhikari'), ('Sabita', 'Bhattarai'),
    ('Nabin', 'Pandey'), ('Kamala', 'Subedi'), ('Suresh', 'Dahal'), ('Mina', 'Khadka'),
    ('Prakash', 'Basnet'), ('Radha', 'Joshi'), ('Ganesh', 'Maharjan'), ('Sarita', 'Nepali'),
]

DEPARTMENTS = [
    ('Sales & Marketing', 'Customer acquisition and retail sales'),
    ('Accounts & Finance', 'Billing, VAT, and financial reporting'),
    ('Warehouse & Logistics', 'Stock handling and delivery'),
    ('Administration', 'HR, office management, and compliance'),
    ('Store Operations', 'Counter sales and POS operations'),
]

DESIGNATIONS = {
    'Sales & Marketing': ['Sales Executive', 'Sales Manager', 'Marketing Officer'],
    'Accounts & Finance': ['Accountant', 'Finance Officer', 'Billing Clerk'],
    'Warehouse & Logistics': ['Store Keeper', 'Delivery Driver', 'Warehouse Supervisor'],
    'Administration': ['HR Officer', 'Office Assistant', 'Receptionist'],
    'Store Operations': ['Cashier', 'Store Supervisor', 'Helper'],
}

PRODUCTS = [
    ('Rice Premium 25kg', 'RICE-25KG', 'Groceries', 2200, 2650, 120),
    ('Sunflower Oil 1L', 'OIL-SFL-1L', 'Groceries', 180, 225, 200),
    ('Sugar 1kg', 'SUG-1KG', 'Groceries', 95, 115, 300),
    ('Tea Leaf 500g', 'TEA-500G', 'Groceries', 280, 350, 80),
    ('Dal Masoor 1kg', 'DAL-MSR-1KG', 'Groceries', 140, 175, 150),
    ('Hammer 500g', 'TOOL-HAM', 'Hardware', 350, 450, 40),
    ('PVC Pipe 1 inch', 'PVC-1IN', 'Hardware', 85, 120, 250),
    ('LED Bulb 9W', 'LED-9W', 'Electrical', 120, 180, 100),
    ('Notebook A4', 'NB-A4', 'Stationery', 45, 65, 500),
    ('Pen Blue Box', 'PEN-BLU', 'Stationery', 120, 160, 200),
    ('Detergent 1kg', 'DET-1KG', 'Household', 110, 145, 90),
    ('Soap Bar', 'SOAP-BAR', 'Household', 35, 48, 400),
    ('Mineral Water 1L', 'WTR-1L', 'Beverages', 12, 18, 600),
    ('Biscuit Pack', 'BIS-PCK', 'Snacks', 25, 35, 350),
    ('Match Box', 'MCH-BOX', 'Household', 8, 12, 800),
    # Extended trade catalog
    ('Basmati Rice 10kg', 'RICE-BAS-10', 'Groceries', 950, 1150, 85),
    ('Wheat Flour 5kg', 'FLR-WHT-5', 'Groceries', 320, 395, 140),
    ('Salt 1kg', 'SLT-1KG', 'Groceries', 22, 30, 500),
    ('Milk Powder 400g', 'MLK-PWD', 'Groceries', 420, 520, 8),
    ('Noodles Pack', 'NDL-PCK', 'Groceries', 28, 38, 12),
    ('Tomato Sauce', 'SCE-TOM', 'Groceries', 95, 125, 60),
    ('Spices Mix 100g', 'SPC-MIX', 'Groceries', 65, 85, 45),
    ('Screwdriver Set', 'TOOL-SCR', 'Hardware', 280, 380, 5),
    ('Drill Machine', 'TOOL-DRL', 'Hardware', 3500, 4200, 3),
    ('Measuring Tape 5m', 'TOOL-TAP', 'Hardware', 120, 180, 18),
    ('Paint Brush Set', 'PNT-BRS', 'Hardware', 150, 220, 25),
    ('Wire 2.5mm', 'ELC-WIR25', 'Electrical', 35, 50, 8),
    ('Switch Board 2 Gang', 'ELC-SWT2', 'Electrical', 180, 250, 15),
    ('MCB 32A', 'ELC-MCB32', 'Electrical', 280, 380, 6),
    ('Extension Cord 5m', 'ELC-EXT5', 'Electrical', 450, 590, 10),
    ('Calculator Basic', 'STN-CALC', 'Stationery', 180, 250, 30),
    ('Stapler Large', 'STN-STPL', 'Stationery', 220, 295, 22),
    ('File Folder A4', 'STN-FILE', 'Stationery', 35, 50, 150),
    ('Bleach 500ml', 'HSH-BLE', 'Household', 75, 98, 7),
    ('Floor Cleaner 1L', 'HSH-CLN', 'Household', 130, 165, 9),
    ('Toilet Paper 4-roll', 'HSH-TP4', 'Household', 180, 230, 14),
    ('Cola 1.5L', 'BEV-COLA', 'Beverages', 85, 110, 5),
    ('Juice Tetra 1L', 'BEV-JUC', 'Beverages', 95, 125, 11),
    ('Energy Drink', 'BEV-ENG', 'Beverages', 110, 145, 4),
    ('Chips Pack 50g', 'SNK-CHP', 'Snacks', 35, 48, 16),
    ('Chocolate Bar', 'SNK-CHO', 'Snacks', 55, 75, 3),
    ('Instant Coffee 100g', 'GRC-COF', 'Groceries', 320, 410, 2),
    ('Hand Sanitizer 500ml', 'HSH-SAN', 'Household', 140, 185, 1),
    ('Face Mask Box 50', 'HSH-MSK', 'Household', 450, 580, 0),
]

CUSTOMERS = [
    ('Kathmandu Mart', '9841112233', 'Business', '601111111', 'New Baneshwor, Kathmandu'),
    ('Anil Traders', '9852223344', 'Business', '602222222', 'Kalimati, Kathmandu'),
    ('Sunita Store', '9863334455', 'Individual', '', 'Lalitpur'),
    ('New Road Shop', '9844445566', 'Business', '604444444', 'New Road, Kathmandu'),
    ('Bhaktapur Retail', '9855556677', 'Business', '605555555', 'Bhaktapur'),
    ('Pokhara Wholesale', '9846667788', 'Business', '606666666', 'Pokhara-8'),
    ('Everest Enterprises', '9857778899', 'Business', '607777777', 'Thamel, Kathmandu'),
    ('Rita General Store', '9868889900', 'Individual', '', 'Kirtipur'),
    ('Valley Supermarket', '9849990011', 'Business', '608888888', 'Koteshwor, Kathmandu'),
    ('Walk-in Customer', '9800000001', 'Individual', '', 'Kathmandu'),
]

SUPPLIERS = [
    ('Himalayan Distributors', '9847778899', '601234567', 'Baneshwor, Kathmandu', 'Nabil Bank'),
    ('Valley Wholesale Pvt. Ltd.', '9858889900', '602345678', 'Kalimati, Kathmandu', 'Nepal Investment Bank'),
    ('Eastern Supply Co.', '9869990011', '603456789', 'Biratnagar', 'Global IME Bank'),
    ('Nepal Trading House', '9841234567', '604567890', 'New Road, Kathmandu', 'Sanima Bank'),
    ('Annapurna FMCG Suppliers', '9852345678', '605678901', 'Butwal', 'Laxmi Sunrise Bank'),
    ('Kathmandu Hardware Hub', '9863456789', '606789012', 'Teku, Kathmandu', 'NIC Asia Bank'),
    ('Everest Electricals', '9844567890', '607890123', 'Patan, Lalitpur', 'Kumari Bank'),
    ('Pokhara General Traders', '9855678901', '608901234', 'Pokhara', 'Prabhu Bank'),
]

# Extra catalog for the Hardware vertical (SKU prefix HW-)
HARDWARE_PRODUCTS = [
    ('Cement OPC 50kg', 'HW-CEM-50', 'Hardware', 650, 780, 180),
    ('Steel Rod 12mm', 'HW-RD-12MM', 'Hardware', 95, 125, 400),
    ('Steel Rod 16mm', 'HW-RD-16MM', 'Hardware', 140, 175, 250),
    ('Binding Wire 25kg', 'HW-BND-25', 'Hardware', 180, 220, 60),
    ('Nails 3 inch Box', 'HW-NAIL-3', 'Hardware', 280, 350, 45),
    ('Paint Emulsion 20L', 'HW-PNT-20L', 'Hardware', 4200, 5100, 12),
    ('Door Handle Set', 'HW-DH-SET', 'Hardware', 450, 620, 35),
    ('Padlock 50mm', 'HW-LOCK-50', 'Hardware', 320, 420, 80),
    ('Water Tap Set Chrome', 'HW-TAP-CR', 'Plumbing', 550, 720, 40),
    ('Sink Basin SS', 'HW-SINK-SS', 'Plumbing', 2800, 3500, 15),
    ('GI Pipe 1/2 inch', 'HW-GI-05', 'Plumbing', 120, 165, 300),
    ('CPVC Elbow 1 inch', 'HW-CPVC-ELB', 'Plumbing', 35, 52, 500),
    ('Distribution Board 4-Way', 'HW-DB-4W', 'Electrical', 850, 1100, 25),
    ('Ceiling Fan 48 inch', 'HW-FAN-48', 'Electrical', 2200, 2850, 18),
    ('Concealed Wire 1.5mm Roll', 'HW-WIR-15', 'Electrical', 2800, 3400, 22),
]

HARDWARE_TRADE_CUSTOMERS = [
    ('Sharma Hardware Store', '9841010101', '609101010', 'Lalitpur'),
    ('Bhaktapur Builders Supply', '9852020202', '609202020', 'Bhaktapur'),
    ('Pokhara Tools & Traders', '9863030303', '609303030', 'Pokhara'),
    ('Everest Construction Mart', '9844040404', '609404040', 'Kathmandu'),
]

# Construction vertical (SKU prefix CON-)
CONSTRUCTION_PRODUCTS = [
    ('Cement OPC 53 Grade', 'CON-CEM-53', 'Construction Materials', 850, 950, 800),
    ('Cement PPC', 'CON-CEM-PPC', 'Construction Materials', 780, 880, 600),
    ('Steel TMT 8mm', 'CON-STL-8', 'Construction Materials', 95, 110, 5000),
    ('Steel TMT 12mm', 'CON-STL-12', 'Construction Materials', 98, 115, 3500),
    ('Red Bricks', 'CON-BRK-RED', 'Construction Materials', 12, 15, 15000),
    ('Fine Sand', 'CON-SAND', 'Construction Materials', 45, 55, 200),
    ('Aggregate 20mm', 'CON-AGG-20', 'Construction Materials', 38, 48, 180),
    ('Binding Wire 20kg', 'CON-BND-20', 'Construction Materials', 160, 195, 80),
]

CONSTRUCTION_SITES = [
    ('Baneshwor Plaza Extension', 'Baneshwor, Kathmandu', 'Sharma Housing Pvt. Ltd.', 500000, 'active', 90),
    ('Lalitpur Row Houses', 'Pulchowk, Lalitpur', 'Metro Developers', 350000, 'active', 60),
    ('Pokhara Resort Phase 2', 'Lakeside, Pokhara', 'Lakeside Resorts', 550000, 'active', 120),
    ('Bhaktapur Heritage Renovation', 'Durbar Square, Bhaktapur', 'Heritage Trust', 420000, 'on_hold', 45),
    ('Chitwan Farm House', 'Bharatpur, Chitwan', 'Private Client', 280000, 'planned', 0),
]

CONSTRUCTION_EQUIPMENT = [
    ('JCB Excavator', 'Excavator', 'rented', None, 8500),
    ('Concrete Mixer 10/7', 'Mixer', 'owned', 280000, None),
    ('Tower Crane 25T', 'Crane', 'rented', None, 12000),
    ('Vibrating Plate Compactor', 'Compactor', 'owned', 45000, None),
]

POS_PAYMENT_METHODS = ['cash', 'cash', 'cash', 'esewa', 'khalti', 'fonepay', 'card', 'credit']


class Command(BaseCommand):
    help = 'Seed random business data for an existing tenant (HR, inventory, sales, purchase, accounting).'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Admin user email (uses their active tenant)')
        parser.add_argument('--tenant', type=str, help='Tenant name or slug')
        parser.add_argument('--clear-hr', action='store_true', help='Clear existing HR data before seeding')
        parser.add_argument('--clear-inventory', action='store_true', help='Clear existing inventory data before seeding')
        parser.add_argument('--inventory-only', action='store_true', help='Only seed inventory (skip HR, sales, purchase)')
        parser.add_argument('--clear-purchase', action='store_true', help='Clear existing purchase data before seeding')
        parser.add_argument('--purchase-only', action='store_true', help='Only seed purchase module data')
        parser.add_argument('--clear-sales', action='store_true', help='Clear existing sales data before seeding')
        parser.add_argument('--sales-only', action='store_true', help='Only seed sales module data')
        parser.add_argument('--clear-hardware', action='store_true', help='Clear hardware bulk/custom pricing and HW products')
        parser.add_argument('--hardware-only', action='store_true', help='Only seed hardware vertical data')
        parser.add_argument('--clear-construction', action='store_true', help='Clear construction module seed data')
        parser.add_argument('--construction-only', action='store_true', help='Only seed construction module data')
        parser.add_argument('--clear-pos', action='store_true', help='Clear POS module seed data')
        parser.add_argument('--pos-only', action='store_true', help='Only seed POS module data')
        parser.add_argument('--clear-accounting', action='store_true', help='Clear accounting module seed data')
        parser.add_argument('--accounting-only', action='store_true', help='Only seed accounting module data')
        parser.add_argument('--employees', type=int, default=18, help='Number of employees to create')

    def handle(self, *args, **options):
        tenant, user = self._resolve_tenant(options)
        set_current_tenant(tenant)
        try:
            self._run_seed(tenant, user, options)
        finally:
            set_current_tenant(None)

    def _run_seed(self, tenant, user, options):
        self.stdout.write(self.style.SUCCESS(f'Seeding data for {tenant.name} (slug: {tenant.slug})'))

        if options['clear_hr']:
            self._clear_hr(tenant)
        if options['clear_inventory']:
            self._clear_inventory(tenant)
        if options['clear_purchase']:
            self._clear_purchase(tenant)
        if options['clear_sales']:
            self._clear_sales(tenant)
        if options['clear_hardware']:
            self._clear_hardware(tenant)
        if options['clear_construction']:
            self._clear_construction(tenant)
        if options['clear_pos']:
            self._clear_pos(tenant)
        if options['clear_accounting']:
            self._clear_accounting(tenant)

        inventory_only = options['inventory_only']
        purchase_only = options['purchase_only']
        sales_only = options['sales_only']
        hardware_only = options['hardware_only']
        construction_only = options['construction_only']
        pos_only = options['pos_only']
        accounting_only = options['accounting_only']
        module_only = (
            inventory_only or purchase_only or sales_only
            or hardware_only or construction_only or pos_only or accounting_only
        )

        with transaction.atomic():
            if not module_only or construction_only or pos_only or accounting_only:
                self._seed_accounting(tenant)
            if not purchase_only and not sales_only and not hardware_only and not construction_only and not pos_only and not accounting_only:
                inv_ctx = self._seed_inventory(tenant, user, force=options['clear_inventory'])
                if inv_ctx and not StockMovement._base_manager.filter(tenant=tenant).exists():
                    self._seed_inventory_movements(tenant, user, inv_ctx)
            if not inventory_only and not purchase_only and not hardware_only and not construction_only and not pos_only and not accounting_only:
                self._seed_sales(tenant, user, force=options['clear_sales'])
            if not inventory_only and not sales_only and not hardware_only and not construction_only and not pos_only and not accounting_only:
                self._seed_purchase(tenant, user, force=options['clear_purchase'])
            if not inventory_only and not purchase_only and not sales_only and not construction_only and not pos_only and not accounting_only:
                self._seed_hardware(tenant, user, force=options['clear_hardware'])
            if not module_only:
                employees = self._seed_hr(tenant, user, options['employees'])
                self._seed_attendance(tenant, employees)
                self._seed_leave(tenant, user, employees)
                self._seed_payroll(tenant, employees)
                self._seed_construction(tenant, user, force=options['clear_construction'])
                self._seed_pos(tenant, user, force=options['clear_pos'])
                self._seed_accounting_demo(tenant, user, force=options['clear_accounting'])
            elif construction_only:
                self._seed_construction(tenant, user, force=options['clear_construction'])
            elif pos_only:
                self._seed_pos(tenant, user, force=options['clear_pos'])
            elif accounting_only:
                self._seed_accounting_demo(tenant, user, force=options['clear_accounting'])

        self.stdout.write(self.style.SUCCESS('Seeding completed.'))
        self._print_summary(tenant)

    def _resolve_tenant(self, options):
        if options.get('email'):
            try:
                user = User.objects.get(email=options['email'])
            except User.DoesNotExist as exc:
                raise CommandError(f'User not found: {options["email"]}') from exc
            if not user.tenant:
                raise CommandError(f'User {user.email} has no active tenant assigned.')
            return user.tenant, user

        if options.get('tenant'):
            key = options['tenant']
            tenant = Tenant.objects.filter(name=key).first() or Tenant.objects.filter(slug=key).first()
            if not tenant:
                raise CommandError(f'Tenant not found: {key}')
            user = User.objects.filter(tenant=tenant, role='admin').first() or User.objects.filter(tenant=tenant).first()
            if not user:
                user = tenant.created_by
            return tenant, user

        raise CommandError('Provide --email or --tenant')

    def _clear_hr(self, tenant):
        Payroll._base_manager.filter(tenant=tenant).delete()
        LeaveRequest._base_manager.filter(tenant=tenant).delete()
        Attendance._base_manager.filter(tenant=tenant).delete()
        Employee._base_manager.filter(tenant=tenant).delete()
        LeaveType._base_manager.filter(tenant=tenant).delete()
        Department._base_manager.filter(tenant=tenant).delete()
        self.stdout.write('Cleared existing HR data')

    def _clear_inventory(self, tenant):
        StockMovement._base_manager.filter(tenant=tenant).delete()
        Stock._base_manager.filter(tenant=tenant).delete()
        Product._base_manager.filter(tenant=tenant).delete()
        Warehouse._base_manager.filter(tenant=tenant).delete()
        Category._base_manager.filter(tenant=tenant).delete()
        UnitOfMeasure._base_manager.filter(tenant=tenant).delete()
        self.stdout.write('Cleared existing inventory data')

    def _clear_purchase(self, tenant):
        DebitNote._base_manager.filter(tenant=tenant).delete()
        PurchaseInvoice._base_manager.filter(tenant=tenant).delete()
        PurchaseOrderLine._base_manager.filter(tenant=tenant).delete()
        PurchaseOrder._base_manager.filter(tenant=tenant).delete()
        PurchaseRequestLine._base_manager.filter(tenant=tenant).delete()
        PurchaseRequest._base_manager.filter(tenant=tenant).delete()
        Supplier._base_manager.filter(tenant=tenant).delete()
        self.stdout.write('Cleared existing purchase data')

    def _clear_sales(self, tenant):
        PaymentReceived._base_manager.filter(tenant=tenant).delete()
        CreditNote._base_manager.filter(tenant=tenant).delete()
        CustomerLedger._base_manager.filter(tenant=tenant).delete()
        Invoice._base_manager.filter(tenant=tenant).delete()
        SalesOrderLine._base_manager.filter(tenant=tenant).delete()
        SalesOrder._base_manager.filter(tenant=tenant).delete()
        QuotationLine._base_manager.filter(tenant=tenant).delete()
        Quotation._base_manager.filter(tenant=tenant).delete()
        Customer._base_manager.filter(tenant=tenant).delete()
        self.stdout.write('Cleared existing sales data')

    def _clear_hardware(self, tenant):
        BulkPricing._base_manager.filter(tenant=tenant).delete()
        CustomerSpecificPrice._base_manager.filter(tenant=tenant).delete()
        hw_products = Product._base_manager.filter(tenant=tenant, sku__startswith='HW-')
        Stock._base_manager.filter(tenant=tenant, product__in=hw_products).delete()
        hw_products.delete()
        SalesOrderLine._base_manager.filter(
            tenant=tenant, sales_order__reference__startswith='SEED-HW-',
        ).delete()
        SalesOrder._base_manager.filter(tenant=tenant, reference__startswith='SEED-HW-').delete()
        self.stdout.write('Cleared hardware vertical seed data')

    def _clear_construction(self, tenant):
        seed_sites = ConstructionSite._base_manager.filter(
            tenant=tenant, description__startswith='SEED-CON',
        )
        site_ids = list(seed_sites.values_list('id', flat=True))
        warehouse_ids = list(seed_sites.values_list('warehouse_id', flat=True))

        EquipmentUsageLog._base_manager.filter(tenant=tenant, site_id__in=site_ids).delete()
        MaterialConsumption._base_manager.filter(tenant=tenant, site_id__in=site_ids).delete()
        DailyLog._base_manager.filter(tenant=tenant, site_id__in=site_ids).delete()
        ConstructionAttendance._base_manager.filter(tenant=tenant, site_id__in=site_ids).delete()
        Equipment._base_manager.filter(tenant=tenant, notes='SEED-CON').delete()
        ConstructionWorker._base_manager.filter(tenant=tenant, id_number__startswith='SEED-CON-').delete()
        seed_sites.delete()

        if warehouse_ids:
            Stock._base_manager.filter(tenant=tenant, warehouse_id__in=warehouse_ids).delete()
            Warehouse._base_manager.filter(tenant=tenant, id__in=warehouse_ids).delete()

        con_products = Product._base_manager.filter(tenant=tenant, sku__startswith='CON-')
        Stock._base_manager.filter(tenant=tenant, product__in=con_products).delete()
        con_products.delete()
        self.stdout.write('Cleared construction module seed data')

    def _clear_pos(self, tenant):
        seed_txns = list(
            POSTransaction._base_manager.filter(tenant=tenant, notes='SEED-POS').select_related('warehouse')
        )
        for txn in seed_txns:
            if txn.status != 'completed':
                continue
            for line in POSTransactionLine._base_manager.filter(tenant=tenant, transaction=txn):
                if txn.warehouse_id:
                    stock = Stock._base_manager.filter(
                        tenant=tenant, product=line.product, warehouse_id=txn.warehouse_id,
                    ).first()
                    if stock:
                        stock.quantity += line.quantity
                        stock.save(update_fields=['quantity'])
            if txn.payment_method == 'credit' and txn.customer_id:
                customer = Customer._base_manager.filter(pk=txn.customer_id).first()
                if customer:
                    customer.current_balance = max(Decimal('0'), customer.current_balance - txn.total)
                    customer.save(update_fields=['current_balance'])

        POSTransactionLine._base_manager.filter(
            tenant=tenant, transaction__notes='SEED-POS',
        ).delete()
        POSTransaction._base_manager.filter(tenant=tenant, notes='SEED-POS').delete()
        POSDiscount._base_manager.filter(tenant=tenant, code__startswith='SEED-').delete()
        POSSession._base_manager.filter(tenant=tenant, notes='SEED-POS').delete()
        self.stdout.write('Cleared POS module seed data')

    def _seed_accounting(self, tenant):
        result = seed_default_chart_of_accounts(tenant)
        ensure_fiscal_year(tenant)
        self.stdout.write(f'  Accounting: {result["created"]} accounts created, {result["skipped"]} skipped')

    def _account(self, tenant, code):
        return Account._base_manager.get(tenant=tenant, code=code)

    def _reverse_entry_balances(self, entry):
        for line in JournalLine._base_manager.filter(journal_entry=entry).select_related('account'):
            account = line.account
            if account.type in ('Assets', 'Expense'):
                account.balance -= line.debit - line.credit
            else:
                account.balance -= line.credit - line.debit
            account.save(update_fields=['balance'])

    def _clear_accounting(self, tenant):
        seed_refs = JournalEntry._base_manager.filter(
            tenant=tenant, reference__startswith='SEED-ACC',
        )
        for entry in seed_refs:
            if entry.status == 'posted':
                self._reverse_entry_balances(entry)
        BankTransaction._base_manager.filter(
            tenant=tenant, reference__startswith='SEED-ACC',
        ).delete()
        JournalLine._base_manager.filter(journal_entry__in=seed_refs).delete()
        seed_refs.delete()
        BankAccount._base_manager.filter(tenant=tenant, account_number__startswith='SEED-').delete()
        VATReturn._base_manager.filter(tenant=tenant, return_number__startswith='SEED-').delete()
        TaxRule._base_manager.filter(tenant=tenant, name__startswith='SEED ').delete()
        drafts = JournalEntry._base_manager.filter(tenant=tenant, reference__startswith='SEED-ACC-DRAFT')
        JournalLine._base_manager.filter(journal_entry__in=drafts).delete()
        drafts.delete()
        self.stdout.write('Cleared accounting module seed data')

    def _seed_accounting_demo(self, tenant, user, *, force=False):
        if BankAccount._base_manager.filter(tenant=tenant, account_number__startswith='SEED-').exists() and not force:
            self.stdout.write('  Accounting demo: skipped (already has seed data)')
            return

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)
        today = timezone.now().date()
        bs_year = current_bs_fiscal_start_year()
        fy_start, fy_end = bs_fiscal_year_ad_range(bs_year)

        cash = self._account(tenant, '1000')
        petty = self._account(tenant, '1005')
        ar = self._account(tenant, '1100')
        inventory = self._account(tenant, '1200')
        ap = self._account(tenant, '2000')
        vat_payable = self._account(tenant, '2200')
        capital = self._account(tenant, '3000')
        sales = self._account(tenant, '4000')
        other_income = self._account(tenant, '4100')
        cogs = self._account(tenant, '5000')
        admin_exp = self._account(tenant, '5400')

        nabil_gl = Account._base_manager.get_or_create(
            tenant=tenant, code='1011',
            defaults={'name': 'Nabil Bank — Current', 'type': 'Assets', 'sub_type': 'Bank', 'status': 'active', 'level': 0},
        )[0]
        gime_gl = Account._base_manager.get_or_create(
            tenant=tenant, code='1012',
            defaults={'name': 'Global IME — Savings', 'type': 'Assets', 'sub_type': 'Bank', 'status': 'active', 'level': 0},
        )[0]

        bank_count = tx_count = je_count = 0
        nabil = BankAccount.objects.create(
            tenant=tenant,
            bank_name='Nabil Bank',
            account_name='Bishal Trade Current',
            account_number='SEED-NABIL-001',
            type='Current',
            branch='New Road, Kathmandu',
            gl_account=nabil_gl,
            balance=Decimal('0'),
            status='active',
        )
        gime = BankAccount.objects.create(
            tenant=tenant,
            bank_name='Global IME Bank',
            account_name='Bishal Trade Savings',
            account_number='SEED-GIME-001',
            type='Savings',
            branch='Baneshwor, Kathmandu',
            gl_account=gime_gl,
            balance=Decimal('0'),
            status='active',
        )
        bank_count = 2

        if not JournalEntry._base_manager.filter(tenant=tenant, reference='SEED-ACC-OPEN').exists():
            opening_entries = [
                {'account': cash, 'debit': Decimal('25000'), 'credit': Decimal('0')},
                {'account': petty, 'debit': Decimal('5000'), 'credit': Decimal('0')},
                {'account': nabil_gl, 'debit': Decimal('350000'), 'credit': Decimal('0')},
                {'account': gime_gl, 'debit': Decimal('180000'), 'credit': Decimal('0')},
                {'account': ar, 'debit': Decimal('85000'), 'credit': Decimal('0')},
                {'account': inventory, 'debit': Decimal('420000'), 'credit': Decimal('0')},
                {'account': capital, 'debit': Decimal('0'), 'credit': Decimal('1065000')},
            ]
            create_journal_entry(
                tenant=tenant,
                description='Opening balances — seed demo',
                reference='SEED-ACC-OPEN',
                date=fy_start,
                entry_type='Opening',
                entries=opening_entries,
            )
            je_count += 1
            nabil.balance = Decimal('350000')
            gime.balance = Decimal('180000')
            nabil.save(update_fields=['balance'])
            gime.save(update_fields=['balance'])

        vat_rule = TaxRule._base_manager.filter(tenant=tenant, name='SEED VAT 13%').first()
        if not vat_rule:
            TaxRule.objects.create(
                tenant=tenant,
                name='SEED VAT 13%',
                type='VAT',
                rate=Decimal('13'),
                applicable_on='Both',
                account=vat_payable,
                status='active',
                description='Standard Nepal VAT for demo',
            )

        for month_offset in range(5, -1, -1):
            if month_offset == 0:
                entry_date = today.replace(day=min(today.day, 28))
            else:
                m = today.month - month_offset
                y = today.year
                while m <= 0:
                    m += 12
                    y -= 1
                entry_date = date(y, m, min(15, 28))

            ref_rev = f'SEED-ACC-REV-{entry_date.strftime("%Y%m")}'
            if not JournalEntry._base_manager.filter(tenant=tenant, reference=ref_rev).exists():
                net_sales = Decimal(str(random.randint(85000, 165000)))
                output_vat = (net_sales * Decimal('0.13')).quantize(Decimal('0.01'))
                bank_gl = nabil_gl if month_offset % 2 == 0 else gime_gl
                create_journal_entry(
                    tenant=tenant,
                    description=f'Monthly sales summary — {entry_date.strftime("%b %Y")}',
                    reference=ref_rev,
                    date=entry_date,
                    entry_type='Sales',
                    entries=[
                        {'account': bank_gl, 'debit': net_sales + output_vat, 'credit': Decimal('0')},
                        {'account': sales, 'debit': Decimal('0'), 'credit': net_sales},
                        {'account': vat_payable, 'debit': Decimal('0'), 'credit': output_vat},
                    ],
                )
                je_count += 1

            ref_exp = f'SEED-ACC-EXP-{entry_date.strftime("%Y%m")}'
            if not JournalEntry._base_manager.filter(tenant=tenant, reference=ref_exp).exists():
                expense = Decimal(str(random.randint(35000, 72000)))
                create_journal_entry(
                    tenant=tenant,
                    description=f'Operating expenses — {entry_date.strftime("%b %Y")}',
                    reference=ref_exp,
                    date=entry_date,
                    entry_type='Payment',
                    entries=[
                        {'account': admin_exp, 'debit': expense, 'credit': Decimal('0')},
                        {'account': gime_gl, 'debit': Decimal('0'), 'credit': expense},
                    ],
                )
                je_count += 1

            if month_offset % 2 == 0:
                ref_cogs = f'SEED-ACC-COGS-{entry_date.strftime("%Y%m")}'
                if not JournalEntry._base_manager.filter(tenant=tenant, reference=ref_cogs).exists():
                    cogs_amt = Decimal(str(random.randint(28000, 55000)))
                    create_journal_entry(
                        tenant=tenant,
                        description=f'Cost of goods sold — {entry_date.strftime("%b %Y")}',
                        reference=ref_cogs,
                        date=entry_date,
                        entry_type='Adjustment',
                        entries=[
                            {'account': cogs, 'debit': cogs_amt, 'credit': Decimal('0')},
                            {'account': inventory, 'debit': Decimal('0'), 'credit': cogs_amt},
                        ],
                    )
                    je_count += 1

        if not JournalEntry._base_manager.filter(tenant=tenant, reference='SEED-ACC-RCPT-01').exists():
            receipt_amount = Decimal('18500')
            create_journal_entry(
                tenant=tenant,
                description='Customer payment received — seed demo',
                reference='SEED-ACC-RCPT-01',
                date=today - timedelta(days=2),
                entry_type='Receipt',
                entries=[
                    {'account': cash, 'debit': receipt_amount, 'credit': Decimal('0')},
                    {'account': ar, 'debit': Decimal('0'), 'credit': receipt_amount},
                ],
            )
            je_count += 1

        if not JournalEntry._base_manager.filter(tenant=tenant, reference='SEED-ACC-PAY-01').exists():
            payment_amount = Decimal('22000')
            create_journal_entry(
                tenant=tenant,
                description='Supplier payment — seed demo',
                reference='SEED-ACC-PAY-01',
                date=today - timedelta(days=1),
                entry_type='Payment',
                entries=[
                    {'account': ap, 'debit': payment_amount, 'credit': Decimal('0')},
                    {'account': nabil_gl, 'debit': Decimal('0'), 'credit': payment_amount},
                ],
            )
            je_count += 1

        if not JournalEntry._base_manager.filter(tenant=tenant, reference='SEED-ACC-INT-01').exists():
            interest = Decimal('3500')
            create_journal_entry(
                tenant=tenant,
                description='Bank interest income',
                reference='SEED-ACC-INT-01',
                date=today - timedelta(days=5),
                entry_type='Receipt',
                entries=[
                    {'account': gime_gl, 'debit': interest, 'credit': Decimal('0')},
                    {'account': other_income, 'debit': Decimal('0'), 'credit': interest},
                ],
            )
            je_count += 1

        for i in range(1, 3):
            ref = f'SEED-ACC-DRAFT-{i:02d}'
            if JournalEntry._base_manager.filter(tenant=tenant, reference=ref).exists():
                continue
            amount = Decimal(str(random.randint(5000, 12000)))
            entry = JournalEntry.objects.create(
                tenant=tenant,
                entry_number=generate_entry_number(tenant),
                date=today,
                reference=ref,
                description=f'Draft adjustment pending review #{i}',
                type='Manual',
                status='draft',
                total_debit=amount,
                total_credit=amount,
            )
            JournalLine.objects.create(
                tenant=tenant, journal_entry=entry, account=admin_exp,
                description='Pending expense', debit=amount, credit=Decimal('0'),
            )
            JournalLine.objects.create(
                tenant=tenant, journal_entry=entry, account=cash,
                description='Pending expense', debit=Decimal('0'), credit=amount,
            )
            je_count += 1

        if not BankTransaction._base_manager.filter(tenant=tenant, reference__startswith='SEED-ACC-BTX').exists():
            bank_tx_templates = [
                (nabil, 'Credit', 'Customer deposit', Decimal('45000')),
                (nabil, 'Debit', 'Supplier payment', Decimal('22000')),
                (nabil, 'Credit', 'POS settlement', Decimal('18500')),
                (nabil, 'Debit', 'Rent payment', Decimal('35000')),
                (gime, 'Credit', 'Transfer from Nabil', Decimal('50000')),
                (gime, 'Debit', 'Utility bills', Decimal('8500')),
                (gime, 'Credit', 'Interest credit', Decimal('3500')),
                (gime, 'Debit', 'Staff advance', Decimal('12000')),
            ]
            for idx, (bank_acct, tx_type, desc, amount) in enumerate(bank_tx_templates):
                tx_date = today - timedelta(days=random.randint(1, 25))
                ref = f'SEED-ACC-BTX-{idx + 1:03d}'
                prev = BankTransaction._base_manager.filter(bank_account=bank_acct).order_by('-date', '-id').first()
                prev_bal = prev.balance if prev else bank_acct.balance
                if tx_type == 'Credit':
                    new_bal = prev_bal + amount
                    BankTransaction.objects.create(
                        tenant=tenant,
                        bank_account=bank_acct,
                        date=tx_date,
                        reference=ref,
                        description=desc,
                        type='Credit',
                        debit=Decimal('0'),
                        credit=amount,
                        balance=new_bal,
                        reconciled=random.choice([True, False]),
                    )
                else:
                    new_bal = prev_bal - amount
                    BankTransaction.objects.create(
                        tenant=tenant,
                        bank_account=bank_acct,
                        date=tx_date,
                        reference=ref,
                        description=desc,
                        type='Debit',
                        debit=amount,
                        credit=Decimal('0'),
                        balance=new_bal,
                        reconciled=random.choice([True, False]),
                    )
                bank_acct.balance = new_bal
                tx_count += 1
            nabil.save(update_fields=['balance'])
            gime.save(update_fields=['balance'])

        if not VATReturn._base_manager.filter(tenant=tenant, return_number='SEED-VAT-001').exists():
            from accounting.utils import calculate_vat_for_period
            vat = calculate_vat_for_period(tenant, fy_start, min(today, fy_end))
            VATReturn.objects.create(
                tenant=tenant,
                return_number='SEED-VAT-001',
                period=f'Q1 FY {bs_year}/{str(bs_year + 1)[-2:]}',
                from_date=fy_start,
                to_date=min(today, fy_end),
                output_tax=vat['output_tax'],
                input_tax=vat['input_tax'],
                net_payable=vat['net_payable'],
                status='draft',
                notes='Auto-generated seed VAT return',
            )

        for inv in Invoice._base_manager.filter(tenant=tenant, status__in=['Sent', 'Partially Paid', 'Overdue'])[:2]:
            inv.due_date = today + timedelta(days=random.randint(2, 6))
            inv.save(update_fields=['due_date'])

        for inv in PurchaseInvoice._base_manager.filter(
            tenant=tenant, status__in=['Received', 'Partially Paid', 'Overdue'],
        )[:2]:
            inv.due_date = today + timedelta(days=random.randint(3, 7))
            inv.save(update_fields=['due_date'])

        self.stdout.write(
            f'  Accounting demo: {bank_count} bank accounts, {je_count} journal entries, '
            f'{tx_count} bank transactions, VAT return + tax rule'
        )

    def _seed_inventory(self, tenant, user, *, force=False):
        if Product._base_manager.filter(tenant=tenant).exists() and not force:
            self.stdout.write('  Inventory: skipped (already has products)')
            warehouses = list(Warehouse._base_manager.filter(tenant=tenant))
            products = list(Product._base_manager.filter(tenant=tenant))
            if warehouses and products:
                return {'warehouses': warehouses, 'products': products}
            return None

        categories = {}
        for cat_name in ('Groceries', 'Hardware', 'Electrical', 'Stationery', 'Household', 'Beverages', 'Snacks'):
            categories[cat_name] = Category.objects.create(
                tenant=tenant, name=cat_name, description=f'{cat_name} products',
            )

        piece = UnitOfMeasure.objects.create(tenant=tenant, name='Piece', abbreviation='pcs', type='count')
        kg = UnitOfMeasure.objects.create(tenant=tenant, name='Kilogram', abbreviation='kg', type='weight')
        liter = UnitOfMeasure.objects.create(tenant=tenant, name='Liter', abbreviation='L', type='volume')
        meter = UnitOfMeasure.objects.create(tenant=tenant, name='Meter', abbreviation='m', type='length')

        main_wh = Warehouse.objects.create(
            tenant=tenant, name='Main Store', location='New Road, Kathmandu', manager=user, is_active=True,
        )
        branch_wh = Warehouse.objects.create(
            tenant=tenant, name='Bhaktapur Branch', location='Bhaktapur', manager=user, is_active=True,
        )
        warehouses = [main_wh, branch_wh]

        products = []
        today = timezone.now().date()
        low_stock_skus = {'MLK-PWD', 'NDL-PCK', 'TOOL-SCR', 'ELC-WIR25', 'BEV-COLA', 'SNK-CHO', 'GRC-COF', 'HSH-SAN', 'HSH-MSK'}

        for name, sku, cat, cost, sell, qty in PRODUCTS:
            unit = piece
            if 'kg' in sku.lower() or sku.startswith('RICE') or sku.startswith('FLR'):
                unit = kg
            elif sku.startswith('OIL') or sku.startswith('WTR') or sku.startswith('BEV') or sku.startswith('HSH-BLE'):
                unit = liter
            elif sku.startswith('PVC') or sku.startswith('ELC-WIR'):
                unit = meter

            reorder = Decimal('25')
            stock_qty = Decimal(str(qty))
            if sku in low_stock_skus:
                stock_qty = Decimal(str(random.randint(0, 8)))
                reorder = Decimal('15')

            expiry = None
            if sku in ('MLK-PWD', 'NDL-PCK', 'BEV-JUC', 'BEV-ENG', 'SNK-CHP', 'SNK-CHO'):
                expiry = today + timedelta(days=random.randint(15, 120))

            product = Product.objects.create(
                tenant=tenant,
                name=name,
                sku=sku,
                category=categories.get(cat),
                unit=unit,
                cost_price=Decimal(str(cost)),
                selling_price=Decimal(str(sell)),
                reorder_level=reorder,
                expiry_date=expiry,
                status='active',
            )
            products.append(product)
            wh = main_wh if random.random() > 0.25 else branch_wh
            Stock.objects.create(tenant=tenant, product=product, warehouse=wh, quantity=stock_qty)
            if random.random() > 0.7 and wh == main_wh:
                Stock.objects.create(
                    tenant=tenant, product=product, warehouse=branch_wh,
                    quantity=Decimal(str(random.randint(5, 40))),
                )

        self.stdout.write(f'  Inventory: {len(products)} products, {len(warehouses)} warehouses')
        return {'warehouses': warehouses, 'products': products}

    def _seed_inventory_movements(self, tenant, user, inv_ctx):
        products = inv_ctx['products']
        warehouses = inv_ctx['warehouses']
        main_wh = warehouses[0]
        branch_wh = warehouses[1] if len(warehouses) > 1 else main_wh
        created = 0

        for day_offset in range(45, 0, -1):
            for _ in range(random.randint(2, 5)):
                product = random.choice(products)
                wh = random.choice(warehouses)
                mtype = random.choice(['in', 'in', 'out', 'out', 'adjustment'])
                qty = Decimal(str(random.randint(1, 25)))
                StockMovement.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=wh,
                    movement_type=mtype,
                    quantity=qty,
                    reason=random.choice([
                        'Purchase receipt', 'Sales dispatch', 'Cycle count adjustment',
                        'Supplier delivery', 'Customer order', 'Damaged goods write-off',
                    ]),
                    reference_type='SEED',
                    performed_by=user,
                )
                created += 1

        for _ in range(8):
            product = random.choice(products)
            qty = Decimal(str(random.randint(5, 20)))
            StockMovement.objects.create(
                tenant=tenant,
                product=product,
                warehouse=main_wh,
                movement_type='transfer',
                quantity=qty,
                from_warehouse=main_wh,
                to_warehouse=branch_wh,
                reason='Inter-branch transfer',
                reference_type='SEED',
                performed_by=user,
            )
            created += 1

        self.stdout.write(f'  Stock movements: {created} records')

    def _ensure_customers(self, tenant):
        if Customer._base_manager.filter(tenant=tenant).count() >= len(CUSTOMERS):
            return list(Customer._base_manager.filter(tenant=tenant, status='active'))

        Customer._base_manager.filter(tenant=tenant).delete()
        customers = []
        for name, phone, ctype, pan, address in CUSTOMERS:
            customers.append(Customer.objects.create(
                tenant=tenant,
                name=name,
                phone=phone,
                email=f'{name.lower().replace(" ", ".")[:24]}@customer.np',
                pan=pan or None,
                address=address,
                type=ctype,
                credit_limit=Decimal(str(random.randint(50000, 250000))) if ctype == 'Business' else Decimal('10000'),
                payment_terms='Net 30' if ctype == 'Business' else 'Immediate',
                status='active',
                current_balance=Decimal('0'),
            ))
        return customers

    def _seed_sales(self, tenant, user, *, force=False):
        products = list(Product._base_manager.filter(tenant=tenant, status='active'))
        if not products:
            self.stdout.write(self.style.WARNING('  Sales: skipped (no products — seed inventory first)'))
            return

        if SalesOrder._base_manager.filter(tenant=tenant).exists() and not force:
            if Quotation._base_manager.filter(tenant=tenant).exists():
                self.stdout.write('  Sales: skipped (already has sales data)')
                return

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)

        customers = self._ensure_customers(tenant)
        today = timezone.now().date()
        qt_count = so_count = inv_count = pay_count = cn_count = 0

        # Quotations
        qt_statuses = ['Draft', 'Sent', 'Sent', 'Accepted', 'Expired']
        quotations = []
        for i, status in enumerate(qt_statuses):
            customer = customers[i % len(customers)]
            q_date = today - timedelta(days=random.randint(5, 40))
            qt = Quotation.objects.create(
                tenant=tenant,
                quotation_number=f'QT-{tenant.id:03d}-{i + 1:04d}',
                date=q_date,
                customer=customer,
                valid_until=q_date + timedelta(days=random.randint(7, 30)),
                status=status,
                notes='Auto-seeded quotation',
                created_by=user,
            )
            for product in random.sample(products, k=min(3, len(products))):
                QuotationLine.objects.create(
                    tenant=tenant,
                    quotation=qt,
                    product=product,
                    description=product.name,
                    quantity=Decimal(str(random.randint(2, 20))),
                    unit_price=product.selling_price,
                    discount_percent=Decimal(str(random.choice([0, 0, 5, 10]))),
                    tax_percent=Decimal('13'),
                )
            qt.calculate_totals()
            quotations.append(qt)
            qt_count += 1

        # Sales orders (mostly draft/confirmed; a few delivered cash)
        so_configs = [
            ('Draft', 'cash'),
            ('Confirmed', 'cash'),
            ('Confirmed', 'credit'),
            ('Delivered', 'cash'),
            ('Delivered', 'cash'),
            ('Confirmed', 'credit'),
            ('Cancelled', 'cash'),
            ('Delivered', 'credit'),
        ]
        sales_orders = []
        warehouse = Warehouse._base_manager.filter(tenant=tenant, is_active=True).first()

        for i, (status, payment_type) in enumerate(so_configs):
            customer = customers[i % len(customers)]
            order_date = today - timedelta(days=random.randint(3, 45))
            so = SalesOrder.objects.create(
                tenant=tenant,
                order_number=f'SO-{tenant.id:03d}-{i + 1:04d}',
                date=order_date,
                customer=customer,
                reference=f'SEED-SO-{i + 1}',
                status='Draft' if status == 'Delivered' else status,
                payment_type=payment_type,
                notes='Auto-seeded sales order',
                created_by=user,
            )
            for product in random.sample(products, k=min(random.randint(2, 4), len(products))):
                SalesOrderLine.objects.create(
                    tenant=tenant,
                    sales_order=so,
                    product=product,
                    description=product.name,
                    quantity=Decimal(str(random.randint(1, 15))),
                    unit_price=product.selling_price,
                    discount_percent=Decimal('0'),
                    tax_percent=Decimal('13'),
                )
            so.calculate_totals()

            if status == 'Delivered' and payment_type == 'cash' and warehouse:
                from sales.stock_integration import handle_sales_order_status_change
                handle_sales_order_status_change(
                    so, old_status='Draft', new_status='Delivered',
                    performed_by=user, warehouse_id=warehouse.id,
                )
                so.status = 'Delivered'
                so.save(update_fields=['status'])
            elif status == 'Delivered' and payment_type == 'credit':
                so.status = 'Confirmed'
                so.save(update_fields=['status'])
            elif status != 'Draft':
                so.status = status
                so.save(update_fields=['status'])

            sales_orders.append(so)
            so_count += 1

        # Invoices
        inv_configs = [
            ('Sent', 'credit', Decimal('0')),
            ('Partially Paid', 'credit', Decimal('0.35')),
            ('Paid', 'credit', Decimal('1')),
            ('Overdue', 'credit', Decimal('0')),
            ('Paid', 'cash', Decimal('1')),
            ('Sent', 'cash', Decimal('0')),
            ('Partially Paid', 'credit', Decimal('0.5')),
        ]
        invoices = []
        for i, (inv_status, pay_type, paid_ratio) in enumerate(inv_configs):
            so = sales_orders[i] if i < len(sales_orders) else random.choice(sales_orders)
            if so.status == 'Cancelled':
                so = sales_orders[0]
            customer = so.customer
            inv_date = so.date + timedelta(days=random.randint(0, 5))
            amount = so.total if so.total > 0 else Decimal(str(random.randint(3000, 25000)))
            paid = (amount * paid_ratio).quantize(Decimal('0.01'))

            inv = Invoice(
                tenant=tenant,
                invoice_number=f'INV-{tenant.id:03d}-{i + 1:04d}',
                date=inv_date,
                due_date=inv_date + timedelta(days=30),
                customer=customer,
                sales_order=so,
                amount=amount,
                paid_amount=paid,
                payment_type=pay_type,
                status=inv_status,
                created_by=user,
            )
            inv.save()
            invoices.append(inv)
            inv_count += 1

        # Standalone payments against credit customers
        credit_customers = [c for c in customers if c.type == 'Business']
        for i, customer in enumerate(credit_customers[:4]):
            linked = next((inv for inv in invoices if inv.customer_id == customer.id and inv.balance > 0), None)
            amount = linked.balance if linked else Decimal(str(random.randint(2000, 15000)))
            PaymentReceived.objects.create(
                tenant=tenant,
                payment_number=f'PAY-{tenant.id:03d}-{i + 1:05d}',
                date=today - timedelta(days=random.randint(1, 20)),
                customer=customer,
                amount=amount,
                payment_method=random.choice(['cash', 'bank', 'esewa', 'khalti', 'fonepay']),
                reference_number=f'REF-{random.randint(10000, 99999)}',
                invoice=linked,
                notes='Seeded customer payment',
                received_by=user,
            )
            pay_count += 1

        for i, inv in enumerate(invoices[:2]):
            CreditNote.objects.create(
                tenant=tenant,
                credit_note_number=f'CN-{tenant.id:03d}-{i + 1:04d}',
                date=inv.date + timedelta(days=2),
                customer=inv.customer,
                invoice=inv,
                amount=Decimal(str(random.randint(200, 1500))),
                reason='Damaged goods return — seeded demo',
                status='Draft',
                created_by=user,
            )
            cn_count += 1

        self.stdout.write(
            f'  Sales: {len(customers)} customers, {qt_count} quotations, '
            f'{so_count} orders, {inv_count} invoices, {pay_count} payments, {cn_count} credit notes'
        )

    def _ensure_suppliers(self, tenant):
        if Supplier._base_manager.filter(tenant=tenant).count() >= len(SUPPLIERS):
            return list(Supplier._base_manager.filter(tenant=tenant, status='active'))

        Supplier._base_manager.filter(tenant=tenant).delete()
        suppliers = []
        for name, phone, pan, address, bank in SUPPLIERS:
            suppliers.append(Supplier.objects.create(
                tenant=tenant,
                name=name,
                phone=phone,
                email=f'{name.split()[0].lower().replace(".", "")}@supplier.np',
                pan=pan,
                address=address,
                type='Company',
                credit_limit=Decimal(str(random.randint(100000, 500000))),
                payment_terms=random.choice(['Net 15', 'Net 30', 'Net 30', 'Net 60']),
                status='active',
                bank_name=bank,
                bank_account=str(random.randint(1000000000, 9999999999)),
                lead_time_days=random.randint(3, 14),
            ))
        return suppliers

    def _seed_purchase(self, tenant, user, *, force=False):
        products = list(Product._base_manager.filter(tenant=tenant, status='active'))
        if not products:
            self.stdout.write(self.style.WARNING('  Purchase: skipped (no products — seed inventory first)'))
            return

        if PurchaseOrder._base_manager.filter(tenant=tenant).exists() and not force:
            self.stdout.write('  Purchase: skipped (already has purchase orders)')
            return

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)

        suppliers = self._ensure_suppliers(tenant)
        today = timezone.now().date()
        pr_count = po_count = inv_count = dn_count = 0

        # Purchase requests
        pr_statuses = [
            ('Draft', None),
            ('Pending Approval', None),
            ('Approved', user),
            ('Rejected', None),
            ('Converted to PO', user),
            ('Approved', user),
            ('Pending Approval', None),
        ]
        purchase_requests = []
        for i, (status, approver) in enumerate(pr_statuses):
            req_date = today - timedelta(days=random.randint(10, 60))
            pr = PurchaseRequest.objects.create(
                tenant=tenant,
                request_number=f'PR-{tenant.id:03d}-{i + 1:04d}',
                date=req_date,
                requested_by=user,
                department=random.choice(['Warehouse', 'Store Operations', 'Administration', 'Sales']),
                required_by=req_date + timedelta(days=random.randint(5, 20)),
                estimated_amount=Decimal('0'),
                priority=random.choice(['Low', 'Medium', 'High']),
                status=status,
                notes='Auto-seeded purchase request',
            )
            if approver and status in ('Approved', 'Converted to PO'):
                pr.approved_by = approver
                pr.approved_at = timezone.now() - timedelta(days=random.randint(1, 15))
                pr.save(update_fields=['approved_by', 'approved_at'])
            if status == 'Rejected':
                pr.rejection_reason = 'Budget not approved for this quarter'
                pr.save(update_fields=['rejection_reason'])

            line_total = Decimal('0')
            for product in random.sample(products, k=min(3, len(products))):
                qty = Decimal(str(random.randint(5, 50)))
                unit_price = product.cost_price
                PurchaseRequestLine.objects.create(
                    tenant=tenant,
                    purchase_request=pr,
                    product=product,
                    description=f'Restock {product.name}',
                    quantity=qty,
                    estimated_unit_price=unit_price,
                )
                line_total += qty * unit_price
            pr.estimated_amount = line_total
            pr.save(update_fields=['estimated_amount'])
            purchase_requests.append(pr)
            pr_count += 1

        # Purchase orders
        po_statuses = ['Draft', 'Sent', 'Sent', 'Partially Received', 'Received', 'Received', 'Cancelled']
        purchase_orders = []
        for i, status in enumerate(po_statuses):
            supplier = suppliers[i % len(suppliers)]
            po_date = today - timedelta(days=random.randint(5, 50))
            linked_pr = purchase_requests[i] if i < len(purchase_requests) and purchase_requests[i].status == 'Converted to PO' else None
            po = PurchaseOrder.objects.create(
                tenant=tenant,
                po_number=f'PO-{tenant.id:03d}-{i + 1:04d}',
                date=po_date,
                supplier=supplier,
                expected_delivery_date=po_date + timedelta(days=random.randint(3, 14)),
                reference=f'SEED-PO-{i + 1}',
                payment_terms=supplier.payment_terms,
                status=status,
                purchase_request=linked_pr,
                notes='Auto-seeded purchase order',
                created_by=user,
            )
            for product in random.sample(products, k=min(random.randint(2, 5), len(products))):
                qty = Decimal(str(random.randint(10, 80)))
                received = qty if status == 'Received' else (qty * Decimal('0.5') if status == 'Partially Received' else Decimal('0'))
                PurchaseOrderLine.objects.create(
                    tenant=tenant,
                    purchase_order=po,
                    product=product,
                    description=product.name,
                    quantity=qty,
                    unit_price=product.cost_price,
                    tax_percent=Decimal('13'),
                    received_quantity=received,
                )
            po.calculate_totals()
            purchase_orders.append(po)
            po_count += 1

        # Purchase invoices (posts to GL)
        inv_configs = [
            ('Received', Decimal('0')),
            ('Partially Paid', Decimal('0.4')),
            ('Paid', Decimal('1')),
            ('Overdue', Decimal('0')),
            ('Partially Paid', Decimal('0.6')),
            ('Paid', Decimal('1')),
        ]
        invoices = []
        for i, (inv_status, paid_ratio) in enumerate(inv_configs):
            po = purchase_orders[i] if i < len(purchase_orders) else random.choice(purchase_orders)
            if po.status in ('Draft', 'Cancelled'):
                continue
            inv_date = po.date + timedelta(days=random.randint(2, 10))
            amount = po.total
            paid = (amount * paid_ratio).quantize(Decimal('0.01'))
            inv = PurchaseInvoice(
                tenant=tenant,
                invoice_number=f'PI-{tenant.id:03d}-{i + 1:04d}',
                date=inv_date,
                due_date=inv_date + timedelta(days=30),
                supplier=po.supplier,
                purchase_order=po,
                amount=amount,
                paid_amount=paid,
                status=inv_status,
                notes='Auto-seeded supplier invoice',
                created_by=user,
            )
            inv.save()
            invoices.append(inv)
            inv_count += 1

        for i, inv in enumerate(invoices[:2]):
            DebitNote.objects.create(
                tenant=tenant,
                debit_note_number=f'DN-{tenant.id:03d}-{i + 1:04d}',
                date=inv.date + timedelta(days=3),
                supplier=inv.supplier,
                invoice=inv,
                amount=Decimal(str(random.randint(500, 3000))),
                reason=random.choice(['Return', 'Damage', 'Overcharge']),
                description='Seeded debit note for demo',
                status='Draft',
                created_by=user,
            )
            dn_count += 1

        self.stdout.write(
            f'  Purchase: {len(suppliers)} suppliers, {pr_count} requests, '
            f'{po_count} orders, {inv_count} invoices, {dn_count} debit notes'
        )

    def _seed_hardware(self, tenant, user, *, force=False):
        """Seed hardware vertical: HW SKUs, bulk pricing, trade customers, credit orders."""
        hw_exists = Product._base_manager.filter(tenant=tenant, sku__startswith='HW-').exists()
        bulk_exists = BulkPricing._base_manager.filter(tenant=tenant).exists()
        if (hw_exists or bulk_exists) and not force:
            self.stdout.write('  Hardware: skipped (already has hardware data)')
            return

        products = list(Product._base_manager.filter(tenant=tenant, status='active'))
        warehouse = Warehouse._base_manager.filter(tenant=tenant, is_active=True).first()
        if not warehouse:
            self.stdout.write(self.style.WARNING('  Hardware: skipped (no warehouse — seed inventory first)'))
            return

        piece = UnitOfMeasure._base_manager.filter(tenant=tenant, abbreviation='pcs').first()
        meter = UnitOfMeasure._base_manager.filter(tenant=tenant, abbreviation='m').first()
        if not piece:
            piece = UnitOfMeasure.objects.create(
                tenant=tenant, name='Piece', abbreviation='pcs', type='count',
            )
        if not meter:
            meter = UnitOfMeasure.objects.create(
                tenant=tenant, name='Meter', abbreviation='m', type='length',
            )

        categories = {}
        for cat_name in ('Hardware', 'Electrical', 'Plumbing'):
            cat, _ = Category._base_manager.get_or_create(
                tenant=tenant,
                name=cat_name,
                defaults={'description': f'{cat_name} products'},
            )
            categories[cat_name] = cat

        today = timezone.now().date()
        low_stock_skus = {'HW-NAIL-3', 'HW-LOCK-50', 'HW-CPVC-ELB', 'HW-WIR-15'}
        hw_products = []
        prod_count = 0

        for name, sku, cat, cost, sell, qty in HARDWARE_PRODUCTS:
            if Product._base_manager.filter(tenant=tenant, sku=sku).exists():
                continue
            unit = meter if sku.startswith('HW-GI') or sku.startswith('HW-WIR') else piece
            reorder = Decimal('20')
            stock_qty = Decimal(str(qty))
            if sku in low_stock_skus:
                stock_qty = Decimal(str(random.randint(2, 12)))
                reorder = Decimal('25')

            product = Product.objects.create(
                tenant=tenant,
                name=name,
                sku=sku,
                category=categories.get(cat),
                unit=unit,
                cost_price=Decimal(str(cost)),
                selling_price=Decimal(str(sell)),
                reorder_level=reorder,
                status='active',
            )
            Stock.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=stock_qty)
            hw_products.append(product)
            prod_count += 1

        all_hw = list(
            Product._base_manager.filter(
                tenant=tenant,
                status='active',
                category__name__in=('Hardware', 'Electrical', 'Plumbing'),
            )
        )
        if not all_hw:
            all_hw = hw_products or products

        bulk_count = 0
        for product in all_hw[:12]:
            base = product.selling_price
            tiers = [
                (Decimal('1'), Decimal('10'), base),
                (Decimal('11'), Decimal('50'), (base * Decimal('0.95')).quantize(Decimal('0.01'))),
                (Decimal('51'), None, (base * Decimal('0.90')).quantize(Decimal('0.01'))),
            ]
            for min_q, max_q, price in tiers:
                if BulkPricing._base_manager.filter(
                    tenant=tenant, product=product, min_quantity=min_q,
                ).exists():
                    continue
                BulkPricing.objects.create(
                    tenant=tenant,
                    product=product,
                    min_quantity=min_q,
                    max_quantity=max_q,
                    unit_price=price,
                    is_active=True,
                )
                bulk_count += 1

        trade_customers = []
        credit_balances = [45000, 82000, 31500, 128000]
        for i, (name, phone, pan, address) in enumerate(HARDWARE_TRADE_CUSTOMERS):
            customer = Customer._base_manager.filter(tenant=tenant, name=name).first()
            if not customer:
                customer = Customer.objects.create(
                    tenant=tenant,
                    name=name,
                    phone=phone,
                    email=f'{name.lower().replace(" ", ".")[:28]}@trade.np',
                    pan=pan,
                    address=address,
                    type='Business',
                    credit_limit=Decimal(str(random.randint(100000, 250000))),
                    payment_terms='Net 30',
                    status='active',
                    current_balance=Decimal(str(credit_balances[i])),
                )
            else:
                customer.credit_limit = max(customer.credit_limit, Decimal('100000'))
                customer.current_balance = Decimal(str(credit_balances[i]))
                customer.save(update_fields=['credit_limit', 'current_balance'])
            trade_customers.append(customer)

        for customer in Customer._base_manager.filter(tenant=tenant, type='Business').exclude(
            id__in=[c.id for c in trade_customers],
        )[:3]:
            if customer.current_balance <= 0:
                customer.current_balance = Decimal(str(random.randint(8000, 35000)))
                customer.save(update_fields=['current_balance'])

        csp_count = 0
        for customer in trade_customers[:3]:
            for product in random.sample(all_hw, k=min(3, len(all_hw))):
                if CustomerSpecificPrice._base_manager.filter(
                    tenant=tenant, customer=customer, product=product,
                ).exists():
                    continue
                special = (product.selling_price * Decimal('0.92')).quantize(Decimal('0.01'))
                CustomerSpecificPrice.objects.create(
                    tenant=tenant,
                    customer=customer,
                    product=product,
                    unit_price=special,
                    valid_from=today - timedelta(days=30),
                    valid_until=today + timedelta(days=365),
                    is_active=True,
                    notes='Trade customer negotiated rate',
                    created_by=user,
                )
                csp_count += 1

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)

        so_count = 0
        if not SalesOrder._base_manager.filter(tenant=tenant, reference__startswith='SEED-HW-').exists():
            so_configs = [
                ('Confirmed', 'credit'),
                ('Delivered', 'credit'),
                ('Confirmed', 'credit'),
                ('Draft', 'cash'),
                ('Delivered', 'cash'),
                ('Confirmed', 'credit'),
            ]
            existing_so = SalesOrder._base_manager.filter(tenant=tenant).count()
            for i, (status, payment_type) in enumerate(so_configs):
                customer = trade_customers[i % len(trade_customers)]
                order_date = today - timedelta(days=random.randint(2, 35))
                so = SalesOrder.objects.create(
                    tenant=tenant,
                    order_number=f'SO-{tenant.id:03d}-{existing_so + i + 1:04d}',
                    date=order_date,
                    customer=customer,
                    reference=f'SEED-HW-{i + 1}',
                    status='Draft' if status == 'Delivered' else status,
                    payment_type=payment_type,
                    notes='Auto-seeded hardware order',
                    created_by=user,
                )
                hw_sample = random.sample(all_hw, k=min(random.randint(2, 4), len(all_hw)))
                for product in hw_sample:
                    qty = Decimal(str(random.randint(5, 60)))
                    tier_price = BulkPricing.get_price_for_quantity(product, qty)
                    SalesOrderLine.objects.create(
                        tenant=tenant,
                        sales_order=so,
                        product=product,
                        description=product.name,
                        quantity=qty,
                        unit_price=tier_price,
                        discount_percent=Decimal('0'),
                        tax_percent=Decimal('13'),
                    )
                so.calculate_totals()

                if status == 'Delivered' and warehouse:
                    from sales.stock_integration import handle_sales_order_status_change
                    handle_sales_order_status_change(
                        so, old_status='Draft', new_status='Delivered',
                        performed_by=user, warehouse_id=warehouse.id,
                    )
                    so.status = 'Delivered'
                    so.save(update_fields=['status'])
                elif status != 'Draft':
                    so.status = status
                    so.save(update_fields=['status'])
                so_count += 1

        self.stdout.write(
            f'  Hardware: {prod_count} new SKUs, {bulk_count} bulk tiers, '
            f'{len(trade_customers)} trade customers, {csp_count} custom prices, '
            f'{so_count} orders'
        )

    def _ensure_site_manager(self, tenant, user):
        manager = Employee._base_manager.filter(tenant=tenant, status='active').first()
        if manager:
            return manager
        dept, _ = Department._base_manager.get_or_create(
            tenant=tenant,
            name='Administration',
            defaults={'description': 'Office management and compliance'},
        )
        today = timezone.now().date()
        return Employee.objects.create(
            tenant=tenant,
            name='Site Manager',
            dob=date(1988, 6, 15),
            gender='Male',
            phone='9841000001',
            email='site.manager@bishaltrade.np',
            department=dept,
            designation='Site Supervisor',
            employment_type='Full-time',
            join_date=today - timedelta(days=365),
            basic_salary=Decimal('55000'),
            status='active',
        )

    def _ensure_construction_products(self, tenant):
        piece = UnitOfMeasure._base_manager.filter(tenant=tenant, abbreviation='pcs').first()
        kg = UnitOfMeasure._base_manager.filter(tenant=tenant, abbreviation='kg').first()
        if not piece:
            piece = UnitOfMeasure.objects.create(
                tenant=tenant, name='Piece', abbreviation='pcs', type='count',
            )
        if not kg:
            kg = UnitOfMeasure.objects.create(
                tenant=tenant, name='Kilogram', abbreviation='kg', type='weight',
            )

        cat, _ = Category._base_manager.get_or_create(
            tenant=tenant,
            name='Construction Materials',
            defaults={'description': 'Cement, steel, bricks, and aggregates'},
        )

        products = []
        for name, sku, _cat, cost, sell, _qty in CONSTRUCTION_PRODUCTS:
            product = Product._base_manager.filter(tenant=tenant, sku=sku).first()
            if not product:
                unit = kg if sku.startswith('CON-STL') or sku in ('CON-SAND', 'CON-AGG-20') else piece
                product = Product.objects.create(
                    tenant=tenant,
                    name=name,
                    sku=sku,
                    category=cat,
                    unit=unit,
                    cost_price=Decimal(str(cost)),
                    selling_price=Decimal(str(sell)),
                    reorder_level=Decimal('50'),
                    status='active',
                )
            products.append(product)
        return products

    def _seed_construction(self, tenant, user, *, force=False):
        if ConstructionSite._base_manager.filter(
            tenant=tenant, description__startswith='SEED-CON',
        ).exists() and not force:
            self.stdout.write('  Construction: skipped (already has seed sites)')
            return

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)
        manager = self._ensure_site_manager(tenant, user)
        products = self._ensure_construction_products(tenant)
        today = timezone.now().date()

        sites = []
        site_count = worker_count = att_count = log_count = mc_count = eq_count = usage_count = 0

        for name, location, client, budget, status, days_started in CONSTRUCTION_SITES:
            site_wh = Warehouse.objects.create(
                tenant=tenant,
                name=f'{name} — Site Storage',
                location=location,
                manager=user,
                is_active=True,
            )
            for product in products:
                Stock.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=site_wh,
                    quantity=Decimal(str(random.randint(1500, 4000))),
                )

            start_date = today - timedelta(days=days_started) if days_started else today + timedelta(days=14)
            site = ConstructionSite.objects.create(
                tenant=tenant,
                name=name,
                location=location,
                client_name=client,
                allocated_budget=Decimal(str(budget)),
                start_date=start_date,
                estimated_end_date=start_date + timedelta(days=180),
                manager=manager,
                status=status,
                warehouse=site_wh,
                description='SEED-CON demo construction project',
            )
            sites.append(site)
            site_count += 1

        worker_categories = ['mason', 'laborer', 'carpenter', 'electrician', 'plumber', 'supervisor', 'helper']
        workers_by_site = {}
        worker_idx = 0
        for site in sites:
            site_workers = []
            if site.status not in ('active', 'on_hold'):
                continue
            count = 5 if site.status == 'active' else 2
            for _ in range(count):
                first, last = NEPALI_NAMES[worker_idx % len(NEPALI_NAMES)]
                worker_idx += 1
                worker = ConstructionWorker.objects.create(
                    tenant=tenant,
                    name=f'{first} {last}',
                    phone=f'98{random.randint(40000000, 59999999)}',
                    category=random.choice(worker_categories),
                    daily_wage=Decimal(str(random.randint(900, 1800))),
                    assigned_site=site,
                    status='active',
                    id_number=f'SEED-CON-{worker_idx:03d}',
                )
                site_workers.append(worker)
                worker_count += 1
            workers_by_site[site.id] = site_workers

        active_sites = [s for s in sites if s.status == 'active']
        site_activity = {
            'Baneshwor Plaza Extension': {'att_days': 18, 'logs': 9, 'exp_range': (2500, 5500), 'qty_range': (18, 45)},
            'Lalitpur Row Houses': {'att_days': 12, 'logs': 6, 'exp_range': (1200, 3500), 'qty_range': (10, 28)},
            'Pokhara Resort Phase 2': {'att_days': 22, 'logs': 12, 'exp_range': (4500, 9000), 'qty_range': (35, 90)},
        }

        for site in active_sites:
            workers = workers_by_site.get(site.id, [])
            cfg = site_activity.get(site.name, {'att_days': 14, 'logs': 7, 'exp_range': (2000, 5000), 'qty_range': (15, 40)})

            for day_offset in range(cfg['att_days'], 0, -1):
                att_date = today - timedelta(days=day_offset)
                if att_date.weekday() == 6:
                    continue
                for worker in workers:
                    st = random.choices(
                        ['present', 'absent', 'half_day', 'overtime'],
                        weights=[82, 10, 5, 3],
                    )[0]
                    ConstructionAttendance.objects.create(
                        tenant=tenant,
                        worker=worker,
                        site=site,
                        date=att_date,
                        status=st,
                        check_in=time(7, random.randint(0, 45)) if st != 'absent' else None,
                        check_out=time(17, random.randint(0, 30)) if st == 'present' else None,
                        marked_by=user,
                    )
                    att_count += 1

            for day_offset in range(cfg['logs'], 0, -1):
                log_date = today - timedelta(days=day_offset)
                if DailyLog._base_manager.filter(tenant=tenant, site=site, date=log_date).exists():
                    continue
                exp_lo, exp_hi = cfg['exp_range']
                daily_log = DailyLog.objects.create(
                    tenant=tenant,
                    site=site,
                    date=log_date,
                    work_description=(
                        f'Foundation and structural work at {site.name}. '
                        f'{"Heavy monsoon prep." if day_offset % 3 == 0 else "Standard progress."}'
                    ),
                    progress_notes='On schedule per site supervisor report.',
                    weather=random.choice(['Clear', 'Partly cloudy', 'Light rain', 'Overcast']),
                    other_expenses=Decimal(str(random.randint(exp_lo, exp_hi))),
                    other_expenses_description=random.choice([
                        'Equipment fuel and maintenance',
                        'Site safety gear replenishment',
                        'Temporary scaffolding rental',
                    ]),
                    submitted_by=user,
                )
                log_count += 1

                qty_lo, qty_hi = cfg['qty_range']
                for product in random.sample(products, k=min(3, len(products))):
                    qty = Decimal(str(random.randint(qty_lo, qty_hi)))
                    MaterialConsumption.objects.create(
                        tenant=tenant,
                        daily_log=daily_log,
                        site=site,
                        product=product,
                        quantity=qty,
                        unit_cost=product.cost_price,
                    )
                    mc_count += 1

        equipment_items = []
        for i, (eq_name, eq_type, ownership, purchase_cost, rental_day) in enumerate(CONSTRUCTION_EQUIPMENT):
            assigned = active_sites[i % len(active_sites)] if active_sites else None
            eq = Equipment.objects.create(
                tenant=tenant,
                name=eq_name,
                equipment_type=eq_type,
                ownership_type=ownership,
                purchase_cost=Decimal(str(purchase_cost)) if purchase_cost else None,
                rental_cost_per_day=Decimal(str(rental_day)) if rental_day else None,
                assigned_site=assigned,
                status='in_use' if assigned else 'available',
                registration_number=f'BA-{random.randint(1000, 9999)}',
                notes='SEED-CON',
            )
            equipment_items.append(eq)
            eq_count += 1

        for site in active_sites[:2]:
            rented = [e for e in equipment_items if e.ownership_type == 'rented' and e.assigned_site_id == site.id]
            for eq in rented:
                for day_offset in range(5, 0, -1):
                    log_date = today - timedelta(days=day_offset)
                    daily_log = DailyLog._base_manager.filter(tenant=tenant, site=site, date=log_date).first()
                    EquipmentUsageLog.objects.create(
                        tenant=tenant,
                        equipment=eq,
                        site=site,
                        daily_log=daily_log,
                        date=log_date,
                        hours_used=Decimal(str(random.randint(4, 8))),
                    )
                    usage_count += 1

        self.stdout.write(
            f'  Construction: {site_count} sites, {worker_count} workers, '
            f'{att_count} attendance, {log_count} daily logs, {mc_count} material logs, '
            f'{eq_count} equipment, {usage_count} usage logs'
        )

    def _pos_retail_products(self, tenant, warehouse):
        products = list(
            Product._base_manager.filter(
                tenant=tenant,
                status='active',
                category__name__in=('Groceries', 'Beverages', 'Snacks', 'Household', 'Stationery'),
            )
        )
        if not products:
            products = list(Product._base_manager.filter(tenant=tenant, status='active')[:20])
        stocked = []
        for product in products:
            qty = Stock._base_manager.filter(
                tenant=tenant, product=product, warehouse=warehouse,
            ).values_list('quantity', flat=True).first()
            if qty and qty > 10:
                stocked.append(product)
        return stocked or products[:12]

    def _create_seed_pos_transaction(
        self,
        tenant,
        user,
        session,
        warehouse,
        products,
        customers,
        tx_datetime,
        payment_method,
        *,
        status='completed',
    ):
        if len(products) < 1:
            return None

        line_products = random.sample(products, k=min(random.randint(1, 4), len(products)))
        lines_data = []
        for product in line_products:
            qty = Decimal(str(random.randint(1, 3)))
            stock = Stock._base_manager.filter(
                tenant=tenant, product=product, warehouse=warehouse,
            ).first()
            if not stock or stock.quantity < qty:
                continue
            lines_data.append({
                'product': product,
                'quantity': qty,
                'unit_price': product.selling_price,
                'discount_amount': Decimal('0'),
            })

        if not lines_data:
            return None

        bill_discount = Decimal('0')
        if random.random() < 0.15:
            bill_discount = quantize_money(
                sum(l['quantity'] * l['unit_price'] for l in lines_data) * Decimal('0.05')
            )

        amounts = compute_pos_amounts(lines_data, bill_discount)
        customer = None
        customer_name = random.choice(['Walk-in Customer', 'Retail Buyer', 'Local Shopper', ''])
        if payment_method == 'credit':
            credit_customers = [c for c in customers if c.credit_limit > c.current_balance]
            if not credit_customers:
                payment_method = 'cash'
            else:
                customer = random.choice(credit_customers)

        amount_paid = amounts['total']
        change_given = Decimal('0')
        if payment_method == 'cash':
            amount_paid = amounts['total'] + Decimal(str(random.choice([0, 0, 50, 100])))
            change_given = amount_paid - amounts['total']

        txn = POSTransaction.objects.create(
            tenant=tenant,
            session=session,
            customer=customer,
            customer_name=customer_name if not customer else '',
            subtotal=amounts['subtotal'],
            discount_amount=amounts['discount_amount'],
            tax_amount=amounts['tax_amount'],
            total=amounts['total'],
            payment_method=payment_method,
            amount_paid=amount_paid,
            change_given=change_given,
            status=status,
            cashier=user,
            warehouse=warehouse,
            notes='SEED-POS',
        )
        POSTransaction._base_manager.filter(pk=txn.pk).update(date=tx_datetime)

        created_lines = []
        if status == 'completed':
            for line_data in lines_data:
                product = line_data['product']
                line_subtotal = quantize_money(line_data['quantity'] * line_data['unit_price'])
                line = POSTransactionLine.objects.create(
                    tenant=tenant,
                    transaction=txn,
                    product=product,
                    product_name=product.name,
                    product_sku=product.sku,
                    quantity=line_data['quantity'],
                    unit_price=line_data['unit_price'],
                    discount_amount=line_data['discount_amount'],
                    line_total=line_subtotal - line_data['discount_amount'],
                )
                line.product = product
                created_lines.append(line)

                stock = Stock._base_manager.filter(
                    tenant=tenant, product=product, warehouse=warehouse,
                ).first()
                if stock:
                    stock.quantity -= line_data['quantity']
                    stock.save(update_fields=['quantity'])
                    StockMovement.objects.create(
                        tenant=tenant,
                        product=product,
                        warehouse=warehouse,
                        movement_type='out',
                        quantity=line_data['quantity'],
                        reference_type='POSTransaction',
                        reference_id=txn.id,
                        reason=f'POS Sale - {txn.transaction_number}',
                        performed_by=user,
                    )

            from sales.accounting_integration import post_pos_sale
            post_pos_sale(txn, created_lines)

            if payment_method == 'credit' and customer:
                customer.current_balance += amounts['total']
                customer.save(update_fields=['current_balance'])
                CustomerLedger.objects.create(
                    tenant=tenant,
                    customer=customer,
                    date=tx_datetime.date(),
                    transaction_type='sale',
                    reference_type='POSTransaction',
                    reference_number=txn.transaction_number,
                    reference_id=txn.id,
                    debit_amount=amounts['total'],
                    credit_amount=Decimal('0'),
                    running_balance=customer.current_balance,
                    description=f'POS Credit Sale - {txn.transaction_number}',
                )

        return txn

    def _finalize_pos_session(self, session, closed_at):
        from django.db.models import Count, Q, Sum

        transactions = POSTransaction._base_manager.filter(
            tenant=session.tenant,
            session=session,
            status='completed',
        )
        aggregates = transactions.aggregate(
            total_count=Count('id'),
            total_sales=Sum('total'),
            cash_sales=Sum('total', filter=Q(payment_method='cash')),
            card_sales=Sum('total', filter=Q(payment_method='card')),
            esewa_sales=Sum('total', filter=Q(payment_method='esewa')),
            khalti_sales=Sum('total', filter=Q(payment_method='khalti')),
            fonepay_sales=Sum('total', filter=Q(payment_method='fonepay')),
            credit_sales=Sum('total', filter=Q(payment_method='credit')),
        )
        session.total_transactions = aggregates['total_count'] or 0
        session.total_sales = aggregates['total_sales'] or Decimal('0')
        session.cash_sales = aggregates['cash_sales'] or Decimal('0')
        session.card_sales = aggregates['card_sales'] or Decimal('0')
        session.esewa_sales = aggregates['esewa_sales'] or Decimal('0')
        session.khalti_sales = aggregates['khalti_sales'] or Decimal('0')
        session.fonepay_sales = aggregates['fonepay_sales'] or Decimal('0')
        session.credit_sales = aggregates['credit_sales'] or Decimal('0')
        session.expected_cash = session.opening_cash + session.cash_sales
        variance = Decimal(str(random.randint(-150, 200)))
        session.closing_cash = session.expected_cash + variance
        session.cash_variance = variance
        session.closed_at = closed_at
        session.status = 'closed'
        session.save()

    def _seed_pos(self, tenant, user, *, force=False):
        if POSSession._base_manager.filter(tenant=tenant, notes='SEED-POS').exists() and not force:
            self.stdout.write('  POS: skipped (already has seed data)')
            return

        ensure_fiscal_year(tenant)
        seed_default_chart_of_accounts(tenant)

        warehouse = (
            Warehouse._base_manager.filter(tenant=tenant, name='Main Store', is_active=True).first()
            or Warehouse._base_manager.filter(tenant=tenant, is_active=True).first()
        )
        if not warehouse:
            self.stdout.write(self.style.WARNING('  POS: skipped (no warehouse — seed inventory first)'))
            return

        products = self._pos_retail_products(tenant, warehouse)
        if not products:
            self.stdout.write(self.style.WARNING('  POS: skipped (no products with stock)'))
            return

        customers = list(Customer._base_manager.filter(tenant=tenant, status='active'))
        if not customers:
            customers = self._ensure_customers(tenant)

        today = timezone.now().date()
        now = timezone.now()
        snacks = Category._base_manager.filter(tenant=tenant, name='Snacks').first()
        cola = Product._base_manager.filter(tenant=tenant, sku='BEV-COLA').first()

        discount_count = 0
        discount_defs = [
            ('Weekend Bill Discount', 'SEED-BILL5', 'percentage', Decimal('5'), 'bill', None, None, Decimal('500')),
            ('Snacks Promo', 'SEED-SNACK10', 'percentage', Decimal('10'), 'category', snacks, None, Decimal('0')),
            ('Cola Special', 'SEED-COLA5', 'fixed', Decimal('5'), 'item', None, cola, Decimal('0')),
        ]
        for name, code, dtype, dval, apply_to, category, product, min_amt in discount_defs:
            if POSDiscount._base_manager.filter(tenant=tenant, code=code).exists():
                continue
            POSDiscount.objects.create(
                tenant=tenant,
                name=name,
                code=code,
                description=f'Seed POS discount {code}',
                discount_type=dtype,
                discount_value=dval,
                apply_to=apply_to,
                category=category,
                product=product,
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=90),
                min_amount=min_amt,
                is_active=True,
            )
            discount_count += 1

        session_count = txn_count = report_count = 0
        closed_configs = [
            (3, Decimal('5000'), 10),
            (2, Decimal('4500'), 12),
            (1, Decimal('6000'), 8),
        ]

        for days_ago, opening_cash, txn_target in closed_configs:
            opened_at = now - timedelta(days=days_ago, hours=random.randint(7, 9))
            closed_at = opened_at + timedelta(hours=random.randint(8, 11))
            session = POSSession.objects.create(
                tenant=tenant,
                session_number=f'SEED-SES-{days_ago:02d}',
                cashier=user,
                warehouse=warehouse,
                opening_cash=opening_cash,
                status='open',
                notes='SEED-POS',
            )
            POSSession._base_manager.filter(pk=session.pk).update(opened_at=opened_at)
            session_count += 1

            for _ in range(txn_target):
                hour = random.randint(9, 18)
                tx_dt = timezone.make_aware(
                    datetime.combine(
                        today - timedelta(days=days_ago),
                        time(hour, random.randint(0, 59)),
                    )
                )
                method = random.choice(POS_PAYMENT_METHODS)
                if self._create_seed_pos_transaction(
                    tenant, user, session, warehouse, products, customers, tx_dt, method,
                ):
                    txn_count += 1

            self._finalize_pos_session(session, closed_at)

        if not POSSession._base_manager.filter(tenant=tenant, cashier=user, status='open').exists():
            open_session = POSSession.objects.create(
                tenant=tenant,
                session_number='SEED-SES-OPEN',
                cashier=user,
                warehouse=warehouse,
                opening_cash=Decimal('5000'),
                status='open',
                notes='SEED-POS',
            )
            session_count += 1

            for _ in range(6):
                tx_dt = now - timedelta(hours=random.randint(1, 6))
                method = random.choice(POS_PAYMENT_METHODS)
                if self._create_seed_pos_transaction(
                    tenant, user, open_session, warehouse, products, customers, tx_dt, method,
                ):
                    txn_count += 1

        for day_offset in range(7):
            report_date = today - timedelta(days=day_offset)
            day_txns = POSTransaction._base_manager.filter(
                tenant=tenant,
                date__date=report_date,
                status='completed',
                notes='SEED-POS',
            )
            if not day_txns.exists():
                continue
            from django.db.models import Q, Sum

            aggregates = day_txns.aggregate(
                total_items=Sum('lines__quantity'),
                gross_sales=Sum('subtotal'),
                total_discounts=Sum('discount_amount'),
                total_tax=Sum('tax_amount'),
                net_sales=Sum('total'),
                cash_sales=Sum('total', filter=Q(payment_method='cash')),
                card_sales=Sum('total', filter=Q(payment_method='card')),
                esewa_sales=Sum('total', filter=Q(payment_method='esewa')),
                khalti_sales=Sum('total', filter=Q(payment_method='khalti')),
                fonepay_sales=Sum('total', filter=Q(payment_method='fonepay')),
                credit_sales=Sum('total', filter=Q(payment_method='credit')),
            )
            cancelled_count = POSTransaction._base_manager.filter(
                tenant=tenant, date__date=report_date, status='cancelled', notes='SEED-POS',
            ).count()
            POSDailySalesReport.objects.update_or_create(
                tenant=tenant,
                date=report_date,
                cashier=None,
                warehouse=warehouse,
                defaults={
                    'total_transactions': day_txns.count(),
                    'total_items_sold': aggregates['total_items'] or Decimal('0'),
                    'gross_sales': aggregates['gross_sales'] or Decimal('0'),
                    'total_discounts': aggregates['total_discounts'] or Decimal('0'),
                    'total_tax': aggregates['total_tax'] or Decimal('0'),
                    'net_sales': aggregates['net_sales'] or Decimal('0'),
                    'cash_sales': aggregates['cash_sales'] or Decimal('0'),
                    'card_sales': aggregates['card_sales'] or Decimal('0'),
                    'esewa_sales': aggregates['esewa_sales'] or Decimal('0'),
                    'khalti_sales': aggregates['khalti_sales'] or Decimal('0'),
                    'fonepay_sales': aggregates['fonepay_sales'] or Decimal('0'),
                    'credit_sales': aggregates['credit_sales'] or Decimal('0'),
                    'cancelled_transactions': cancelled_count,
                    'refunded_amount': Decimal('0'),
                    'generated_by': user,
                },
            )
            report_count += 1

        self.stdout.write(
            f'  POS: {discount_count} discounts, {session_count} sessions, '
            f'{txn_count} transactions, {report_count} daily reports'
        )

    def _seed_hr(self, tenant, user, count):
        if Employee._base_manager.filter(tenant=tenant).exists():
            self.stdout.write('  HR: skipped (already has employees)')
            return list(Employee._base_manager.filter(tenant=tenant, status='active'))

        departments = []
        for name, desc in DEPARTMENTS:
            departments.append(Department.objects.create(tenant=tenant, name=name, description=desc))

        LeaveType.objects.create(tenant=tenant, name='Annual Leave', days_allowed=18, is_paid=True)
        LeaveType.objects.create(tenant=tenant, name='Sick Leave', days_allowed=12, is_paid=True)
        LeaveType.objects.create(tenant=tenant, name='Unpaid Leave', days_allowed=30, is_paid=False)

        employees = []
        used_names = set()
        today = timezone.now().date()

        for i in range(count):
            first, last = random.choice(NEPALI_NAMES)
            while f'{first} {last}' in used_names:
                first, last = random.choice(NEPALI_NAMES)
            used_names.add(f'{first} {last}')
            dept = departments[i % len(departments)]
            designation = random.choice(DESIGNATIONS[dept.name])
            join_date = today - timedelta(days=random.randint(90, 900))
            salary = Decimal(str(random.randint(18000, 85000)))

            emp = Employee.objects.create(
                tenant=tenant,
                name=f'{first} {last}',
                dob=date(1985 + random.randint(0, 15), random.randint(1, 12), random.randint(1, 28)),
                gender=random.choice(['Male', 'Female']),
                phone=f'98{random.randint(40000000, 59999999)}',
                email=f'{first.lower()}.{last.lower()}{i}@bishaltrade.np',
                department=dept,
                designation=designation,
                employment_type=random.choice(['Full-time', 'Full-time', 'Part-time', 'Contract']),
                join_date=join_date,
                basic_salary=salary,
                status='active' if random.random() > 0.08 else 'inactive',
            )
            employees.append(emp)

        for dept in departments:
            dept_emps = [e for e in employees if e.department_id == dept.id and e.status == 'active']
            if dept_emps:
                dept.head = max(dept_emps, key=lambda e: e.basic_salary)
                dept.save(update_fields=['head'])

        self.stdout.write(f'  HR: {len(departments)} departments, {len(employees)} employees')
        return [e for e in employees if e.status == 'active']

    def _seed_attendance(self, tenant, employees):
        if not employees:
            return
        if Attendance._base_manager.filter(tenant=tenant).exists():
            self.stdout.write('  Attendance: skipped (already exists)')
            return

        today = timezone.now().date()
        statuses = ['present', 'present', 'present', 'present', 'late', 'half-day', 'absent', 'leave']
        created = 0

        for day_offset in range(30, 0, -1):
            att_date = today - timedelta(days=day_offset)
            if att_date.weekday() == 6:
                continue
            for emp in employees:
                st = random.choice(statuses)
                check_in = check_out = None
                if st in ('present', 'late'):
                    hour = 9 if st == 'present' else 10
                    check_in = time(hour, random.randint(0, 45))
                    check_out = time(17, random.randint(0, 30))
                elif st == 'half-day':
                    check_in = time(9, 15)
                    check_out = time(13, 0)

                Attendance.objects.create(
                    tenant=tenant,
                    employee=emp,
                    date=att_date,
                    status=st,
                    check_in=check_in,
                    check_out=check_out,
                )
                created += 1

        self.stdout.write(f'  Attendance: {created} records')

    def _seed_leave(self, tenant, user, employees):
        if not employees:
            return
        if LeaveRequest._base_manager.filter(tenant=tenant).exists():
            self.stdout.write('  Leave: skipped (already exists)')
            return

        leave_types = list(LeaveType._base_manager.filter(tenant=tenant))
        if not leave_types:
            return
        today = timezone.now().date()
        configs = [
            ('pending', 0, 2),
            ('approved', -14, 3),
            ('approved', -30, 2),
            ('rejected', -7, 1),
            ('pending', 5, 4),
            ('approved', -60, 5),
        ]

        for i, (status, start_offset, duration) in enumerate(configs):
            emp = employees[i % len(employees)]
            start = today + timedelta(days=start_offset)
            end = start + timedelta(days=duration - 1)
            lr = LeaveRequest.objects.create(
                tenant=tenant,
                employee=emp,
                leave_type=random.choice(leave_types),
                start_date=start,
                end_date=end,
                reason=random.choice([
                    'Family function in hometown',
                    'Medical appointment',
                    'Personal work',
                    'Dashain vacation',
                    'Child school event',
                ]),
                status=status,
            )
            if status == 'approved':
                lr.approved_by = user
                lr.approved_at = timezone.now() - timedelta(days=abs(start_offset) + 1)
                lr.save(update_fields=['approved_by', 'approved_at'])
            elif status == 'rejected':
                lr.rejection_reason = 'Insufficient staff coverage during peak season'
                lr.save(update_fields=['rejection_reason'])

        self.stdout.write(f'  Leave: {len(configs)} requests')

    def _seed_payroll(self, tenant, employees):
        if not employees:
            return
        if Payroll._base_manager.filter(tenant=tenant).exists():
            self.stdout.write('  Payroll: skipped (already exists)')
            return

        bs_year = current_bs_year()
        months = NEPALI_MONTHS[-3:]
        created = 0

        for month_name in months:
            for emp in employees[:12]:
                amounts = calculate_employee_payroll_amounts(emp, bs_year, month_name, tenant)
                Payroll.objects.create(
                    tenant=tenant,
                    employee=emp,
                    month=month_name,
                    year=bs_year,
                    basic_salary=amounts['basic_salary'],
                    allowances=amounts['allowances'],
                    gross_salary=amounts['gross_salary'],
                    deductions=amounts['deductions'],
                    net_salary=amounts['net_salary'],
                    status=random.choice(['processed', 'processed', 'paid', 'draft']),
                    processed_date=timezone.now() - timedelta(days=random.randint(1, 20)),
                )
                created += 1

        self.stdout.write(f'  Payroll: {created} records')

    def _print_summary(self, tenant):
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write(f'Organization: {tenant.name}')
        self.stdout.write(f'Slug: {tenant.slug}')
        self.stdout.write('HR dashboard: http://localhost:3000/dashboard/hr')
        self.stdout.write('Inventory dashboard: http://localhost:3000/dashboard/inventory')
        self.stdout.write('Purchase dashboard: http://localhost:3000/dashboard/purchase')
        self.stdout.write('Sales dashboard: http://localhost:3000/dashboard/sales')
        self.stdout.write('Hardware dashboard: http://localhost:3000/dashboard/hardware')
        self.stdout.write('Construction dashboard: http://localhost:3000/dashboard/construction')
        self.stdout.write('POS dashboard: http://localhost:3000/dashboard/pos')
        self.stdout.write('Accounting dashboard: http://localhost:3000/dashboard/accounting')
        self.stdout.write('=' * 50)
        for label, model in [
            ('Departments', Department),
            ('Employees', Employee),
            ('Attendance', Attendance),
            ('Leave requests', LeaveRequest),
            ('Payroll', Payroll),
            ('Products', Product),
            ('Warehouses', Warehouse),
            ('Stock lines', Stock),
            ('Stock movements', StockMovement),
            ('Customers', Customer),
            ('Quotations', Quotation),
            ('Sales orders', SalesOrder),
            ('Sales invoices', Invoice),
            ('Payments received', PaymentReceived),
            ('Credit notes', CreditNote),
            ('Suppliers', Supplier),
            ('Purchase requests', PurchaseRequest),
            ('Purchase orders', PurchaseOrder),
            ('Purchase invoices', PurchaseInvoice),
            ('Debit notes', DebitNote),
            ('Bulk pricing rules', BulkPricing),
            ('Customer-specific prices', CustomerSpecificPrice),
            ('Construction sites', ConstructionSite),
            ('Construction workers', ConstructionWorker),
            ('Construction attendance', ConstructionAttendance),
            ('Daily logs', DailyLog),
            ('Material consumption', MaterialConsumption),
            ('Equipment', Equipment),
            ('POS sessions', POSSession),
            ('POS transactions', POSTransaction),
            ('POS discounts', POSDiscount),
            ('POS daily reports', POSDailySalesReport),
            ('GL accounts', Account),
            ('Journal entries', JournalEntry),
            ('Bank accounts', BankAccount),
            ('Bank transactions', BankTransaction),
            ('Tax rules', TaxRule),
            ('VAT returns', VATReturn),
        ]:
            self.stdout.write(f'  {label}: {model._base_manager.filter(tenant=tenant).count()}')
