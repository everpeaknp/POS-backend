from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db import transaction
from django.db.models import Sum, Q
from decimal import Decimal

from users.dynamic_permissions import DynamicModulePermission
from .models import FinanceAccount, FinanceCategory, FinanceTransaction, FinanceBudget, FinanceBill, PartyLender
from .serializers import (
    AccountSerializer, CategorySerializer,
    TransactionListSerializer, TransactionDetailSerializer,
    BudgetSerializer, BillSerializer, PartyLenderSerializer
)


FINANCE_FILTER_BACKENDS = [DjangoFilterBackend, SearchFilter, OrderingFilter]


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
    
    def perform_destroy(self, instance):
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
    
    def perform_destroy(self, instance):
        """Reverse account balance when deleting transaction"""
        with transaction.atomic():
            # Reverse the balance change
            if instance.type == 'income':
                instance.account.current_balance -= instance.amount
            else:  # expense
                instance.account.current_balance += instance.amount
            instance.account.save()
            
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
