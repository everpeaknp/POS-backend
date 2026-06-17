from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal

from .models import Account, JournalEntry, JournalLine, BankAccount, BankTransaction, TaxRule, VATReturn
from .serializers import (
    AccountSerializer, JournalEntrySerializer, BankAccountSerializer,
    BankTransactionSerializer, TaxRuleSerializer, VATReturnSerializer
)


@extend_schema_view(
    list=extend_schema(tags=['Accounting - Chart of Accounts'], summary='List all accounts'),
    retrieve=extend_schema(tags=['Accounting - Chart of Accounts'], summary='Get account details'),
    create=extend_schema(tags=['Accounting - Chart of Accounts'], summary='Create new account'),
    update=extend_schema(tags=['Accounting - Chart of Accounts'], summary='Update account'),
    partial_update=extend_schema(tags=['Accounting - Chart of Accounts'], summary='Partially update account'),
    destroy=extend_schema(tags=['Accounting - Chart of Accounts'], summary='Delete account'),
)
class AccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Chart of Accounts
    Supports hierarchical account structure
    """
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'sub_type', 'status', 'parent']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'balance', 'created_at']
    ordering = ['code']
    
    def get_queryset(self):
        return Account.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Accounting - Chart of Accounts'],
        summary='Get account tree structure',
        description='Returns hierarchical tree of accounts'
    )
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Get hierarchical account tree"""
        accounts = self.get_queryset().filter(level=0)
        serializer = self.get_serializer(accounts, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['Accounting - Chart of Accounts'],
        summary='Get account ledger',
        description='Returns all journal lines for this account',
        parameters=[
            OpenApiParameter('from_date', type=str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('to_date', type=str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """Get ledger entries for an account"""
        account = self.get_object()
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        lines = JournalLine.objects.filter(
            tenant=request.user.tenant,
            account=account,
            journal_entry__status='posted'
        )
        
        if from_date:
            lines = lines.filter(journal_entry__date__gte=from_date)
        if to_date:
            lines = lines.filter(journal_entry__date__lte=to_date)
        
        lines = lines.select_related('journal_entry').order_by('journal_entry__date', 'id')
        
        # Calculate running balance
        balance = Decimal('0.00')
        ledger_data = []
        
        for line in lines:
            balance += line.debit - line.credit
            ledger_data.append({
                'date': line.journal_entry.date,
                'reference': line.journal_entry.entry_number,
                'description': line.description,
                'debit': line.debit,
                'credit': line.credit,
                'balance': balance,
                'source': line.journal_entry.type
            })
        
        return Response(ledger_data)
    
    @extend_schema(
        tags=['Accounting - Reports'],
        summary='Get trial balance',
        description='Returns trial balance report showing debit and credit balances for all accounts',
        parameters=[
            OpenApiParameter('as_of_date', type=str, description='As of date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Get trial balance report"""
        as_of_date = request.query_params.get('as_of_date')
        
        # Get all active accounts with level > 0 (leaf accounts)
        accounts = self.get_queryset().filter(status='active', level__gt=0).order_by('type', 'code')
        
        trial_balance_data = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        
        for account in accounts:
            # Calculate balance for this account up to as_of_date
            lines = JournalLine.objects.filter(
                tenant=request.user.tenant,
                account=account,
                journal_entry__status='posted'
            )
            
            if as_of_date:
                lines = lines.filter(journal_entry__date__lte=as_of_date)
            
            # Calculate net balance
            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            
            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            balance = debit_sum - credit_sum
            
            # Determine if this account type normally has debit or credit balance
            is_debit_type = account.type in ['Assets', 'Expense']
            
            # Only include accounts with non-zero balance
            if balance != 0:
                if is_debit_type:
                    debit_balance = abs(balance) if balance > 0 else Decimal('0.00')
                    credit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                else:
                    debit_balance = abs(balance) if balance > 0 else Decimal('0.00')
                    credit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                
                # For normal balance side
                if is_debit_type and balance > 0:
                    debit_balance = balance
                    credit_balance = Decimal('0.00')
                elif is_debit_type and balance < 0:
                    debit_balance = Decimal('0.00')
                    credit_balance = abs(balance)
                elif not is_debit_type and balance > 0:
                    debit_balance = balance
                    credit_balance = Decimal('0.00')
                else:
                    debit_balance = Decimal('0.00')
                    credit_balance = abs(balance)
                
                total_debit += debit_balance
                total_credit += credit_balance
                
                trial_balance_data.append({
                    'id': account.id,
                    'code': account.code,
                    'name': account.name,
                    'type': account.type,
                    'level': account.level,
                    'debit': debit_balance,
                    'credit': credit_balance,
                    'balance': balance
                })
        
        return Response({
            'as_of_date': as_of_date,
            'accounts': trial_balance_data,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'is_balanced': abs(total_debit - total_credit) < Decimal('0.01')
        })
    
    @extend_schema(
        tags=['Accounting - Reports'],
        summary='Get profit & loss statement',
        description='Returns profit & loss statement showing income, expenses, and net profit',
        parameters=[
            OpenApiParameter('from_date', type=str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('to_date', type=str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'])
    def profit_loss(self, request):
        """Get profit & loss statement"""
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        # Get all active income and expense accounts
        accounts = self.get_queryset().filter(
            status='active',
            level__gt=0,
            type__in=['Income', 'Expense']
        ).order_by('type', 'code')
        
        income_accounts = []
        expense_accounts = []
        total_income = Decimal('0.00')
        total_expenses = Decimal('0.00')
        
        for account in accounts:
            # Calculate balance for this account within date range
            lines = JournalLine.objects.filter(
                tenant=request.user.tenant,
                account=account,
                journal_entry__status='posted'
            )
            
            if from_date:
                lines = lines.filter(journal_entry__date__gte=from_date)
            if to_date:
                lines = lines.filter(journal_entry__date__lte=to_date)
            
            # Calculate net balance
            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            
            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            
            # For Income accounts: credit increases income (normal credit balance)
            # For Expense accounts: debit increases expense (normal debit balance)
            if account.type == 'Income':
                amount = credit_sum - debit_sum  # Net credit is income
                if amount != 0:
                    total_income += amount
                    income_accounts.append({
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'sub_type': account.sub_type,
                        'amount': amount
                    })
            else:  # Expense
                amount = debit_sum - credit_sum  # Net debit is expense
                if amount != 0:
                    total_expenses += amount
                    expense_accounts.append({
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'sub_type': account.sub_type,
                        'amount': amount
                    })
        
        # Calculate net profit/loss
        net_profit = total_income - total_expenses
        
        # Calculate margins
        income_margin = (net_profit / total_income * 100) if total_income > 0 else Decimal('0.00')
        
        return Response({
            'from_date': from_date,
            'to_date': to_date,
            'income': {
                'accounts': income_accounts,
                'total': total_income
            },
            'expenses': {
                'accounts': expense_accounts,
                'total': total_expenses
            },
            'net_profit': net_profit,
            'net_margin': income_margin
        })
    
    @extend_schema(
        tags=['Accounting - Reports'],
        summary='Get balance sheet',
        description='Returns balance sheet showing assets, liabilities, and equity',
        parameters=[
            OpenApiParameter('as_of_date', type=str, description='As of date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'])
    def balance_sheet(self, request):
        """Get balance sheet report"""
        as_of_date = request.query_params.get('as_of_date')
        
        # Get all active accounts with level > 0 (leaf accounts)
        accounts = self.get_queryset().filter(
            status='active',
            level__gt=0,
            type__in=['Assets', 'Liabilities', 'Equity']
        ).order_by('type', 'sub_type', 'code')
        
        assets_data = {'current': [], 'fixed': [], 'other': []}
        liabilities_data = {'current': [], 'long_term': [], 'other': []}
        equity_data = []
        
        total_assets = Decimal('0.00')
        total_liabilities = Decimal('0.00')
        total_equity = Decimal('0.00')
        
        for account in accounts:
            # Calculate balance for this account up to as_of_date
            lines = JournalLine.objects.filter(
                tenant=request.user.tenant,
                account=account,
                journal_entry__status='posted'
            )
            
            if as_of_date:
                lines = lines.filter(journal_entry__date__lte=as_of_date)
            
            # Calculate net balance
            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            
            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            balance = debit_sum - credit_sum
            
            # Skip accounts with zero balance
            if balance == 0:
                continue
            
            account_data = {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'sub_type': account.sub_type,
                'amount': abs(balance)  # Always show positive amounts
            }
            
            # Categorize by type and sub_type
            if account.type == 'Assets':
                # Assets have normal debit balance
                if balance < 0:
                    # Contra asset - reduce total
                    account_data['amount'] = -abs(balance)
                
                total_assets += balance
                
                # Categorize by sub_type
                if 'Current' in account.sub_type or 'Cash' in account.sub_type or 'Receivable' in account.sub_type:
                    assets_data['current'].append(account_data)
                elif 'Fixed' in account.sub_type or 'Property' in account.sub_type or 'Equipment' in account.sub_type:
                    assets_data['fixed'].append(account_data)
                else:
                    assets_data['other'].append(account_data)
                    
            elif account.type == 'Liabilities':
                # Liabilities have normal credit balance (negative in our calculation)
                amount = abs(balance)
                if balance > 0:
                    # Contra liability
                    amount = -balance
                
                total_liabilities += abs(balance)
                
                account_data['amount'] = amount
                
                # Categorize by sub_type
                if 'Current' in account.sub_type or 'Payable' in account.sub_type:
                    liabilities_data['current'].append(account_data)
                elif 'Long' in account.sub_type or 'Term' in account.sub_type:
                    liabilities_data['long_term'].append(account_data)
                else:
                    liabilities_data['other'].append(account_data)
                    
            elif account.type == 'Equity':
                # Equity has normal credit balance (negative in our calculation)
                amount = abs(balance)
                if balance > 0:
                    # Contra equity
                    amount = -balance
                
                total_equity += abs(balance)
                
                account_data['amount'] = amount
                equity_data.append(account_data)
        
        # Calculate totals for each category
        total_current_assets = sum(acc['amount'] for acc in assets_data['current'])
        total_fixed_assets = sum(acc['amount'] for acc in assets_data['fixed'])
        total_other_assets = sum(acc['amount'] for acc in assets_data['other'])
        
        total_current_liabilities = sum(acc['amount'] for acc in liabilities_data['current'])
        total_long_term_liabilities = sum(acc['amount'] for acc in liabilities_data['long_term'])
        total_other_liabilities = sum(acc['amount'] for acc in liabilities_data['other'])
        
        total_liab_equity = total_liabilities + total_equity
        is_balanced = abs(total_assets - total_liab_equity) < Decimal('0.01')
        
        return Response({
            'as_of_date': as_of_date,
            'assets': {
                'current': assets_data['current'],
                'fixed': assets_data['fixed'],
                'other': assets_data['other'],
                'total_current': total_current_assets,
                'total_fixed': total_fixed_assets,
                'total_other': total_other_assets,
                'total': total_assets
            },
            'liabilities': {
                'current': liabilities_data['current'],
                'long_term': liabilities_data['long_term'],
                'other': liabilities_data['other'],
                'total_current': total_current_liabilities,
                'total_long_term': total_long_term_liabilities,
                'total_other': total_other_liabilities,
                'total': total_liabilities
            },
            'equity': {
                'accounts': equity_data,
                'total': total_equity
            },
            'total_liabilities_equity': total_liab_equity,
            'is_balanced': is_balanced
        })


@extend_schema_view(
    list=extend_schema(tags=['Accounting - Journal Entries'], summary='List all journal entries'),
    retrieve=extend_schema(tags=['Accounting - Journal Entries'], summary='Get journal entry details'),
    create=extend_schema(tags=['Accounting - Journal Entries'], summary='Create new journal entry'),
    update=extend_schema(tags=['Accounting - Journal Entries'], summary='Update journal entry (draft only)'),
    partial_update=extend_schema(tags=['Accounting - Journal Entries'], summary='Partially update journal entry'),
    destroy=extend_schema(tags=['Accounting - Journal Entries'], summary='Delete journal entry (draft only)'),
)
class JournalEntryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Journal Entries
    Supports double-entry bookkeeping with immutable posted entries
    """
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'type', 'date']
    search_fields = ['entry_number', 'reference', 'description']
    ordering_fields = ['date', 'entry_number', 'created_at']
    ordering = ['-date', '-entry_number']
    
    def get_queryset(self):
        return JournalEntry.objects.filter(tenant=self.request.user.tenant).prefetch_related('lines__account')
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != 'draft':
            return Response(
                {'error': 'Only draft entries can be deleted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(
        tags=['Accounting - Journal Entries'],
        summary='Post journal entry',
        description='Post a draft journal entry (makes it immutable)'
    )
    @action(detail=True, methods=['post'])
    def post_entry(self, request, pk=None):
        """Post a journal entry"""
        entry = self.get_object()
        
        if entry.status != 'draft':
            return Response(
                {'error': 'Only draft entries can be posted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update account balances
        for line in entry.lines.all():
            account = line.account
            if account.type in ['Assets', 'Expense']:
                account.balance += line.debit - line.credit
            else:  # Liabilities, Equity, Income
                account.balance += line.credit - line.debit
            account.save()
        
        # Mark as posted
        entry.status = 'posted'
        entry.posted_by = request.user
        entry.posted_date = timezone.now()
        entry.save()
        
        serializer = self.get_serializer(entry)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['Accounting - Journal Entries'],
        summary='Reverse journal entry',
        description='Create a reversal entry for a posted journal entry'
    )
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a posted journal entry"""
        entry = self.get_object()
        
        if entry.status != 'posted':
            return Response(
                {'error': 'Only posted entries can be reversed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create reversal entry
        reversal_data = {
            'date': request.data.get('date', timezone.now().date()),
            'description': f"Reversal of {entry.entry_number}: {entry.description}",
            'type': 'Adjustment',
            'tenant': request.user.tenant,
        }
        
        reversal_entry = JournalEntry.objects.create(**reversal_data)
        
        # Generate entry number
        last_entry = JournalEntry.objects.filter(tenant=request.user.tenant).order_by('-id').first()
        if last_entry and last_entry.entry_number.startswith('JE-'):
            try:
                last_num = int(last_entry.entry_number.split('-')[1])
                reversal_entry.entry_number = f"JE-{last_num + 1:04d}"
            except:
                reversal_entry.entry_number = f"JE-0001"
        else:
            reversal_entry.entry_number = f"JE-0001"
        
        # Create reversed lines (swap debit/credit)
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        
        for line in entry.lines.all():
            JournalLine.objects.create(
                journal_entry=reversal_entry,
                tenant=request.user.tenant,
                account=line.account,
                description=line.description,
                debit=line.credit,  # Swap
                credit=line.debit,  # Swap
            )
            total_debit += line.credit
            total_credit += line.debit
        
        reversal_entry.total_debit = total_debit
        reversal_entry.total_credit = total_credit
        reversal_entry.status = 'posted'
        reversal_entry.posted_by = request.user
        reversal_entry.posted_date = timezone.now()
        reversal_entry.save()
        
        # Update original entry
        entry.status = 'reversed'
        entry.reversed_by = request.user
        entry.reversed_date = timezone.now()
        entry.reversal_entry = reversal_entry
        entry.save()
        
        # Update account balances
        for line in reversal_entry.lines.all():
            account = line.account
            if account.type in ['Assets', 'Expense']:
                account.balance += line.debit - line.credit
            else:
                account.balance += line.credit - line.debit
            account.save()
        
        serializer = self.get_serializer(reversal_entry)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['Accounting - Bank Accounts'], summary='List all bank accounts'),
    retrieve=extend_schema(tags=['Accounting - Bank Accounts'], summary='Get bank account details'),
    create=extend_schema(tags=['Accounting - Bank Accounts'], summary='Create new bank account'),
    update=extend_schema(tags=['Accounting - Bank Accounts'], summary='Update bank account'),
    partial_update=extend_schema(tags=['Accounting - Bank Accounts'], summary='Partially update bank account'),
    destroy=extend_schema(tags=['Accounting - Bank Accounts'], summary='Delete bank account'),
)
class BankAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for Bank Accounts"""
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'status']
    search_fields = ['bank_name', 'account_name', 'account_number']
    ordering_fields = ['bank_name', 'balance', 'created_at']
    ordering = ['bank_name']
    
    def get_queryset(self):
        return BankAccount.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Accounting - Bank Accounts'],
        summary='Get bank statement',
        description='Returns all transactions for this bank account'
    )
    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Get bank statement"""
        bank_account = self.get_object()
        transactions = BankTransaction.objects.filter(
            tenant=request.user.tenant,
            bank_account=bank_account
        ).order_by('-date', '-id')
        
        serializer = BankTransactionSerializer(transactions, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['Accounting - Bank Transactions'], summary='List all bank transactions'),
    retrieve=extend_schema(tags=['Accounting - Bank Transactions'], summary='Get transaction details'),
    create=extend_schema(tags=['Accounting - Bank Transactions'], summary='Create new transaction'),
    update=extend_schema(tags=['Accounting - Bank Transactions'], summary='Update transaction'),
    partial_update=extend_schema(tags=['Accounting - Bank Transactions'], summary='Partially update transaction'),
    destroy=extend_schema(tags=['Accounting - Bank Transactions'], summary='Delete transaction'),
)
class BankTransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for Bank Transactions"""
    serializer_class = BankTransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['bank_account', 'type', 'reconciled']
    search_fields = ['reference', 'description']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']
    
    def get_queryset(self):
        return BankTransaction.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Accounting - Bank Transactions'],
        summary='Reconcile transaction',
        description='Mark transaction as reconciled'
    )
    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Reconcile a transaction"""
        transaction = self.get_object()
        transaction.reconciled = True
        transaction.reconciled_date = timezone.now().date()
        transaction.save()
        
        serializer = self.get_serializer(transaction)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['Accounting - Tax Rules'], summary='List all tax rules'),
    retrieve=extend_schema(tags=['Accounting - Tax Rules'], summary='Get tax rule details'),
    create=extend_schema(tags=['Accounting - Tax Rules'], summary='Create new tax rule'),
    update=extend_schema(tags=['Accounting - Tax Rules'], summary='Update tax rule'),
    partial_update=extend_schema(tags=['Accounting - Tax Rules'], summary='Partially update tax rule'),
    destroy=extend_schema(tags=['Accounting - Tax Rules'], summary='Delete tax rule'),
)
class TaxRuleViewSet(viewsets.ModelViewSet):
    """ViewSet for Tax Rules"""
    serializer_class = TaxRuleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'applicable_on', 'status']
    search_fields = ['name']
    ordering_fields = ['name', 'rate', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        return TaxRule.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(tags=['Accounting - VAT Returns'], summary='List all VAT returns'),
    retrieve=extend_schema(tags=['Accounting - VAT Returns'], summary='Get VAT return details'),
    create=extend_schema(tags=['Accounting - VAT Returns'], summary='Create new VAT return'),
    update=extend_schema(tags=['Accounting - VAT Returns'], summary='Update VAT return'),
    partial_update=extend_schema(tags=['Accounting - VAT Returns'], summary='Partially update VAT return'),
    destroy=extend_schema(tags=['Accounting - VAT Returns'], summary='Delete VAT return'),
)
class VATReturnViewSet(viewsets.ModelViewSet):
    """ViewSet for VAT Returns"""
    serializer_class = VATReturnSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['return_number', 'period']
    ordering_fields = ['from_date', 'created_at']
    ordering = ['-from_date']
    
    def get_queryset(self):
        return VATReturn.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Accounting - VAT Returns'],
        summary='File VAT return',
        description='Mark VAT return as filed'
    )
    @action(detail=True, methods=['post'])
    def file(self, request, pk=None):
        """File a VAT return"""
        vat_return = self.get_object()
        
        if vat_return.status != 'draft':
            return Response(
                {'error': 'Only draft returns can be filed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vat_return.status = 'filed'
        vat_return.filed_date = timezone.now().date()
        vat_return.save()
        
        serializer = self.get_serializer(vat_return)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['Accounting - VAT Returns'],
        summary='Mark VAT return as paid',
        description='Mark VAT return as paid'
    )
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark VAT return as paid"""
        vat_return = self.get_object()
        
        if vat_return.status != 'filed':
            return Response(
                {'error': 'Only filed returns can be marked as paid'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vat_return.status = 'paid'
        vat_return.paid_date = timezone.now().date()
        vat_return.save()
        
        serializer = self.get_serializer(vat_return)
        return Response(serializer.data)
