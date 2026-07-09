from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from utils.models import TenantModel
from users.models import User
from inventory.models import Product


class Customer(TenantModel):
    """Customer model for sales management"""
    TYPE_CHOICES = [
        ('Individual', 'Individual'),
        ('Business', 'Business'),
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
    pan = models.CharField(max_length=20, blank=True, null=True, verbose_name='PAN Number')
    address = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Individual')
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    current_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Current outstanding balance (credit owed by customer)'
    )
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='Immediate')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
    
    def __str__(self):
        return self.name
    
    @property
    def total_orders(self):
        return self.sales_orders.count()
    
    @property
    def total_spent(self):
        return self.sales_orders.filter(status='Delivered').aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0')
    
    @property
    def is_over_limit(self):
        """Check if customer has exceeded credit limit"""
        return self.current_balance > self.credit_limit
    
    @property
    def available_credit(self):
        """Calculate available credit"""
        return max(Decimal('0.00'), self.credit_limit - self.current_balance)



class SalesOrder(TenantModel):
    """Sales Order model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Confirmed', 'Confirmed'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]
    
    PAYMENT_TYPE_CHOICES = [
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ]
    
    order_number = models.CharField(max_length=50)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_orders')
    reference = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='cash')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_sales_orders')
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Sales Order'
        verbose_name_plural = 'Sales Orders'
        unique_together = [['tenant', 'order_number']]
    
    def __str__(self):
        return f"{self.order_number} - {self.customer.name}"
    
    def calculate_totals(self):
        """Calculate subtotal, discount, tax, and total from line items."""
        lines = self.lines.all()
        self.subtotal = sum(line.quantity * line.unit_price for line in lines)
        self.discount = sum(
            line.quantity * line.unit_price * line.discount_percent / Decimal('100')
            for line in lines
        )
        self.tax = sum(
            (line.quantity * line.unit_price - line.quantity * line.unit_price * line.discount_percent / Decimal('100'))
            * line.tax_percent / Decimal('100')
            for line in lines
        )
        self.total = self.subtotal - self.discount + self.tax
        self.save()
    
    @property
    def items_count(self):
        return self.lines.count()
    
    def finalize_on_credit(self, performed_by=None, warehouse_id=None):
        """
        Finalize sales order on credit
        Wrapped in transaction.atomic() for financial integrity
        Creates ledger entry and updates customer balance
        """
        from django.db import transaction
        
        if self.payment_type != 'credit':
            raise ValueError("This order is not a credit sale")
        
        if self.status == 'Delivered':
            raise ValueError("Order is already finalized")
        
        from sales.credit_utils import check_credit_available
        check_credit_available(self.customer, self.total)
        
        with transaction.atomic():
            old_status = self.status
            if old_status == 'Draft':
                from sales.stock_integration import handle_sales_order_status_change
                handle_sales_order_status_change(
                    self,
                    old_status='Draft',
                    new_status='Delivered',
                    performed_by=performed_by,
                    warehouse_id=warehouse_id,
                )

            # Update order status
            self.status = 'Delivered'
            self.save()
            
            # Create ledger entry
            current_balance = self.customer.current_balance
            new_balance = current_balance + self.total
            
            CustomerLedger.objects.create(
                tenant=self.tenant,
                customer=self.customer,
                date=self.date,
                transaction_type='sale',
                reference_type='SalesOrder',
                reference_number=self.order_number,
                reference_id=self.id,
                debit_amount=self.total,
                credit_amount=Decimal('0.00'),
                running_balance=new_balance,
                description=f"Credit sale - Order {self.order_number}"
            )
            
            # Update customer balance
            self.customer.current_balance = new_balance
            self.customer.save()

            from accounting.services import record_credit_sale
            try:
                record_credit_sale(
                    self.customer,
                    self.total,
                    self.order_number,
                    tenant=self.tenant,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"Failed to post GL for credit order {self.order_number}: {e}"
                )



class SalesOrderLine(TenantModel):
    """Sales Order Line Item"""
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    description = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=13, validators=[MinValueValidator(Decimal('0'))])
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Sales Order Line'
        verbose_name_plural = 'Sales Order Lines'
    
    def __str__(self):
        return f"{self.sales_order.order_number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        # Calculate amount before saving
        base_amount = self.quantity * self.unit_price
        discount_amount = base_amount * (self.discount_percent / Decimal('100'))
        taxable_amount = base_amount - discount_amount
        tax_amount = taxable_amount * (self.tax_percent / Decimal('100'))
        self.amount = taxable_amount + tax_amount
        super().save(*args, **kwargs)



class Quotation(TenantModel):
    """Quotation model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Accepted', 'Accepted'),
        ('Expired', 'Expired'),
    ]
    
    quotation_number = models.CharField(max_length=50)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='quotations')
    valid_until = models.DateField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_quotations')
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Quotation'
        verbose_name_plural = 'Quotations'
        # Quotation number should be unique per tenant, not globally
        unique_together = [['tenant', 'quotation_number']]
    
    def __str__(self):
        return f"{self.quotation_number} - {self.customer.name}"
    
    @property
    def items_count(self):
        return self.lines.count()
    
    def calculate_totals(self):
        """Calculate subtotal, discount, tax, and total from line items"""
        lines = self.lines.all()
        self.subtotal = sum(line.quantity * line.unit_price for line in lines)
        self.discount = sum(line.quantity * line.unit_price * line.discount_percent / 100 for line in lines)
        self.tax = sum((line.quantity * line.unit_price - line.quantity * line.unit_price * line.discount_percent / 100) * line.tax_percent / 100 for line in lines)
        self.total = self.subtotal - self.discount + self.tax
        self.save()


