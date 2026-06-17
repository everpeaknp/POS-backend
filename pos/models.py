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
    session_number = models.CharField(max_length=50, unique=True)
    
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
    upi_sales = models.DecimalField(
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
                last_session = POSSession._base_manager.select_for_update().all().order_by('-id').first()
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
    code = models.CharField(max_length=50, unique=True)
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
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI/Digital'),
        ('credit', 'Credit'),
    ]
    
    # Transaction details
    transaction_number = models.CharField(max_length=50, unique=True)
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
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'cashier', 'date']),
            models.Index(fields=['tenant', 'status']),
        ]
    
    def __str__(self):
        return f"POS-{self.transaction_number} - Rs. {self.total}"
    
    def save(self, *args, **kwargs):
        # Generate transaction number if not exists
        if not self.transaction_number:
            from django.db import transaction
            with transaction.atomic():
                last_transaction = POSTransaction._base_manager.select_for_update().all().order_by('-id').first()
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
    
    def save(self, *args, **kwargs):
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
    upi_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
