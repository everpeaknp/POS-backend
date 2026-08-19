from rest_framework import serializers
from .models import FinanceAccount, FinanceCategory, FinanceTransaction, FinanceBudget, FinanceBill, PartyLender, PartyTransaction, PartyTransactionShare


class AccountSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    
    class Meta:
        model = FinanceAccount
        fields = [
            'id', 'name', 'type', 'type_display', 'opening_balance',
            'current_balance', 'description', 'bank_name', 'account_number',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'current_balance', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Set current_balance to opening_balance on creation
        validated_data['current_balance'] = validated_data.get('opening_balance', 0)
        return super().create(validated_data)


class CategorySerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    transaction_count = serializers.SerializerMethodField()
    
    class Meta:
        model = FinanceCategory
        fields = [
            'id', 'name', 'type', 'type_display', 'description',
            'transaction_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_transaction_count(self, obj):
        return obj.transactions.count()


class TransactionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for transaction lists"""
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = FinanceTransaction
        fields = [
            'id', 'transaction_number', 'date', 'type', 'type_display',
            'amount', 'category', 'category_name', 'account', 'account_name',
            'description', 'created_at'
        ]
        read_only_fields = ['id', 'transaction_number', 'created_at']


class TransactionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single transaction view"""
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_type = serializers.CharField(source='category.type', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_type = serializers.CharField(source='account.type', read_only=True)
    
    class Meta:
        model = FinanceTransaction
        fields = [
            'id', 'transaction_number', 'date', 'type', 'type_display',
            'amount', 'category', 'category_name', 'category_type',
            'account', 'account_name', 'account_type',
            'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'transaction_number', 'created_at', 'updated_at']


class BudgetSerializer(serializers.ModelSerializer):
    period_display = serializers.CharField(source='get_period_display', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = FinanceBudget
        fields = [
            'id', 'name', 'category', 'category_name', 'amount',
            'period', 'period_display', 'start_date', 'end_date',
            'spent_amount', 'remaining_amount', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_spent_amount(self, obj):
        """Calculate spent amount for this budget period"""
        if not obj.category:
            return 0
        
        from django.db.models import Sum
        from decimal import Decimal
        
        spent = obj.category.transactions.filter(
            date__gte=obj.start_date,
            date__lte=obj.end_date if obj.end_date else obj.start_date,
            type='expense'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return float(spent)
    
    def get_remaining_amount(self, obj):
        """Calculate remaining budget amount"""
        spent = self.get_spent_amount(obj)
        return float(obj.amount) - spent


class BillSerializer(serializers.ModelSerializer):
    recurring_display = serializers.CharField(source='get_recurring_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = FinanceBill
        fields = [
            'id', 'bill_number', 'name', 'amount', 'due_date',
            'category', 'category_name', 'recurring', 'recurring_display',
            'status', 'status_display', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'bill_number', 'created_at', 'updated_at']


class PartyTransactionSerializer(serializers.ModelSerializer):
    """Serializer for party transactions (In/Out)"""
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    party_name = serializers.CharField(source='party.name', read_only=True)
    receipt_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PartyTransaction
        fields = [
            'id', 'party', 'party_name', 'direction', 'direction_display',
            'amount', 'date', 'payment_method', 'payment_method_display',
            'receipt', 'receipt_url', 'note', 'share_token', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'share_token', 'created_at', 'updated_at']
    
    def get_receipt_url(self, obj):
        """Return full URL for receipt if it exists"""
        if obj.receipt:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.receipt.url)
            return obj.receipt.url
        return None


class PartyLenderSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    total_given = serializers.SerializerMethodField()
    total_received = serializers.SerializerMethodField()
    net_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = PartyLender
        fields = [
            'id', 'name', 'pan', 'mobile', 'email',
            'photo', 'photo_url', 'total_given', 'total_received',
            'net_balance', 'share_token', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'share_token', 'created_at', 'updated_at']
    
    def get_photo_url(self, obj):
        """Return full URL for photo if it exists"""
        if obj.photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo.url)
            return obj.photo.url
        return None
    
    def get_total_given(self, obj):
        """Sum of all 'Out' transactions"""
        from django.db.models import Sum
        from decimal import Decimal
        
        total = obj.transactions.filter(direction='out').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        return float(total)
    
    def get_total_received(self, obj):
        """Sum of all 'In' transactions"""
        from django.db.models import Sum
        from decimal import Decimal
        
        total = obj.transactions.filter(direction='in').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        return float(total)
    
    def get_net_balance(self, obj):
        """Calculate net balance: received - given (positive means we owe, negative means they owe)"""
        total_received = float(self.get_total_received(obj))
        total_given = float(self.get_total_given(obj))
        return total_received - total_given


class PartyTransactionShareSerializer(serializers.ModelSerializer):
    """Serializer for shareable transaction links"""
    share_type_display = serializers.CharField(source='get_share_type_display', read_only=True)
    transaction_data = serializers.SerializerMethodField()
    party_data = serializers.SerializerMethodField()
    
    class Meta:
        model = PartyTransactionShare
        fields = [
            'id', 'token', 'share_type', 'share_type_display',
            'is_active', 'expires_at', 'transaction_data', 'party_data',
            'created_at'
        ]
        read_only_fields = ['id', 'token', 'created_at']
    
    def get_transaction_data(self, obj):
        """Return transaction details if share_type is 'transaction'"""
        if obj.transaction and obj.share_type == 'transaction':
            return PartyTransactionSerializer(obj.transaction, context=self.context).data
        return None
    
    def get_party_data(self, obj):
        """Return party ledger details if share_type is 'party_ledger'"""
        if obj.party and obj.share_type == 'party_ledger':
            return PartyLenderSerializer(obj.party, context=self.context).data
        return None