class QuotationLine(TenantModel):
    """Quotation line items"""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT)
    description = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Quotation Line'
        verbose_name_plural = 'Quotation Lines'
    
    def save(self, *args, **kwargs):
        # Calculate line amount
        base = self.quantity * self.unit_price
        discount = base * self.discount_percent / 100
        tax = (base - discount) * self.tax_percent / 100
        self.amount = base - discount + tax
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.product.name}"


class Invoice(TenantModel):
    """Invoice model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Partially Paid', 'Partially Paid'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
    ]
    
    PAYMENT_TYPE_CHOICES = [
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ]
    
    invoice_number = models.CharField(max_length=50)
    date = models.DateField()
    due_date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0'))])
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='cash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        unique_together = [['tenant', 'invoice_number']]
    
    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"
    
    @property
    def balance(self):
        return self.amount - self.paid_amount

    def _ar_amount(self):
        """Outstanding amount to post to customer AR."""
        return max(Decimal('0.00'), self.amount - self.paid_amount)

    def _should_post_credit_sale(self, is_new, old_status):
        if self.payment_type != 'credit' or self.status == 'Draft':
            return False
        if self._ar_amount() <= 0:
            return False
        if not (is_new or (old_status == 'Draft' and self.status != 'Draft')):
            return False
        from sales.credit_utils import order_already_on_ledger
        if self.sales_order_id and order_already_on_ledger(self.sales_order):
            return False
        return True
    
    def save(self, *args, **kwargs):
        """
        Create ledger entry for credit sales
        Wrapped in transaction.atomic() for financial integrity
        """
        from django.db import transaction
        
        # Check if this is a new record
        is_new = self.pk is None
        old_status = None
        
        if not is_new:
            # Get old status to detect status changes
            old_invoice = Invoice.objects.get(pk=self.pk)
            old_status = old_invoice.status
        
        # Use atomic transaction for financial integrity
        with transaction.atomic():
            super().save(*args, **kwargs)
            
            if self._should_post_credit_sale(is_new, old_status):
                from sales.credit_utils import check_credit_available
                check_credit_available(self.customer, self._ar_amount())
                self._create_ledger_entry()
                self._update_customer_balance()

            if self.status != 'Draft':
                if is_new or (old_status == 'Draft' and self.status != 'Draft'):
                    from sales.accounting_integration import post_sales_invoice
                    post_sales_invoice(self)
    
    def _create_ledger_entry(self):
        """Create customer ledger entry for credit sale"""
        ar_amount = self._ar_amount()
        if ar_amount <= 0:
            return
        current_balance = self.customer.current_balance
        new_balance = current_balance + ar_amount
        
        CustomerLedger.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            date=self.date,
            transaction_type='sale',
            reference_type='Invoice',
            reference_number=self.invoice_number,
            reference_id=self.id,
            debit_amount=ar_amount,
            credit_amount=Decimal('0.00'),
            running_balance=new_balance,
            description=f"Credit sale - Invoice {self.invoice_number}"
        )
    
    def _update_customer_balance(self):
        """Update customer's current balance for credit sale"""
        ar_amount = self._ar_amount()
        if ar_amount <= 0:
            return
        self.customer.current_balance += ar_amount
        self.customer.save()



