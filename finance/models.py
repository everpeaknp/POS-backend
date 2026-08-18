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
    
    transaction_number = models.CharField(max_length=50)
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
        related_name='transactions'
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
    
    bill_number = models.CharField(max_length=50)
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
    recurring = models.CharField(max_length=20, choices=RECURRING_CHOICES, default='one-time')
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
    
    class Meta:
        db_table = 'finance_parties_lenders'
        ordering = ['name']
        verbose_name = 'Party/Lender'
        verbose_name_plural = 'Parties/Lenders'
    
    def __str__(self):
        return self.name
