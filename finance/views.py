from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db import transaction
from django.db.models import Sum, Q, F
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import secrets

from users.dynamic_permissions import DynamicModulePermission
from .models import FinanceAccount, FinanceCategory, FinanceTransaction, FinanceBudget, FinanceBill, PartyLender, PartyTransaction, PartyTransactionShare, FinanceLoan
from .serializers import (
    AccountSerializer, CategorySerializer,
    TransactionListSerializer, TransactionDetailSerializer,
    BudgetSerializer, BillSerializer, PartyLenderSerializer,
    PartyTransactionSerializer, PartyTransactionShareSerializer, LoanSerializer
)


FINANCE_FILTER_BACKENDS = [DjangoFilterBackend, SearchFilter, OrderingFilter]


@extend_schema(
    tags=['Personal Finance - Dashboard'],
    summary='Get personal finance dashboard data',
    description='Get comprehensive dashboard data including summary, net worth trend, alerts, activities, and top accounts.',
)
@api_view(['GET'])
def personal_finance_dashboard(request):
    """
    Personal Finance Dashboard endpoint
    Returns summary metrics, net worth trend, alerts, activities, and top accounts
    """
    tenant = request.user.get_tenant() if request.user and request.user.is_authenticated else None

    if not tenant:
        return Response({'error': 'Tenant not found'}, status=status.HTTP_403_FORBIDDEN)

    # 1. Summary metrics
    accounts = FinanceAccount.objects.filter(tenant=tenant)
    bills = FinanceBill.objects.filter(tenant=tenant)

    total_balance = accounts.filter(type='bank').aggregate(
        total=Sum('current_balance')
    )['total'] or Decimal('0.00')

    total_investments = accounts.filter(type='investment').aggregate(
        total=Sum('current_balance')
    )['total'] or Decimal('0.00')

    total_debt = accounts.filter(type__in=['credit_card', 'loan']).aggregate(
        total=Sum('current_balance')
    )['total'] or Decimal('0.00')

    # Upcoming renewals (bills due in next 30 days)
    today = date.today()
    next_month = today + timedelta(days=30)
    upcoming_renewals = bills.filter(
        due_date__gte=today,
        due_date__lte=next_month,
        status__in=['unpaid', 'pending']
    ).count()

    # 2. Net Worth Trend (last 6 months)
    net_worth_trend = []
    transactions = FinanceTransaction.objects.filter(tenant=tenant)

    for i in range(5, -1, -1):
        month_date = date.today() - relativedelta(months=i)
        month_name = month_date.strftime('%b')

        # Calculate cumulative balance up to this month
        month_end = date(month_date.year, month_date.month, 1) + relativedelta(months=1) - timedelta(days=1)

        income = transactions.filter(
            type='income',
            date__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        expenses = transactions.filter(
            type='expense',
            date__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        net_worth = float(income - expenses)
        net_worth_trend.append({'month': month_name, 'value': net_worth})

    # 3. Alerts
    alerts = []

    # Overdue bills
    overdue_bills = bills.filter(
        due_date__lt=today,
        status__in=['unpaid', 'pending']
    )
    for bill in overdue_bills[:3]:  # Limit to 3
        alerts.append({
            'type': 'bill',
            'message': f'{bill.name} is overdue',
            'amount': float(bill.amount),
            'date': bill.due_date.isoformat()
        })

    # Upcoming bills
    upcoming_bills = bills.filter(
        due_date__gte=today,
        due_date__lte=next_month,
        status__in=['unpaid', 'pending']
    ).order_by('due_date')[:3]
    for bill in upcoming_bills:
        days_until = (bill.due_date - today).days
        alerts.append({
            'type': 'bill',
            'message': f'{bill.name} due in {days_until} day{"s" if days_until != 1 else ""}',
            'amount': float(bill.amount),
            'date': bill.due_date.isoformat()
        })

    # Over budget warnings
    budgets = FinanceBudget.objects.filter(tenant=tenant).select_related('category')
    for budget in budgets:
        if not budget.category:
            continue
        spent = budget.category.transactions.filter(
            date__gte=budget.start_date,
            date__lte=budget.end_date if budget.end_date else budget.start_date,
            type='expense'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if spent > budget.amount:
            over_amount = spent - budget.amount
            over_percentage = int((over_amount / budget.amount) * 100)
            alerts.append({
                'type': 'over_budget',
                'message': f'{budget.name} budget exceeded by {over_percentage}%',
                'amount': float(over_amount)
            })

    # 4. Recent Activities
    activities = []

    # Recent transactions
    recent_transactions = transactions.order_by('-created_at')[:3]
    for txn in recent_transactions:
        activities.append({
            'type': 'transaction',
            'action': 'created',
            'description': f'{"Income" if txn.type == "income" else "Expense"}: {txn.description or txn.category.name if txn.category else "Transaction"}',
            'timestamp': txn.created_at.isoformat(),
            'amount': float(txn.amount)
        })

    # Recent accounts
    recent_accounts = accounts.order_by('-created_at')[:2]
    for acc in recent_accounts:
        activities.append({
            'type': 'account',
            'action': 'created',
            'description': f'Created account: {acc.name}',
            'timestamp': acc.created_at.isoformat()
        })

    # Sort by timestamp descending
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    activities = activities[:6]  # Limit to 6

    # 5. Top Accounts by Balance
    top_accounts = accounts.filter(
        type__in=['bank', 'cash', 'investment']
    ).order_by('-current_balance')[:4]

    top_accounts_data = [
        {
            'name': acc.name,
            'balance': float(acc.current_balance),
            'type': acc.type
        }
        for acc in top_accounts
    ]

    return Response({
        'summary': {
            'total_balance': float(total_balance),
            'total_investments': float(total_investments),
            'total_debt': float(total_debt),
            'upcoming_renewals': upcoming_renewals
        },
        'netWorthTrend': net_worth_trend,
        'alerts': alerts,
        'activities': activities,
        'topAccounts': top_accounts_data
    })


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='List all parties/lenders',
        description='Get a paginated list of all parties/lenders with optional contact info and photos.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='Get party/lender details',
        description='Retrieve detailed information about a specific party/lender.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='Create a new party/lender',
        description='Create a new party/lender. Name is required; PAN, mobile, email, and photo are optional.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='Update party/lender',
        description='Update an existing party/lender.',
    ),
    partial_update=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='Partially update party/lender',
        description='Partially update an existing party/lender.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Parties/Lenders'],
        summary='Delete party/lender',
        description='Delete a party/lender.',
    ),
)
class PartyLenderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing parties/lenders"""
    serializer_class = PartyLenderSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    search_fields = ['name', 'pan', 'mobile', 'email']
    ordering_fields = ['name', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return PartyLender.objects.filter(tenant=tenant)
        return PartyLender.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating"""
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)

    @action(detail=True, methods=['post'], url_path='regenerate-share-link')
    def regenerate_share_link(self, request, pk=None):
        """Issue a fresh share_token, invalidating any previously shared link for this party."""
        import uuid
        party = self.get_object()
        party.share_token = uuid.uuid4().hex[:32]
        party.save(update_fields=['share_token', 'updated_at'])
        return Response(PartyLenderSerializer(party, context={'request': request}).data)


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Accounts'],
        summary='List all accounts',
        description='Get a paginated list of all financial accounts.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Accounts'],
        summary='Get account details',
        description='Retrieve detailed information about a specific account.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Accounts'],
        summary='Create a new account',
        description='Create a new financial account.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Accounts'],
        summary='Update account',
        description='Update an existing account.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Accounts'],
        summary='Delete account',
        description='Delete an account. Cannot delete if it has transactions.',
    ),
)
class AccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing accounts"""
    serializer_class = AccountSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['type']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'type', 'current_balance', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return FinanceAccount.objects.filter(tenant=tenant)
        return FinanceAccount.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating"""
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)
    
    def perform_destroy(self, instance):
        if instance.transactions.exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Cannot delete an account that has transactions.'})
        instance.delete()


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Categories'],
        summary='List all categories',
        description='Get a paginated list of all income/expense categories.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Categories'],
        summary='Get category details',
        description='Retrieve detailed information about a specific category.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Categories'],
        summary='Create a new category',
        description='Create a new income or expense category.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Categories'],
        summary='Update category',
        description='Update an existing category.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Categories'],
        summary='Delete category',
        description='Delete a category. Cannot delete if it has transactions or budgets.',
    ),
)
class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing categories"""
    serializer_class = CategorySerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['type']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'type', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return FinanceCategory.objects.filter(tenant=tenant)
        return FinanceCategory.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating"""
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        if serializer.instance.is_system:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'System categories cannot be edited.'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'System categories cannot be deleted.'})
        if instance.transactions.exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Cannot delete a category that has transactions.'})
        if instance.budgets.exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Cannot delete a category that has budgets.'})
        instance.delete()


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='List all transactions',
        description='Get a paginated list of all transactions with filtering options.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='Get transaction details',
        description='Retrieve detailed information about a specific transaction.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='Create a new transaction',
        description='Create a new income or expense transaction. Transaction number is auto-generated.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='Update transaction',
        description='Update an existing transaction.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='Delete transaction',
        description='Delete a transaction and reverse its effect on account balance.',
    ),
)
class TransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing transactions"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['type', 'category', 'account', 'date']
    search_fields = ['transaction_number', 'description']
    ordering_fields = ['date', 'amount', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionDetailSerializer
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return FinanceTransaction.objects.filter(tenant=tenant).select_related(
                    'category', 'account'
                )
        return FinanceTransaction.objects.none()
    
    def perform_create(self, serializer):
        """Auto-generate transaction number and set tenant"""
        tenant = self.request.user.get_tenant()
        
        with transaction.atomic():
            # Generate transaction number
            last_transaction = FinanceTransaction._base_manager.select_for_update().order_by('-id').first()
            if last_transaction and last_transaction.transaction_number.startswith('TXN-'):
                try:
                    last_num = int(last_transaction.transaction_number.split('-')[1])
                    transaction_number = f"TXN-{str(last_num + 1).zfill(6)}"
                except (ValueError, IndexError):
                    transaction_number = "TXN-000001"
            else:
                transaction_number = "TXN-000001"
            
            serializer.save(tenant=tenant, transaction_number=transaction_number)

    def perform_update(self, serializer):
        """Reverse the old balance effect and apply the new one on edit.

        Uses an atomic F() update on the account row rather than load-mutate-save,
        because the FK resolved by the serializer's PrimaryKeyRelatedField is a
        freshly-queried instance distinct from the one cached on the pre-update
        instance -- mutating both in Python and saving them in sequence silently
        drops whichever write happens first.
        """
        instance = serializer.instance
        old_account_id = instance.account_id
        old_amount = instance.amount
        old_type = instance.type

        with transaction.atomic():
            updated = serializer.save()

            if old_account_id:
                delta = -old_amount if old_type == 'income' else old_amount
                FinanceAccount.objects.filter(pk=old_account_id).update(
                    current_balance=F('current_balance') + delta
                )

            if updated.account_id:
                delta = updated.amount if updated.type == 'income' else -updated.amount
                FinanceAccount.objects.filter(pk=updated.account_id).update(
                    current_balance=F('current_balance') + delta
                )

    def perform_destroy(self, instance):
        """Reverse account balance when deleting transaction"""
        with transaction.atomic():
            if instance.account_id:
                delta = -instance.amount if instance.type == 'income' else instance.amount
                FinanceAccount.objects.filter(pk=instance.account_id).update(
                    current_balance=F('current_balance') + delta
                )

            instance.delete()
    
    @extend_schema(
        tags=['Personal Finance - Transactions'],
        summary='Get transaction summary',
        description='Get summary statistics for all transactions (total income, expenses, balance).',
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get transaction summary (income, expenses, balance)"""
        queryset = self.get_queryset()
        
        total_income = queryset.filter(type='income').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        total_expenses = queryset.filter(type='expense').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        net_balance = total_income - total_expenses
        
        return Response({
            'total_income': float(total_income),
            'total_expenses': float(total_expenses),
            'net_balance': float(net_balance),
            'transaction_count': queryset.count()
        })


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Budgets'],
        summary='List all budgets',
        description='Get a paginated list of all budgets.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Budgets'],
        summary='Get budget details',
        description='Retrieve detailed information about a specific budget including spent amount.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Budgets'],
        summary='Create a new budget',
        description='Create a new budget for expense tracking.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Budgets'],
        summary='Update budget',
        description='Update an existing budget.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Budgets'],
        summary='Delete budget',
        description='Delete a budget.',
    ),
)
class BudgetViewSet(viewsets.ModelViewSet):
    """ViewSet for managing budgets"""
    serializer_class = BudgetSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['period', 'category']
    search_fields = ['name']
    ordering_fields = ['start_date', 'amount', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return FinanceBudget.objects.filter(tenant=tenant).select_related('category')
        return FinanceBudget.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating"""
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Bills'],
        summary='List all bills',
        description='Get a paginated list of all bills and recurring payments.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Bills'],
        summary='Get bill details',
        description='Retrieve detailed information about a specific bill.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Bills'],
        summary='Create a new bill',
        description='Create a new bill or recurring payment. Bill number is auto-generated.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Bills'],
        summary='Update bill',
        description='Update an existing bill.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Bills'],
        summary='Delete bill',
        description='Delete a bill.',
    ),
)
class BillViewSet(viewsets.ModelViewSet):
    """ViewSet for managing bills"""
    serializer_class = BillSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['recurring', 'status', 'category', 'due_date']
    search_fields = ['bill_number', 'name', 'notes']
    ordering_fields = ['due_date', 'amount', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return FinanceBill.objects.filter(tenant=tenant).select_related('category')
        return FinanceBill.objects.none()
    
    def perform_create(self, serializer):
        """Auto-generate bill number and set tenant"""
        tenant = self.request.user.get_tenant()
        
        with transaction.atomic():
            # Generate bill number
            last_bill = FinanceBill._base_manager.select_for_update().order_by('-id').first()
            if last_bill and last_bill.bill_number.startswith('BILL-'):
                try:
                    last_num = int(last_bill.bill_number.split('-')[1])
                    bill_number = f"BILL-{str(last_num + 1).zfill(6)}"
                except (ValueError, IndexError):
                    bill_number = "BILL-000001"
            else:
                bill_number = "BILL-000001"
            
            serializer.save(tenant=tenant, bill_number=bill_number)
    
    @extend_schema(
        tags=['Personal Finance - Bills'],
        summary='Get upcoming bills',
        description='Get bills that are due soon (within next 30 days).',
    )
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming bills (due in next 30 days)"""
        from datetime import date, timedelta
        
        today = date.today()
        next_month = today + timedelta(days=30)
        
        upcoming_bills = self.get_queryset().filter(
            due_date__gte=today,
            due_date__lte=next_month,
            status__in=['unpaid', 'pending']
        ).order_by('due_date')
        
        serializer = self.get_serializer(upcoming_bills, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Party Transactions'],
        summary='List all party transactions',
        description='Get a paginated list of all party transactions (In/Out).',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Party Transactions'],
        summary='Get party transaction details',
        description='Retrieve detailed information about a specific party transaction.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Party Transactions'],
        summary='Create a new party transaction',
        description='Create a new transaction with a party (Money In/Out). Payment method and receipt are only for Out transactions.',
    ),
    update=extend_schema(
        tags=['Personal Finance - Party Transactions'],
        summary='Update party transaction',
        description='Update an existing party transaction.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Party Transactions'],
        summary='Delete party transaction',
        description='Delete a party transaction.',
    ),
)
class PartyTransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing party transactions (In/Out)"""
    serializer_class = PartyTransactionSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['direction', 'party', 'payment_method', 'date']
    search_fields = ['party__name', 'note']
    ordering_fields = ['date', 'amount', 'created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return PartyTransaction.objects.filter(
                    tenant=tenant
                ).select_related('party').order_by('-date')
        return PartyTransaction.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating"""
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Party Shares'],
        summary='List shareable links',
        description='Get a list of all created shareable links for parties/transactions.',
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Party Shares'],
        summary='Get share details',
        description='Retrieve details about a specific shareable link.',
    ),
    create=extend_schema(
        tags=['Personal Finance - Party Shares'],
        summary='Create shareable link',
        description='Generate a unique shareable read-only link for a party ledger or specific transaction.',
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Party Shares'],
        summary='Revoke share',
        description='Revoke/delete a shareable link.',
    ),
)
class PartyTransactionShareViewSet(viewsets.ModelViewSet):
    """ViewSet for managing shareable party transaction links"""
    serializer_class = PartyTransactionShareSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    filterset_fields = ['share_type', 'is_active']
    search_fields = ['token']
    ordering_fields = ['created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if self.request.user and self.request.user.is_authenticated:
            tenant = self.request.user.get_tenant()
            if tenant:
                return PartyTransactionShare.objects.filter(
                    tenant=tenant
                ).select_related('transaction', 'party')
        return PartyTransactionShare.objects.none()
    
    def perform_create(self, serializer):
        """Generate unique token and set tenant"""
        tenant = self.request.user.get_tenant()
        token = secrets.token_urlsafe(48)
        serializer.save(tenant=tenant, token=token)


# Public view for shared transactions (no authentication required)
from rest_framework.response import Response
from rest_framework.status import HTTP_404_NOT_FOUND
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

class PublicPartyTransactionShareView(APIView):
    """Public endpoint to view a single shared transaction without authentication"""
    permission_classes = [AllowAny]

    def get(self, request, token):
        """Retrieve a transaction by its own share_token."""
        from django.db import connection
        from tenants.middleware import set_current_tenant
        from tenants.models import Tenant

        # Same problem as PublicPartyLedgerShareView: no authenticated
        # tenant means TenantManager would filter every query to nothing.
        # Resolve the owning tenant with a raw lookup first, then set it as
        # current so the normal ORM query below resolves correctly.
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT tenant_id FROM finance_party_transactions WHERE share_token = %s',
                [token]
            )
            row = cursor.fetchone()

        if not row:
            return Response({'error': 'Share not found'}, status=HTTP_404_NOT_FOUND)

        try:
            tenant = Tenant.objects.get(id=row[0])
        except Tenant.DoesNotExist:
            return Response({'error': 'Share not found'}, status=HTTP_404_NOT_FOUND)

        set_current_tenant(tenant)

        try:
            transaction = PartyTransaction.objects.select_related('party').get(share_token=token)
        except PartyTransaction.DoesNotExist:
            return Response({'error': 'Share not found'}, status=HTTP_404_NOT_FOUND)

        data = PartyTransactionSerializer(transaction, context={'request': request}).data
        data['tenant'] = {
            'name': tenant.name,
            'workspace_name': tenant.workspace_name,
            'logo_url': request.build_absolute_uri(tenant.logo.url) if getattr(tenant, 'logo', None) else None,
        }
        return Response(data)


class PublicPartyLedgerShareView(APIView):
    """Public endpoint to view party ledger by share token without authentication"""
    permission_classes = [AllowAny]

    def get(self, request, token):
        """Retrieve party ledger details by share token."""
        from django.db import connection
        from tenants.middleware import set_current_tenant
        from tenants.models import Tenant

        # The requester has no authenticated tenant, so TenantManager would
        # otherwise filter every query down to nothing (see TenantManager.
        # get_queryset). Look up just the owning tenant with a raw query
        # first (bypassing that filter), then set it as the current tenant
        # for the rest of the request so the normal ORM queries below —
        # for both the party and its transactions — resolve correctly.
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT tenant_id FROM finance_parties_lenders WHERE share_token = %s',
                [token]
            )
            row = cursor.fetchone()

        if not row:
            return Response({'error': 'Party ledger not found'}, status=HTTP_404_NOT_FOUND)

        try:
            tenant = Tenant.objects.get(id=row[0])
        except Tenant.DoesNotExist:
            return Response({'error': 'Party ledger not found'}, status=HTTP_404_NOT_FOUND)

        set_current_tenant(tenant)

        try:
            party = PartyLender.objects.get(share_token=token)
        except PartyLender.DoesNotExist:
            return Response({'error': 'Party ledger not found'}, status=HTTP_404_NOT_FOUND)

        transactions_qs = PartyTransaction.objects.filter(party=party).order_by('-date', '-created_at')

        return Response({
            'tenant': {
                'name': tenant.name,
                'workspace_name': tenant.workspace_name,
                'logo_url': request.build_absolute_uri(tenant.logo.url) if getattr(tenant, 'logo', None) else None,
            },
            'party': PartyLenderSerializer(party, context={'request': request}).data,
            'transactions': PartyTransactionSerializer(
                transactions_qs,
                many=True,
                context={'request': request}
            ).data,
        })


@extend_schema_view(
    list=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='List all loans',
        description='Retrieve a list of all loans for the current tenant.'
    ),
    create=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='Create a new loan',
        description='Create a new loan entry with EMI details.'
    ),
    retrieve=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='Get loan details',
        description='Retrieve detailed information about a specific loan.'
    ),
    update=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='Update a loan',
        description='Update loan details including remaining balance.'
    ),
    partial_update=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='Partially update a loan',
        description='Partially update loan details.'
    ),
    destroy=extend_schema(
        tags=['Personal Finance - Loans'],
        summary='Delete a loan',
        description='Delete a loan entry.'
    ),
)
class LoanViewSet(viewsets.ModelViewSet):
    """ViewSet for managing loans"""
    serializer_class = LoanSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'personal_finance'
    filter_backends = FINANCE_FILTER_BACKENDS
    search_fields = ['name', 'type']
    ordering_fields = ['start_date', 'principal', 'emi', 'remaining_balance']
    ordering = ['-start_date']

    def get_queryset(self):
        tenant = self.request.user.get_tenant()
        return FinanceLoan.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = self.request.user.get_tenant()
        serializer.save(tenant=tenant)