class CreditNote(TenantModel):
    """Credit Note model"""
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Issued', 'Issued'),
        ('Applied', 'Applied'),
    ]
    
    credit_note_number = models.CharField(max_length=50)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='credit_notes')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='credit_notes')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_credit_notes')
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Credit Note'
        verbose_name_plural = 'Credit Notes'
        unique_together = [['tenant', 'credit_note_number']]
    
    def __str__(self):
        return f"{self.credit_note_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        from django.db import transaction

        is_new = self.pk is None
        old_status = None
        if not is_new:
            old_status = CreditNote.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.status == 'Issued' and (is_new or old_status == 'Draft'):
                from sales.accounting_integration import post_sales_credit_note
                post_sales_credit_note(self)
                self._apply_to_customer_ledger()
                self._apply_to_invoice()

    def _apply_to_customer_ledger(self):
        """Reduce customer balance and record return in ledger."""
        if CustomerLedger.objects.filter(
            tenant=self.tenant,
            reference_type='CreditNote',
            reference_id=self.id,
        ).exists():
            return
        customer = Customer.objects.select_for_update().get(pk=self.customer_id)
        new_balance = customer.current_balance - self.amount
        CustomerLedger.objects.create(
            tenant=self.tenant,
            customer=customer,
            date=self.date,
            transaction_type='return',
            reference_type='CreditNote',
            reference_number=self.credit_note_number,
            reference_id=self.id,
            debit_amount=Decimal('0.00'),
            credit_amount=self.amount,
            running_balance=new_balance,
            description=f"Credit note {self.credit_note_number} - {self.reason[:80]}",
        )
        customer.current_balance = new_balance
        customer.save(update_fields=['current_balance', 'updated_at'])

    def _apply_to_invoice(self):
        """Apply credit note against the linked invoice."""
        invoice = Invoice.objects.select_for_update().get(pk=self.invoice_id)
        if invoice.paid_amount + self.amount > invoice.amount and invoice.paid_amount >= invoice.amount:
            return
        new_paid = min(invoice.amount, invoice.paid_amount + self.amount)
        new_status = invoice.status
        if new_paid >= invoice.amount:
            new_status = 'Paid'
        elif new_paid > 0:
            new_status = 'Partially Paid'
        Invoice.objects.filter(pk=invoice.pk).update(
            paid_amount=new_paid,
            status=new_status,
        )


