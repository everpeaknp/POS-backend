from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from utils.models import TenantModel
from users.models import User
from inventory.models import Product


class Supplier(TenantModel):
    """Supplier model for purchase management"""
    TYPE_CHOICES = [
        ('Company', 'Company'),
        ('Individual', 'Individual'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    PAYMENT_TERMS_CHOICES = [
        ('Immediate', 'Immediate'),
        ('Net 15', 'Net 15'),
        ('Net 30', 'Net 30'),
        ('Net 60', 'Net 60'),
    ]
    
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    pan = models.CharField(max_length=20, blank=True, null=True, verbose_name='PAN/VAT Number')
    address = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Company')
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='Net 30')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Banking details
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account = models.CharField(max_length=50, blank=True, null=True)
    
    # Lead time in days
    lead_time_days = models.IntegerField(default=7, validators=[MinValueValidator(0)])
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
    
    def __str__(self):
        return self.name
    
    @property
    def total_orders(self):
        """Total number of purchase orders"""
        return self.purchase_orders.count()
    
    @property
    def total_purchased(self):
        """Total amount purchased from this supplier"""
        return self.purchase_orders.filter(
            status__in=['Received', 'Partially Received']
        ).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0')
    
    @property
    def outstanding_amount(self):
        """Outstanding amount to be paid"""
        return self.purchase_invoices.aggregate(
            total=models.Sum(models.F('amount') - models.F('paid_amount'))
        )['total'] or Decimal('0')



class PurchaseRequest(TenantModel):
    """Purchase Request model - 3-step approval workflow"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending Approval', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Converted to PO', 'Converted to PO'),
    ]
    
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]
    
    request_number = models.CharField(max_length=50)
    date = models.DateField()
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='purchase_requests'
    )
    department = models.CharField(max_length=100)
    required_by = models.DateField()
    estimated_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Draft')
    
    # Approval workflow
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_purchase_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Purchase Request'
        verbose_name_plural = 'Purchase Requests'
        unique_together = [['tenant', 'request_number']]
    
    def __str__(self):
        return f"{self.request_number} - {self.department}"
    
    @property
    def items_count(self):
        """Number of line items"""
        return self.lines.count()



class PurchaseRequestLine(TenantModel):
    """Purchase Request Line Item"""
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    description = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    estimated_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    estimated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Purchase Request Line'
        verbose_name_plural = 'Purchase Request Lines'
    
    def __str__(self):
        return f"{self.purchase_request.request_number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        # Calculate estimated amount
        self.estimated_amount = self.quantity * self.estimated_unit_price
        super().save(*args, **kwargs)


class PurchaseOrder(TenantModel):
    """Purchase Order model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Partially Received', 'Partially Received'),
        ('Received', 'Received'),
        ('Cancelled', 'Cancelled'),
    ]
    
    po_number = models.CharField(max_length=50)
    date = models.DateField()
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders'
    )
    expected_delivery_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    payment_terms = models.CharField(max_length=50)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Draft')
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Link to purchase request (optional)
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders'
    )
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_purchase_orders'
    )
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        unique_together = [['tenant', 'po_number']]
    
    def __str__(self):
        return f"{self.po_number} - {self.supplier.name}"
    
    def calculate_totals(self):
        """Calculate order totals from line items"""
        lines = self.lines.all()
        subtotal = Decimal('0')
        tax = Decimal('0')
        
        for line in lines:
            base_amount = line.quantity * line.unit_price
            tax_amount = base_amount * (line.tax_percent / Decimal('100'))
            subtotal += base_amount
            tax += tax_amount
        
        self.subtotal = subtotal
        self.tax = tax
        self.total = subtotal + tax
        self.save()
    
    @property
    def items_count(self):
        """Number of line items"""
        return self.lines.count()



class PurchaseOrderLine(TenantModel):
    """Purchase Order Line Item"""
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    description = models.TextField(blank=True, null=True)
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
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=13,
        validators=[MinValueValidator(Decimal('0'))]
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Receiving tracking
    received_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Purchase Order Line'
        verbose_name_plural = 'Purchase Order Lines'
    
    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        # Calculate amount before saving
        base_amount = self.quantity * self.unit_price
        tax_amount = base_amount * (self.tax_percent / 100)
        self.amount = base_amount + tax_amount
        super().save(*args, **kwargs)


class PurchaseInvoice(TenantModel):
    """Purchase Invoice model"""
    STATUS_CHOICES = [
        ('Received', 'Received'),
        ('Partially Paid', 'Partially Paid'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
    ]
    
    invoice_number = models.CharField(max_length=50)
    date = models.DateField()
    due_date = models.DateField()
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_invoices'
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Received')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_purchase_invoices'
    )
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Purchase Invoice'
        verbose_name_plural = 'Purchase Invoices'
        unique_together = [['tenant', 'invoice_number']]
    
    def __str__(self):
        return f"{self.invoice_number} - {self.supplier.name}"
    
    @property
    def balance(self):
        """Remaining balance to be paid"""
        return self.amount - self.paid_amount

    def _ap_amount(self):
        """Outstanding amount to post to accounts payable."""
        return max(Decimal('0.00'), self.amount - self.paid_amount)

    def save(self, *args, **kwargs):
        from django.db import transaction

        is_new = self.pk is None
        upfront_paid = Decimal('0.00')
        if is_new:
            upfront_paid = Decimal(str(self.paid_amount or 0))

        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.amount and self.amount > 0:
                from purchase.accounting_integration import (
                    post_purchase_invoice,
                    post_purchase_invoice_payment,
                )
                post_purchase_invoice(self)
                if upfront_paid > 0:
                    post_purchase_invoice_payment(self, upfront_paid)


class DebitNote(TenantModel):
    """Debit Note model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Issued', 'Issued'),
        ('Applied', 'Applied'),
    ]
    
    REASON_CHOICES = [
        ('Return', 'Return'),
        ('Overcharge', 'Overcharge'),
        ('Damage', 'Damage'),
        ('Other', 'Other'),
    ]
    
    debit_note_number = models.CharField(max_length=50)
    date = models.DateField()
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='debit_notes'
    )
    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.PROTECT,
        related_name='debit_notes'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_debit_notes'
    )
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Debit Note'
        verbose_name_plural = 'Debit Notes'
        unique_together = [['tenant', 'debit_note_number']]
    
    def __str__(self):
        return f"{self.debit_note_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        from django.db import transaction

        is_new = self.pk is None
        old_status = None
        if not is_new:
            old_status = DebitNote.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.status == 'Issued' and (is_new or old_status == 'Draft'):
                from purchase.accounting_integration import post_purchase_debit_note
                post_purchase_debit_note(self)
                self._apply_to_invoice()

    def _apply_to_invoice(self):
        """Reduce payable on the linked invoice when debit note is issued."""
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=self.invoice_id)
        if self.supplier_id != invoice.supplier_id:
            return
        if self.amount > invoice.balance:
            raise ValueError('Debit note amount exceeds invoice balance')
        new_paid = min(invoice.amount, invoice.paid_amount + self.amount)
        new_status = invoice.status
        if new_paid >= invoice.amount:
            new_status = 'Paid'
        elif new_paid > 0:
            new_status = 'Partially Paid'
        PurchaseInvoice.objects.filter(pk=invoice.pk).update(
            paid_amount=new_paid,
            status=new_status,
        )
        DebitNote.objects.filter(pk=self.pk).update(status='Applied')
        self.status = 'Applied'
