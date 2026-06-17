from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from utils.models import TenantModel


class Account(TenantModel):
    """
    Chart of Accounts - Hierarchical account structure
    Supports multi-level account hierarchy with parent-child relationships
    """
    ACCOUNT_TYPES = [
        ('Assets', 'Assets'),
        ('Liabilities', 'Liabilities'),
        ('Equity', 'Equity'),
        ('Income', 'Income'),
        ('Expense', 'Expense'),
    ]
    
    SUB_TYPES = [
        ('Header', 'Header'),
        ('Current Asset', 'Current Asset'),
        ('Fixed Asset', 'Fixed Asset'),
        ('Cash', 'Cash'),
        ('Bank', 'Bank'),
        ('Receivable', 'Receivable'),
        ('Current Liability', 'Current Liability'),
        ('Long-term Liability', 'Long-term Liability'),
        ('Payable', 'Payable'),
        ('Tax', 'Tax'),
        ('Capital', 'Capital'),
        ('Retained Earnings', 'Retained Earnings'),
        ('Revenue', 'Revenue'),
        ('Other Income', 'Other Income'),
        ('COGS', 'COGS'),
        ('Operating', 'Operating'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    code = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    sub_type = models.CharField(max_length=50, choices=SUB_TYPES)
    level = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'accounting_accounts'
        ordering = ['code']
        unique_together = [['tenant', 'code']]
        indexes = [
            models.Index(fields=['tenant', 'type']),
            models.Index(fields=['tenant', 'status']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class JournalEntry(TenantModel):
    """
    Journal Entry Header - Double-entry bookkeeping
    Immutable once posted (can only be reversed)
    """
    ENTRY_TYPES = [
        ('Manual', 'Manual'),
        ('Sales', 'Sales'),
        ('Purchase', 'Purchase'),
        ('Payment', 'Payment'),
        ('Receipt', 'Receipt'),
        ('Adjustment', 'Adjustment'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
    ]
    
    entry_number = models.CharField(max_length=50, unique=True, db_index=True)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='Manual')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    
    # Totals (must balance)
    total_debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Posting information
    posted_by = models.ForeignKey('users.User', on_delete=models.PROTECT, null=True, blank=True, related_name='posted_entries')
    posted_date = models.DateTimeField(null=True, blank=True)
    
    # Reversal tracking
    reversed_by = models.ForeignKey('users.User', on_delete=models.PROTECT, null=True, blank=True, related_name='reversed_entries')
    reversed_date = models.DateTimeField(null=True, blank=True)
    reversal_entry = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='original_entry')
    
    class Meta:
        db_table = 'accounting_journal_entries'
        ordering = ['-date', '-entry_number']
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'type']),
        ]
    
    def __str__(self):
        return f"{self.entry_number} - {self.description}"


class JournalLine(TenantModel):
    """
    Journal Entry Lines - Individual debit/credit entries
    Immutable once parent entry is posted
    """
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    description = models.TextField()
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    class Meta:
        db_table = 'accounting_journal_lines'
        ordering = ['id']
        indexes = [
            models.Index(fields=['tenant', 'account']),
            models.Index(fields=['tenant', 'journal_entry']),
        ]
    
    def __str__(self):
        return f"{self.journal_entry.entry_number} - {self.account.name}"


class BankAccount(TenantModel):
    """
    Bank Account Management
    Tracks company bank accounts for reconciliation
    """
    ACCOUNT_TYPES = [
        ('Current', 'Current Account'),
        ('Savings', 'Savings Account'),
        ('Fixed', 'Fixed Deposit'),
        ('Overdraft', 'Overdraft'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('closed', 'Closed'),
    ]
    
    bank_name = models.CharField(max_length=200)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    branch = models.CharField(max_length=200, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    
    # Link to Chart of Accounts
    gl_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='bank_accounts')
    
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    last_reconciled = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    class Meta:
        db_table = 'accounting_bank_accounts'
        ordering = ['bank_name', 'account_name']
        unique_together = [['tenant', 'account_number']]
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]
    
    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class BankTransaction(TenantModel):
    """
    Bank Transactions for reconciliation
    """
    TRANSACTION_TYPES = [
        ('Opening', 'Opening Balance'),
        ('Credit', 'Credit'),
        ('Debit', 'Debit'),
        ('Transfer', 'Transfer'),
    ]
    
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    reference = models.CharField(max_length=100)
    description = models.TextField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Reconciliation
    reconciled = models.BooleanField(default=False)
    reconciled_date = models.DateField(null=True, blank=True)
    
    # Link to journal entry if applicable
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='bank_transactions')
    
    class Meta:
        db_table = 'accounting_bank_transactions'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'bank_account', 'date']),
            models.Index(fields=['tenant', 'reconciled']),
        ]
    
    def __str__(self):
        return f"{self.bank_account.account_number} - {self.reference}"


class TaxRule(TenantModel):
    """
    Tax Rules - VAT, TDS, etc.
    """
    TAX_TYPES = [
        ('VAT', 'Value Added Tax'),
        ('TDS', 'Tax Deducted at Source'),
        ('Income Tax', 'Income Tax'),
        ('Other', 'Other'),
    ]
    
    APPLICABLE_ON = [
        ('Sales', 'Sales'),
        ('Purchase', 'Purchase'),
        ('Both', 'Both'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TAX_TYPES)
    rate = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    applicable_on = models.CharField(max_length=20, choices=APPLICABLE_ON)
    
    # Link to GL Account for tax liability/asset
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='tax_rules')
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'accounting_tax_rules'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'type']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class VATReturn(TenantModel):
    """
    VAT Return Filing
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('filed', 'Filed'),
        ('paid', 'Paid'),
    ]
    
    return_number = models.CharField(max_length=50, unique=True, db_index=True)
    period = models.CharField(max_length=50)  # e.g., "Magh 2081"
    from_date = models.DateField()
    to_date = models.DateField()
    
    output_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))  # VAT on sales
    input_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))   # VAT on purchases
    net_payable = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))  # output - input
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    filed_date = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'accounting_vat_returns'
        ordering = ['-from_date']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'from_date', 'to_date']),
        ]
    
    def __str__(self):
        return f"{self.return_number} - {self.period}"
