from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.dynamic_permissions import DynamicModulePermission
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from django.utils import timezone
from django.db.models import Sum, Q, Count
from decimal import Decimal

from .models import Account, JournalEntry, JournalLine, BankAccount, BankTransaction, TaxRule, VATReturn
from tenants.utils import get_request_tenant
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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'sub_type', 'status', 'parent']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'balance', 'created_at']
    ordering = ['code']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return Account._base_manager.none()
        return Account._base_manager.filter(tenant=tenant)
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        serializer.save(tenant=tenant)

    def perform_destroy(self, instance):
        from django.db.models.deletion import ProtectedError
        from rest_framework.exceptions import ValidationError

        if instance.children.exists():
            raise ValidationError({
                'detail': 'Cannot delete an account that has sub-accounts. Delete or reassign child accounts first.'
            })

        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                'detail': (
                    'Cannot delete this account because it is used in journal entries, '
                    'bank accounts, tax rules, or other records. Remove those links first.'
                )
            })
    
    @extend_schema(
        tags=['Accounting - Chart of Accounts'],
        summary='Seed default chart of accounts',
        description='Creates the standard chart of accounts for this organization. Safe to run multiple times — existing account codes are skipped.',
    )
    @action(detail=False, methods=['post'], url_path='seed_default')
    def seed_default(self, request):
        """Create standard chart of accounts for the tenant."""
        from accounting.chart_seed import seed_default_chart_of_accounts
        from accounting.serializers import AccountSerializer

        tenant = get_request_tenant(request.user)
        if not tenant:
            return Response({'detail': 'No active organization.'}, status=status.HTTP_400_BAD_REQUEST)

        result = seed_default_chart_of_accounts(tenant)
        serializer = AccountSerializer(result['accounts'], many=True)
        return Response({
            'created': result['created'],
            'skipped': result['skipped'],
            'total': result['total'],
            'accounts': serializer.data,
            'message': (
                f"Created {result['created']} account(s)."
                if result['created']
                else 'Chart of accounts is already set up — no new accounts were needed.'
            ),
        })

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
        tenant = get_request_tenant(request.user)
        is_debit_type = account.type in ['Assets', 'Expense']

        def line_delta(line):
            if is_debit_type:
                return line.debit - line.credit
            return line.credit - line.debit

        base_qs = JournalLine.objects.filter(
            tenant=tenant,
            account=account,
            journal_entry__status='posted',
        )

        balance = Decimal('0.00')
        ledger_data = []

        if from_date:
            prior_lines = base_qs.filter(journal_entry__date__lt=from_date).select_related('journal_entry')
            for line in prior_lines:
                balance += line_delta(line)
            if balance != 0:
                ledger_data.append({
                    'date': from_date,
                    'reference': 'B/F',
                    'description': 'Opening balance',
                    'debit': float(balance) if is_debit_type and balance > 0 else float(abs(balance)) if not is_debit_type and balance < 0 else 0.0,
                    'credit': float(balance) if not is_debit_type and balance > 0 else float(abs(balance)) if is_debit_type and balance < 0 else 0.0,
                    'balance': float(balance),
                    'source': 'Opening',
                })

        lines = base_qs
        if from_date:
            lines = lines.filter(journal_entry__date__gte=from_date)
        if to_date:
            lines = lines.filter(journal_entry__date__lte=to_date)

        lines = lines.select_related('journal_entry').order_by('journal_entry__date', 'id')

        for line in lines:
            balance += line_delta(line)
            ledger_data.append({
                'date': line.journal_entry.date,
                'reference': line.journal_entry.entry_number,
                'description': line.description,
                'debit': float(line.debit),
                'credit': float(line.credit),
                'balance': float(balance),
                'source': line.journal_entry.type,
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
        tenant = get_request_tenant(request.user)

        accounts = self.get_queryset().filter(status='active').order_by('type', 'code')

        trial_balance_data = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')

        for account in accounts:
            lines = JournalLine.objects.filter(
                tenant=tenant,
                account=account,
                journal_entry__status='posted',
            )

            if as_of_date:
                lines = lines.filter(journal_entry__date__lte=as_of_date)

            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit'),
            )

            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            net = debit_sum - credit_sum

            if net == 0:
                continue

            is_debit_type = account.type in ['Assets', 'Expense']

            if is_debit_type:
                if net > 0:
                    debit_balance, credit_balance = net, Decimal('0.00')
                else:
                    debit_balance, credit_balance = Decimal('0.00'), abs(net)
            elif net < 0:
                debit_balance, credit_balance = Decimal('0.00'), abs(net)
            else:
                debit_balance, credit_balance = net, Decimal('0.00')

            total_debit += debit_balance
            total_credit += credit_balance

            trial_balance_data.append({
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'type': account.type,
                'level': account.level,
                'debit': float(debit_balance),
                'credit': float(credit_balance),
                'balance': float(net),
            })

        return Response({
            'as_of_date': as_of_date or timezone.now().date().isoformat(),
            'accounts': trial_balance_data,
            'total_debit': float(total_debit),
            'total_credit': float(total_credit),
            'is_balanced': abs(total_debit - total_credit) < Decimal('0.01'),
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
        tenant = get_request_tenant(request.user)

        if not from_date:
            from_date = timezone.now().replace(day=1).date().isoformat()
        if not to_date:
            to_date = timezone.now().date().isoformat()

        accounts = self.get_queryset().filter(
            status='active',
            type__in=['Income', 'Expense'],
        ).order_by('type', 'code')

        income_accounts = []
        expense_accounts = []
        total_income = Decimal('0.00')
        total_expenses = Decimal('0.00')

        for account in accounts:
            lines = JournalLine.objects.filter(
                tenant=tenant,
                account=account,
                journal_entry__status='posted',
            )

            lines = lines.filter(journal_entry__date__gte=from_date, journal_entry__date__lte=to_date)

            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit'),
            )

            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')

            if account.type == 'Income':
                amount = credit_sum - debit_sum
                if amount != 0:
                    total_income += amount
                    income_accounts.append({
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'sub_type': account.sub_type,
                        'amount': float(amount),
                    })
            else:
                amount = debit_sum - credit_sum
                if amount != 0:
                    total_expenses += amount
                    expense_accounts.append({
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'sub_type': account.sub_type,
                        'amount': float(amount),
                    })

        net_profit = total_income - total_expenses
        income_margin = (net_profit / total_income * 100) if total_income > 0 else Decimal('0.00')

        return Response({
            'from_date': from_date,
            'to_date': to_date,
            'income': {
                'accounts': income_accounts,
                'total': float(total_income),
            },
            'expenses': {
                'accounts': expense_accounts,
                'total': float(total_expenses),
            },
            'net_profit': float(net_profit),
            'net_margin': float(income_margin),
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
        as_of_date = request.query_params.get('as_of_date') or timezone.now().date().isoformat()
        tenant = get_request_tenant(request.user)

        accounts = self.get_queryset().filter(
            status='active',
            type__in=['Assets', 'Liabilities', 'Equity'],
        ).order_by('type', 'sub_type', 'code')

        assets_data = {'current': [], 'fixed': [], 'other': []}
        liabilities_data = {'current': [], 'long_term': [], 'other': []}
        equity_data = []

        total_assets = Decimal('0.00')
        total_liabilities = Decimal('0.00')
        total_equity = Decimal('0.00')

        def balance_as_of(account):
            lines = JournalLine.objects.filter(
                tenant=tenant,
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lte=as_of_date,
            )
            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit'),
            )
            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            net = debit_sum - credit_sum
            if account.type in ['Assets', 'Expense']:
                return net
            return credit_sum - debit_sum

        for account in accounts:
            amount = balance_as_of(account)
            if amount == 0:
                continue

            account_data = {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'sub_type': account.sub_type,
                'amount': float(amount),
            }

            if account.type == 'Assets':
                total_assets += amount
                sub_type = account.sub_type or ''
                if any(k in sub_type for k in ('Current', 'Cash', 'Receivable', 'Bank')):
                    assets_data['current'].append(account_data)
                elif any(k in sub_type for k in ('Fixed', 'Property', 'Equipment')):
                    assets_data['fixed'].append(account_data)
                else:
                    assets_data['other'].append(account_data)

            elif account.type == 'Liabilities':
                total_liabilities += amount
                sub_type = account.sub_type or ''
                if any(k in sub_type for k in ('Current', 'Payable')):
                    liabilities_data['current'].append(account_data)
                elif any(k in sub_type for k in ('Long', 'Term')):
                    liabilities_data['long_term'].append(account_data)
                else:
                    liabilities_data['other'].append(account_data)

            elif account.type == 'Equity':
                total_equity += amount
                equity_data.append(account_data)

        # Include unclosed P&L in equity so Assets = Liabilities + Equity
        pl_accounts = self.get_queryset().filter(
            status='active',
            type__in=['Income', 'Expense'],
        )
        net_income = Decimal('0.00')
        for account in pl_accounts:
            lines = JournalLine.objects.filter(
                tenant=tenant,
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lte=as_of_date,
            )
            aggregates = lines.aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit'),
            )
            debit_sum = aggregates['total_debit'] or Decimal('0.00')
            credit_sum = aggregates['total_credit'] or Decimal('0.00')
            if account.type == 'Income':
                net_income += credit_sum - debit_sum
            else:
                net_income -= debit_sum - credit_sum

        if net_income != 0:
            equity_data.append({
                'id': 'current-earnings',
                'code': '',
                'name': 'Current Year Earnings',
                'sub_type': 'Retained',
                'amount': float(net_income),
            })
            total_equity += net_income

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
                'total_current': float(total_current_assets),
                'total_fixed': float(total_fixed_assets),
                'total_other': float(total_other_assets),
                'total': float(total_assets),
            },
            'liabilities': {
                'current': liabilities_data['current'],
                'long_term': liabilities_data['long_term'],
                'other': liabilities_data['other'],
                'total_current': float(total_current_liabilities),
                'total_long_term': float(total_long_term_liabilities),
                'total_other': float(total_other_liabilities),
                'total': float(total_liabilities),
            },
            'equity': {
                'accounts': equity_data,
                'total': float(total_equity),
            },
            'total_liabilities_equity': float(total_liab_equity),
            'is_balanced': is_balanced,
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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'type', 'date']
    search_fields = ['entry_number', 'reference', 'description']
    ordering_fields = ['date', 'entry_number', 'created_at']
    ordering = ['-date', '-entry_number']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return JournalEntry.objects.none()
        return JournalEntry.objects.filter(tenant=tenant).prefetch_related('lines__account')
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        serializer.save(tenant=tenant)
    
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
        
        if entry.total_debit != entry.total_credit:
            return Response(
                {'error': f'Debits ({entry.total_debit}) must equal credits ({entry.total_credit}) before posting'},
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
            'tenant': get_request_tenant(request.user),
        }
        
        reversal_entry = JournalEntry.objects.create(**reversal_data)
        
        # Generate entry number
        last_entry = JournalEntry.objects.filter(tenant=get_request_tenant(request.user)).order_by('-id').first()
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
                tenant=get_request_tenant(request.user),
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

    @extend_schema(
        tags=['Accounting - Journal Entries'],
        summary='GL integration summary',
        description='Posted journal entry counts for construction and payroll auto-posting flows',
    )
    @action(detail=False, methods=['get'], url_path='gl-integration-summary')
    def gl_integration_summary(self, request):
        tenant = get_request_tenant(request.user)
        if not tenant:
            return Response({'detail': 'No tenant'}, status=status.HTTP_400_BAD_REQUEST)

        posted = JournalEntry.objects.filter(tenant=tenant, status='posted')
        prefixes = {
            'material_consumption': 'MC-',
            'labor_wage': 'ATT-',
            'equipment_usage': 'EQ-',
            'daily_log_expense': 'DL-',
            'payroll': 'PAY-',
        }
        by_prefix = {
            key: posted.filter(reference__startswith=prefix).count()
            for key, prefix in prefixes.items()
        }
        by_type = {}
        for row in posted.values('type').annotate(count=Count('id')):
            by_type[row['type'] or 'Manual'] = row['count']

        checklist = [
            {'step': 1, 'action': 'Log material consumption at a construction site', 'expect': 'Journal ref MC-* posted'},
            {'step': 2, 'action': 'Mark worker attendance (present/half-day/overtime)', 'expect': 'Journal ref ATT-* posted'},
            {'step': 3, 'action': 'Log rented equipment usage', 'expect': 'Journal ref EQ-* posted (if cost > 0)'},
            {'step': 4, 'action': 'Add other expenses on a daily log', 'expect': 'Journal ref DL-* posted'},
            {'step': 5, 'action': 'Run HR payroll for a month', 'expect': 'Journal ref PAY-* per employee'},
            {'step': 6, 'action': 'Review Profit & Loss and Trial Balance', 'expect': 'Construction/labor expenses reflected'},
        ]

        return Response({
            'by_prefix': by_prefix,
            'by_type': by_type,
            'total_posted': posted.count(),
            'checklist': checklist,
        })


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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'status']
    search_fields = ['bank_name', 'account_name', 'account_number']
    ordering_fields = ['bank_name', 'balance', 'created_at']
    ordering = ['bank_name']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return BankAccount.objects.none()
        return BankAccount.objects.filter(tenant=tenant)
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        bank_account = serializer.save(tenant=tenant)
        if bank_account.balance and bank_account.balance > 0:
            BankTransaction.objects.create(
                tenant=tenant,
                bank_account=bank_account,
                date=timezone.now().date(),
                reference='OPENING',
                description='Opening balance',
                type='Opening',
                debit=Decimal('0.00'),
                credit=bank_account.balance,
                balance=bank_account.balance,
                reconciled=True,
                reconciled_date=timezone.now().date(),
            )
    
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
            tenant=get_request_tenant(request.user),
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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['bank_account', 'type', 'reconciled']
    search_fields = ['reference', 'description']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return BankTransaction.objects.none()
        return BankTransaction.objects.filter(tenant=tenant)
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        serializer.save(tenant=tenant)
    
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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'applicable_on', 'status']
    search_fields = ['name']
    ordering_fields = ['name', 'rate', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return TaxRule.objects.none()
        return TaxRule.objects.filter(tenant=tenant)
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        serializer.save(tenant=tenant)


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
    permission_classes = [DynamicModulePermission]
    permission_module = 'accounting'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['return_number', 'period']
    ordering_fields = ['from_date', 'created_at']
    ordering = ['-from_date']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return VATReturn.objects.none()
        return VATReturn.objects.filter(tenant=tenant)
    
    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise PermissionDenied("No active organization. Please select an organization first.")
        serializer.save(tenant=tenant)
    
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
