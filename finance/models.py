from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from utils.models import TenantModel


class FinanceAccount(TenantModel):
    """Financial accounts (bank, cash, credit card, investment, loan)"""
    TYPE_CHOICES = [
        ('bank', 'Bank Account'),
        ('cash', 'Cash'),
        ('credit_card', 'Credit Card'),
        ('investment', 'Investment'),
        ('loan', 'Loan'),
    ]
    
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='bank')
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    current_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    description = models.TextField(blank=True)
    bank_name = models.CharField(max_length=255, blank=True, help_text='Bank name for bank accounts')
    account_number = models.CharField(max_length=50, blank=True, help_text='Account/card number')
    
    class Meta:
        db_table = 'finance_accounts'
        ordering = ['name']
        verbose_name = 'Finance Account'
        verbose_name_plural = 'Finance Accounts'
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class FinanceCategory(TenantModel):
    """Income and expense categories"""
    TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='expense')
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'finance_categories'
        ordering = ['type', 'name']
        verbose_name = 'Finance Category'
        verbose_name_plural = 'Finance Categories'
        unique_together = [['tenant', 'name', 'type']]
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class FinanceTransaction(TenantModel):
    """Income, expense, and transfer transactions"""
    TYPE_CHOICES = [
        ('income', 'Transaction In (Income)'),
        ('expense', 'Transaction Out (Expense)'),
    ]
    
    transaction_number = models.CharField(max_length=50, null=True, blank=True)
    date = models.DateField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='expense')
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    account = models.ForeignKey(
        FinanceAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True
    )
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'finance_transactions'
        ordering = ['-date', '-created_at']
        verbose_name = 'Finance Transaction'
        verbose_name_plural = 'Finance Transactions'
        unique_together = [['tenant', 'transaction_number']]
    
    def __str__(self):
        return f"{self.transaction_number} - {self.get_type_display()} Rs.{self.amount}"
    
    def save(self, *args, **kwargs):
        """Update account balance when transaction is saved"""
        is_new = self.pk is None
        
        if is_new:
            # New transaction - adjust account balance
            if self.type == 'income':
                self.account.current_balance += self.amount
            else:  # expense
                self.account.current_balance -= self.amount
            self.account.save()
        
        super().save(*args, **kwargs)


class FinanceBudget(TenantModel):
    """Budget planning"""
    PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.PROTECT,
        related_name='budgets',
        null=True,
        blank=True
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'finance_budgets'
        ordering = ['-start_date']
        verbose_name = 'Finance Budget'
        verbose_name_plural = 'Finance Budgets'
    
    def __str__(self):
        return f"{self.name} - Rs.{self.amount} ({self.get_period_display()})"


class FinanceBill(TenantModel):
    """Bills and recurring payments"""
    RECURRING_CHOICES = [
        ('one-time', 'One-time'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('pending', 'Pending'),
        ('overdue', 'Overdue'),
    ]
    
    bill_number = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    due_date = models.DateField()
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.SET_NULL,
        related_name='bills',
        null=True,
        blank=True
    )
    recurring = models.CharField(max_length=20, choices=RECURRING_CHOICES, default='one-time', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'finance_bills'
        ordering = ['-due_date']
        verbose_name = 'Finance Bill'
        verbose_name_plural = 'Finance Bills'
        unique_together = [['tenant', 'bill_number']]
    
    def __str__(self):
        return f"{self.bill_number} - {self.name} - Rs.{self.amount}"


class PartyLender(TenantModel):
    """Parties/Lenders with optional contact info and photo"""
    name = models.CharField(max_length=255)  # REQUIRED
    pan = models.CharField(max_length=50, blank=True)  # Optional
    mobile = models.CharField(max_length=20, blank=True)  # Optional
    email = models.EmailField(blank=True)  # Optional
    photo = models.ImageField(
        upload_to='finance/parties/',  # Files stored in media/finance/parties/
        null=True,
        blank=True,
        help_text='Party/Lender photo (optional)'
    )
    share_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Unique token for sharing this party ledger'
    )
    
    class Meta:
        db_table = 'finance_parties_lenders'
        ordering = ['name']
        verbose_name = 'Party/Lender'
        verbose_name_plural = 'Parties/Lenders'
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.share_token:
            import uuid
            self.share_token = uuid.uuid4().hex[:32]
        super().save(*args, **kwargs)


class PartyTransaction(TenantModel):
    """Transactions with parties (money In/Out)"""
    DIRECTION_CHOICES = [
        ('in', 'Money In (Received)'),
        ('out', 'Money Out (Given)'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('esewa', 'eSewa'),
        ('bank', 'Bank Transfer'),
    ]
    
    party = models.ForeignKey(
        PartyLender,
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    date = models.DateField()
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        null=True,
        help_text='Payment method (only for Money Out transactions)'
    )
    receipt = models.FileField(
        upload_to='finance/party-receipts/',
        blank=True,
        null=True,
        help_text='Receipt image or PDF (only for Money Out transactions)'
    )
    note = models.TextField(blank=True)
    share_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Unique token for sharing this transaction'
    )
    
    class Meta:
        db_table = 'finance_party_transactions'
        ordering = ['-date', '-created_at']
        verbose_name = 'Party Transaction'
        verbose_name_plural = 'Party Transactions'
    
    def __str__(self):
        return f"{self.party.name} - {self.get_direction_display()} - Rs.{self.amount}"

    def save(self, *args, **kwargs):
        if not self.share_token:
            import uuid
            self.share_token = uuid.uuid4().hex[:32]
        super().save(*args, **kwargs)


class PartyTransactionShare(TenantModel):
    """Shareable read-only links for party transactions/ledger"""
    SHARE_TYPE_CHOICES = [
        ('transaction', 'Single Transaction'),
        ('party_ledger', 'Party Ledger'),
    ]
    
    transaction = models.ForeignKey(
        PartyTransaction,
        on_delete=models.CASCADE,
        related_name='shares',
        blank=True,
        null=True,
        help_text='For single transaction shares'
    )
    party = models.ForeignKey(
        PartyLender,
        on_delete=models.CASCADE,
        related_name='ledger_shares',
        blank=True,
        null=True,
        help_text='For party ledger shares'
    )
    share_type = models.CharField(max_length=20, choices=SHARE_TYPE_CHOICES)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'finance_party_transaction_shares'
        ordering = ['-created_at']
        verbose_name = 'Party Transaction Share'
        verbose_name_plural = 'Party Transaction Shares'
    
    def __str__(self):
        return f"Share - {self.get_share_type_display()}"