class CustomerLedger(TenantModel):
    """
    Customer Ledger - Immutable audit trail of all credit transactions
    Tracks every sale, payment, and return for credit customers
    """
    TRANSACTION_TYPES = [
        ('sale', 'Credit Sale'),
        ('payment', 'Payment Received'),
        ('return', 'Sales Return'),
        ('adjustment', 'Adjustment'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='ledger_entries'
    )
    date = models.DateField()
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Reference to source document
    reference_type = models.CharField(max_length=50, help_text='e.g., Invoice, Payment, CreditNote')
    reference_number = models.CharField(max_length=100, help_text='Document number')
    reference_id = models.IntegerField(null=True, blank=True, help_text='Document ID')
    
    # Double-entry style tracking
    debit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Amount customer owes (increases balance)'
    )
    credit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Amount customer paid (decreases balance)'
    )
    
    # Running balance after this transaction
    running_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Customer balance after this transaction'
    )
    
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'sales_customer_ledger'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'customer', 'date']),
            models.Index(fields=['tenant', 'transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.customer.name} - {self.transaction_type} - {self.date}"


class PaymentReceived(TenantModel):
    """
    Payment Received from Customer
    Automatically creates ledger entry and updates customer balance
    """
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('esewa', 'eSewa'),
        ('khalti', 'Khalti'),
        ('fonepay', 'FonePay'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]
    
    payment_number = models.CharField(max_length=50, db_index=True)
    date = models.DateField()
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='payments_received'
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    
    # Payment details
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Transaction ID, Cheque number, etc.'
    )
    bank_name = models.CharField(max_length=200, blank=True)
    
    # Link to invoice if paying specific invoice
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )
    
    notes = models.TextField(blank=True)
    
    # Audit
    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='received_payments'
    )
    
    class Meta:
        db_table = 'sales_payments_received'
        ordering = ['-date', '-created_at']
        unique_together = [['tenant', 'payment_number']]
        indexes = [
            models.Index(fields=['tenant', 'customer', 'date']),
            models.Index(fields=['tenant', 'payment_method']),
        ]
    
    def __str__(self):
        return f"{self.payment_number} - {self.customer.name} - Rs. {self.amount}"
    
    def save(self, *args, **kwargs):
        """
        Auto-generate payment number and create ledger entry
        """
        from django.db import transaction
        
        # Check if this is a new record
        is_new = self.pk is None
        
        if is_new and not self.payment_number:
            last_payment = (
                PaymentReceived.objects.filter(tenant=self.tenant)
                .select_for_update()
                .order_by('-id')
                .first()
            )
            if last_payment and last_payment.payment_number.startswith('PAY-'):
                try:
                    last_num = int(last_payment.payment_number.split('-')[1])
                    self.payment_number = f"PAY-{last_num + 1:05d}"
                except (ValueError, IndexError):
                    self.payment_number = "PAY-00001"
            else:
                self.payment_number = "PAY-00001"
        
        # Use atomic transaction for financial integrity
        with transaction.atomic():
            super().save(*args, **kwargs)
            
            # Create ledger entry and update customer balance (only for new records)
            if is_new:
                self._create_ledger_entry()
                self._update_customer_balance()

                from sales.accounting_integration import post_payment_received
                post_payment_received(self)
                
                # Update invoice if linked
                if self.invoice:
                    self._update_invoice_payment()
    
    def _create_ledger_entry(self):
        """Create customer ledger entry for this payment"""
        # Get current customer balance
        current_balance = self.customer.current_balance
        new_balance = current_balance - self.amount
        
        CustomerLedger.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            date=self.date,
            transaction_type='payment',
            reference_type='Payment',
            reference_number=self.payment_number,
            reference_id=self.id,
            debit_amount=Decimal('0.00'),
            credit_amount=self.amount,
            running_balance=new_balance,
            description=f"Payment received via {self.get_payment_method_display()}"
        )
    
    def _update_customer_balance(self):
        """Update customer's current balance"""
        self.customer.current_balance -= self.amount
        self.customer.save()
    
    def _update_invoice_payment(self):
        """Update invoice paid amount if payment is linked to invoice."""
        invoice = self.invoice
        new_paid = invoice.paid_amount + self.amount
        new_status = invoice.status
        if new_paid >= invoice.amount:
            new_status = 'Paid'
        elif new_paid > 0:
            new_status = 'Partially Paid'

        Invoice.objects.filter(pk=invoice.pk).update(
            paid_amount=new_paid,
            status=new_status,
        )
