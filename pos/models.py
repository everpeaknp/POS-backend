"""
POS (Point of Sale) Models for Khata

This module defines models for the retail/POS system including:
- POS Sessions (shift management)
- POS Transactions (sales)
- POS Transaction Lines (items in cart)
- Discounts
- Daily Sales Reports
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from utils.models import TenantModel
from .constants import PAYMENT_METHOD_CHOICES


class POSSession(TenantModel):
    """
    POS Session - represents a cashier's shift/session
    Tracks opening/closing cash and all transactions during the session
    """
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    
    # Session identification
    session_number = models.CharField(max_length=50)
    
    # Cashier
    cashier = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='pos_sessions'
    )
    
    # Warehouse/Store
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_sessions'
    )
    
    # Session timing
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Cash management
    opening_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Cash in drawer at session start'
    )
    closing_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Actual cash counted at session end'
    )
    expected_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Expected cash (opening + cash sales)'
    )
    cash_variance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Difference between expected and actual (can be negative)'
    )
    
    # Session summary (calculated when closed)
    total_transactions = models.IntegerField(default=0)
    total_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    cash_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    card_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    esewa_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    khalti_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    fonepay_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    credit_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'pos_sessions'
        ordering = ['-opened_at']
        unique_together = [['tenant', 'session_number']]
        indexes = [
            models.Index(fields=['tenant', 'cashier', 'opened_at']),
            models.Index(fields=['tenant', 'status']),
        ]
    
    def __str__(self):
        return f"Session {self.session_number} - {self.cashier.username}"
    
    def save(self, *args, **kwargs):
        # Generate session number if not exists
        if not self.session_number:
            from django.db import transaction
            with transaction.atomic():
                last_session = (
                    POSSession._base_manager.filter(tenant=self.tenant)
                    .select_for_update()
                    .order_by('-id')
                    .first()
                )
                if last_session and last_session.session_number.startswith('SES-'):
                    try:
                        last_num = int(last_session.session_number.split('-')[1])
                        self.session_number = f"SES-{str(last_num + 1).zfill(4)}"
                    except:
                        self.session_number = "SES-0001"
                else:
                    self.session_number = "SES-0001"
        
        super().save(*args, **kwargs)


class POSDiscount(TenantModel):
    """
    Discount configurations for POS
    Can be item-level, bill-level, or promotional
    """
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]
    
    APPLY_TO_CHOICES = [
        ('item', 'Item Level'),
        ('bill', 'Bill Level'),
        ('category', 'Category'),
    ]
    
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    apply_to = models.CharField(max_length=20, choices=APPLY_TO_CHOICES)
    
    # For category-specific discounts
    category = models.ForeignKey(
        'inventory.Category',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='pos_discounts'
    )
    
    # For item-specific discounts
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='pos_discounts'
    )
    
    # Validity
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Minimum purchase requirements
    min_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'pos_discounts'
        ordering = ['-created_at']
        unique_together = [['tenant', 'code']]
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def calculate_discount(self, amount):
        """Calculate discount amount based on type"""
        if self.discount_type == 'percentage':
            return amount * (self.discount_value / 100)
        else:
            return min(self.discount_value, amount)


class POSTransaction(TenantModel):
    """
    POS Transaction - represents a completed sale
    """
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('partially_refunded', 'Partially Refunded'),
        ('refunded', 'Fully Refunded'),
        ('cancelled', 'Cancelled'),
    ]

    REFUNDABLE_STATUSES = frozenset({'completed', 'partially_refunded'})
    
    PAYMENT_METHOD_CHOICES = PAYMENT_METHOD_CHOICES
    
    # Transaction details
    transaction_number = models.CharField(max_length=50)
    date = models.DateTimeField(auto_now_add=True)
    
    # Session (optional - links transaction to a session)
    session = models.ForeignKey(
        POSSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    
    # Customer (optional for walk-in customers)
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_transactions'
    )
    customer_name = models.CharField(max_length=255, blank=True, help_text='For walk-in customers')
    
    # Amounts
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    change_given = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    
    # Cashier
    cashier = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='pos_transactions'
    )
    
    # Warehouse/Store
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        related_name='pos_transactions'
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'pos_transactions'
        ordering = ['-date']
        unique_together = [['tenant', 'transaction_number']]
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'cashier', 'date']),
            models.Index(fields=['tenant', 'status']),
        ]
    
    def __str__(self):
        return f"POS-{self.transaction_number} - Rs. {self.total}"
    
    @property
    def is_split_payment(self):
        """True when this transaction has split payment records."""
        return self.payments.exists()

    def save(self, *args, **kwargs):
        # Generate transaction number if not exists
        if not self.transaction_number:
            from django.db import transaction
            with transaction.atomic():
                last_transaction = (
                    POSTransaction._base_manager.filter(tenant=self.tenant)
                    .select_for_update()
                    .order_by('-id')
                    .first()
                )
                if last_transaction and last_transaction.transaction_number.startswith('POS-'):
                    try:
                        last_num = int(last_transaction.transaction_number.split('-')[1])
                        self.transaction_number = f"POS-{str(last_num + 1).zfill(6)}"
                    except:
                        self.transaction_number = "POS-000001"
                else:
                    self.transaction_number = "POS-000001"
        
        super().save(*args, **kwargs)


class POSTransactionLine(TenantModel):
    """
    Line items in a POS transaction
    """
    transaction = models.ForeignKey(
        POSTransaction,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='pos_transaction_lines'
    )
    
    # Product details (snapshot at time of sale)
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=100)
    
    # Quantity and pricing
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Discount on this line
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Line total
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    class Meta:
        db_table = 'pos_transaction_lines'
        ordering = ['id']
    
    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def get_refund_amount(self, refund_quantity):
        """
        Calculate the refund amount for a quantity of this line using the
        transaction line's effective discounted value, not the raw unit price.
        """
        refund_quantity = Decimal(str(refund_quantity))
        if refund_quantity <= 0:
            return Decimal('0.00')

        if self.quantity <= 0:
            return Decimal('0.00')

        line_total = self.line_total or (self.quantity * self.unit_price - self.discount_amount)
        effective_unit_price = line_total / self.quantity
        return effective_unit_price * refund_quantity
    
    def save(self, *args, **kwargs):
        # Ensure product_sku is never empty or None
        if not self.product_sku:
            if self.product and self.product.sku:
                self.product_sku = self.product.sku
            elif self.product:
                self.product_sku = f'PROD-{self.product.id}'
            else:
                self.product_sku = 'UNKNOWN'
        
        # Ensure product_name is never empty or None  
        if not self.product_name and self.product:
            self.product_name = self.product.name
        
        # Calculate line total if not provided
        if not self.line_total:
            subtotal = self.quantity * self.unit_price
            self.line_total = subtotal - self.discount_amount
        
        super().save(*args, **kwargs)


class POSDailySalesReport(TenantModel):
    """
    Daily sales summary report for POS
    Generated automatically at end of day or on-demand
    """
    date = models.DateField()
    
    # Cashier (optional - if report is per cashier)
    cashier = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_daily_reports'
    )
    
    # Warehouse/Store
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_daily_reports'
    )
    
    # Summary metrics
    total_transactions = models.IntegerField(default=0)
    total_items_sold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Revenue breakdown
    gross_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payment method breakdown
    cash_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    esewa_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    khalti_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fonepay_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Cancelled/Refunded
    cancelled_transactions = models.IntegerField(default=0)
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Report metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_pos_reports'
    )
    
    class Meta:
        db_table = 'pos_daily_sales_reports'
        ordering = ['-date']
        unique_together = [['tenant', 'date', 'cashier', 'warehouse']]
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'cashier', 'date']),
        ]
    
    def __str__(self):
        cashier_name = self.cashier.username if self.cashier else 'All Cashiers'
        return f"POS Report - {self.date} - {cashier_name}"


class POSPayment(TenantModel):
    """
    Individual payment entry for a POS transaction.
    Supports split payments (Option A — backward compatible).
    """
    transaction = models.ForeignKey(
        POSTransaction,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='Card last-4, eSewa TXN ID, etc.'
    )

    class Meta:
        db_table = 'pos_payments'
        ordering = ['id']

    def __str__(self):
        return f"{self.payment_method} Rs.{self.amount} for {self.transaction.transaction_number}"


class POSHeldOrder(TenantModel):
    """
    Parked/held orders that can be resumed later.
    """
    session = models.ForeignKey(
        POSSession,
        on_delete=models.CASCADE,
        related_name='held_orders'
    )
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    customer_name = models.CharField(max_length=255, blank=True)
    items = models.JSONField(help_text='Snapshot of cart items')
    notes = models.TextField(blank=True)
    held_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True
    )
    held_at = models.DateTimeField(auto_now_add=True)
    is_resumed = models.BooleanField(default=False)
    resumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'pos_held_orders'
        ordering = ['-held_at']

    def __str__(self):
        return f"Held Order #{self.id} - {self.customer_name or 'Walk-in'}"


class POSCashMovement(TenantModel):
    """
    Manual cash in/out movements during a session.
    """
    MOVEMENT_CHOICES = [
        ('in', 'Cash In'),
        ('out', 'Cash Out'),
    ]

    session = models.ForeignKey(
        POSSession,
        on_delete=models.CASCADE,
        related_name='cash_movements'
    )
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reason = models.CharField(max_length=255)
    performed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True
    )
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pos_cash_movements'
        ordering = ['-performed_at']

    def __str__(self):
        return f"{self.movement_type} Rs.{self.amount} — {self.reason}"


class POSSettings(TenantModel):
    """
    Per-tenant POS configuration (tax rate, receipt text, etc.)
    """
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('13.00')
    )
    tax_label = models.CharField(max_length=50, default='VAT')
    tax_inclusive_pricing = models.BooleanField(default=False)
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(
        blank=True,
        default='Thank you for your purchase!'
    )
    auto_print_receipt = models.BooleanField(default=True)
    allow_zero_price_items = models.BooleanField(default=False)
    require_customer_for_credit = models.BooleanField(default=True)
    
    # Payment method settings
    esewa_enabled = models.BooleanField(default=True)
    esewa_qr = models.ImageField(upload_to='pos/qr/', blank=True, null=True)
    esewa_number = models.CharField(max_length=50, blank=True)
    esewa_name = models.CharField(max_length=100, blank=True)
    
    khalti_enabled = models.BooleanField(default=True)
    khalti_qr = models.ImageField(upload_to='pos/qr/', blank=True, null=True)
    khalti_number = models.CharField(max_length=50, blank=True)
    khalti_name = models.CharField(max_length=100, blank=True)
    
    fonepay_enabled = models.BooleanField(default=True)
    fonepay_qr = models.ImageField(upload_to='pos/qr/', blank=True, null=True)
    fonepay_number = models.CharField(max_length=50, blank=True, null=True)
    
    bank_transfer_enabled = models.BooleanField(default=True)
    bank_qr = models.ImageField(upload_to='pos/qr/', blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_account_name = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'pos_settings'
        unique_together = [['tenant']]

    def __str__(self):
        return f"POS Settings — {self.tenant}"

    @classmethod
    def get_for_tenant(cls, tenant):
        settings, _ = cls._base_manager.get_or_create(tenant=tenant)
        return settings


# ============================================================================
# Feature 1: Refund Tracking
# ============================================================================

class POSRefund(TenantModel):
    """
    Tracks partial or full refunds against a POS transaction.
    Created when a cashier returns items from a completed sale.
    """
    original_transaction = models.ForeignKey(
        POSTransaction,
        on_delete=models.PROTECT,
        related_name='refunds'
    )
    refund_transaction = models.ForeignKey(
        POSTransaction,
        on_delete=models.PROTECT,
        related_name='refund_source',
        null=True,
        blank=True
    )
    reason = models.TextField(blank=True)
    refund_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    refunded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='pos_refunds'
    )
    refunded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pos_refunds'
        ordering = ['-refunded_at']

    def __str__(self):
        return f"Refund for {self.original_transaction.transaction_number}"

    @property
    def refund_number(self):
        return f"REF-{self.id:06d}"

    def get_subtotal_amount(self):
        from django.db.models import Sum
        return self.lines.aggregate(total=Sum('refund_amount'))['total'] or Decimal('0.00')

    def get_total_amount(self):
        from .utils import compute_refund_tax_amount, quantize_money
        txn = self.original_transaction
        subtotal = self.get_subtotal_amount()
        tax_amount = compute_refund_tax_amount(txn, subtotal)
        return quantize_money(subtotal + tax_amount)


class POSRefundLine(TenantModel):
    """
    Individual line items being refunded.
    """
    refund = models.ForeignKey(
        POSRefund,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    original_line = models.ForeignKey(
        POSTransactionLine,
        on_delete=models.PROTECT,
        related_name='refund_lines'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )

    class Meta:
        db_table = 'pos_refund_lines'
        ordering = ['id']

    def __str__(self):
        return f"Refund line: {self.original_line.product_name} x {self.quantity}"


# ============================================================================
# Feature 2: Customer Loyalty / Points
# ============================================================================

class LoyaltyProgram(TenantModel):
    """
    Per-tenant loyalty program configuration.
    """
    points_per_rupee = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('1.0000'),
        help_text='Points earned per Rs 1 spent'
    )
    rupees_per_point = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0.1000'),
        help_text='Rs value of 1 point when redeeming'
    )
    min_redemption_points = models.IntegerField(
        default=100,
        help_text='Minimum points required to redeem'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'pos_loyalty_programs'
        unique_together = [['tenant']]

    def __str__(self):
        return f"Loyalty Program — {self.tenant}"

    @classmethod
    def get_for_tenant(cls, tenant):
        program, _ = cls._base_manager.get_or_create(tenant=tenant)
        return program


class CustomerLoyaltyPoints(TenantModel):
    """
    Loyalty points balance per customer.
    """
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.CASCADE,
        related_name='loyalty_points'
    )
    points_balance = models.IntegerField(default=0)
    total_earned = models.IntegerField(default=0)
    total_redeemed = models.IntegerField(default=0)

    class Meta:
        db_table = 'pos_customer_loyalty_points'
        unique_together = [['tenant', 'customer']]

    def __str__(self):
        return f"{self.customer.name}: {self.points_balance} pts"


class LoyaltyTransaction(TenantModel):
    """
    Audit trail of all loyalty point movements.
    """
    TYPES = [
        ('earn', 'Earn'),
        ('redeem', 'Redeem'),
        ('expire', 'Expire'),
        ('adjust', 'Adjust'),
    ]
    customer_points = models.ForeignKey(
        CustomerLoyaltyPoints,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TYPES)
    points = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'pos_loyalty_transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type}: {self.points} pts — {self.reference}"
