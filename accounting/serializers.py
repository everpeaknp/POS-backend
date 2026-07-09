from rest_framework import serializers
from decimal import Decimal
from .models import Account, JournalEntry, JournalLine, BankAccount, BankTransaction, TaxRule, VATReturn
from accounting.utils import generate_entry_number


class AccountSerializer(serializers.ModelSerializer):
    """Serializer for Chart of Accounts"""
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    opening_balance = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, write_only=True, default=Decimal('0')
    )
    opening_balance_date = serializers.DateField(required=False, write_only=True, allow_null=True)
    balance_type = serializers.ChoiceField(
        choices=['debit', 'credit', 'Debit', 'Credit'],
        required=False, write_only=True, default='debit'
    )
    
    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'type', 'sub_type', 'level', 'parent', 'parent_name',
            'balance', 'status', 'description', 'created_at', 'updated_at',
            'opening_balance', 'opening_balance_date', 'balance_type',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'parent_name']
    
    def validate(self, data):
        parent = data.get('parent')
        account_type = data.get('type') or (self.instance.type if self.instance else None)
        if parent and account_type and parent.type != account_type:
            raise serializers.ValidationError("Parent account must be of the same type")
        if parent:
            data['level'] = parent.level + 1
        elif 'parent' in data and data.get('parent') is None:
            data['level'] = 0

        if not self.instance:
            code = data.get('code')
            request = self.context.get('request')
            if code and request and getattr(request, 'user', None):
                from tenants.utils import get_request_tenant
                tenant = get_request_tenant(request.user)
                if tenant and Account._base_manager.filter(tenant=tenant, code=code).exists():
                    raise serializers.ValidationError({
                        'code': 'An account with this code already exists.',
                    })

        return data

    def create(self, validated_data):
        opening_balance = validated_data.pop('opening_balance', Decimal('0')) or Decimal('0')
        opening_balance_date = validated_data.pop('opening_balance_date', None)
        balance_type = validated_data.pop('balance_type', 'debit')
        tenant = validated_data['tenant']

        account = Account._base_manager.create(**validated_data)

        if opening_balance > 0:
            from .services import create_account_opening_balance
            create_account_opening_balance(
                account, opening_balance, opening_balance_date, balance_type, tenant
            )
            account.refresh_from_db()

        return account


class JournalLineSerializer(serializers.ModelSerializer):
    """Serializer for Journal Entry Lines"""
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    
    class Meta:
        model = JournalLine
        fields = [
            'id', 'account', 'account_name', 'account_code', 'description',
            'debit', 'credit'
        ]
        read_only_fields = ['id', 'account_name', 'account_code']
    
    def validate(self, data):
        # Ensure either debit or credit is non-zero, but not both
        debit = data.get('debit', Decimal('0.00'))
        credit = data.get('credit', Decimal('0.00'))
        
        if debit > 0 and credit > 0:
            raise serializers.ValidationError("A line cannot have both debit and credit")
        if debit == 0 and credit == 0:
            raise serializers.ValidationError("Either debit or credit must be greater than zero")
        
        return data


class JournalEntrySerializer(serializers.ModelSerializer):
    """Serializer for Journal Entries with nested lines"""
    lines = JournalLineSerializer(many=True)
    posted_by_name = serializers.CharField(source='posted_by.username', read_only=True)
    reversed_by_name = serializers.CharField(source='reversed_by.username', read_only=True)
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'date', 'reference', 'description', 'type', 'status',
            'total_debit', 'total_credit', 'posted_by', 'posted_by_name', 'posted_date',
            'reversed_by', 'reversed_by_name', 'reversed_date', 'reversal_entry',
            'lines', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'entry_number', 'total_debit', 'total_credit', 'posted_by', 'posted_by_name',
            'posted_date', 'reversed_by', 'reversed_by_name', 'reversed_date', 'reversal_entry',
            'created_at', 'updated_at'
        ]
    
    def validate(self, data):
        # Only allow editing if status is draft
        if self.instance and self.instance.status != 'draft':
            raise serializers.ValidationError("Cannot modify a posted or reversed journal entry")
        
        return data
    
    def validate_lines(self, lines):
        if len(lines) < 2:
            raise serializers.ValidationError("Journal entry must have at least 2 lines")
        
        total_debit = sum(line.get('debit', Decimal('0.00')) for line in lines)
        total_credit = sum(line.get('credit', Decimal('0.00')) for line in lines)
        
        # Draft entries may be saved unbalanced; balance is enforced on post
        status = 'draft'
        if self.instance:
            status = self.instance.status
        elif getattr(self, 'initial_data', None):
            status = self.initial_data.get('status', 'draft')
        
        if status != 'draft' and total_debit != total_credit:
            raise serializers.ValidationError(
                f"Debits ({total_debit}) must equal credits ({total_credit})"
            )
        
        return lines
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        
        # Calculate totals
        total_debit = sum(line.get('debit', Decimal('0.00')) for line in lines_data)
        total_credit = sum(line.get('credit', Decimal('0.00')) for line in lines_data)
        
        # Generate entry number
        tenant = validated_data['tenant']
        validated_data['entry_number'] = generate_entry_number(tenant)
        validated_data['total_debit'] = total_debit
        validated_data['total_credit'] = total_credit
        
        journal_entry = JournalEntry.objects.create(**validated_data)
        
        # Create lines
        for line_data in lines_data:
            JournalLine.objects.create(
                journal_entry=journal_entry,
                tenant=tenant,
                **line_data
            )
        
        return journal_entry
    
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update header
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update lines if provided
        if lines_data is not None:
            # Delete existing lines
            instance.lines.all().delete()
            
            # Calculate totals
            total_debit = sum(line.get('debit', Decimal('0.00')) for line in lines_data)
            total_credit = sum(line.get('credit', Decimal('0.00')) for line in lines_data)
            
            instance.total_debit = total_debit
            instance.total_credit = total_credit
            
            # Create new lines
            for line_data in lines_data:
                JournalLine.objects.create(
                    journal_entry=instance,
                    tenant=instance.tenant,
                    **line_data
                )
        
        instance.save()
        return instance


class BankAccountSerializer(serializers.ModelSerializer):
    """Serializer for Bank Accounts"""
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)
    gl_account_code = serializers.CharField(source='gl_account.code', read_only=True)
    
    class Meta:
        model = BankAccount
        fields = [
            'id', 'bank_name', 'account_name', 'account_number', 'type', 'branch',
            'swift_code', 'gl_account', 'gl_account_name', 'gl_account_code',
            'balance', 'last_reconciled', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'gl_account_name', 'gl_account_code', 'created_at', 'updated_at']


class BankTransactionSerializer(serializers.ModelSerializer):
    """Serializer for Bank Transactions"""
    bank_account_name = serializers.CharField(source='bank_account.account_name', read_only=True)
    journal_entry_number = serializers.CharField(source='journal_entry.entry_number', read_only=True)
    
    class Meta:
        model = BankTransaction
        fields = [
            'id', 'bank_account', 'bank_account_name', 'date', 'reference', 'description',
            'type', 'debit', 'credit', 'balance', 'reconciled', 'reconciled_date',
            'journal_entry', 'journal_entry_number', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'bank_account_name', 'journal_entry_number', 'created_at', 'updated_at', 'balance']

    def create(self, validated_data):
        bank_account = validated_data['bank_account']
        debit = validated_data.get('debit', Decimal('0')) or Decimal('0')
        credit = validated_data.get('credit', Decimal('0')) or Decimal('0')

        last_tx = (
            BankTransaction.objects.filter(bank_account=bank_account)
            .order_by('-date', '-id')
            .first()
        )
        prev_balance = last_tx.balance if last_tx else bank_account.balance
        new_balance = prev_balance + credit - debit
        validated_data['balance'] = new_balance

        transaction = super().create(validated_data)

        bank_account.balance = new_balance
        bank_account.save(update_fields=['balance', 'updated_at'])
        return transaction


class TaxRuleSerializer(serializers.ModelSerializer):
    """Serializer for Tax Rules"""
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    
    class Meta:
        model = TaxRule
        fields = [
            'id', 'name', 'type', 'rate', 'applicable_on', 'account', 'account_name',
            'account_code', 'status', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'account_name', 'account_code', 'created_at', 'updated_at']


class VATReturnSerializer(serializers.ModelSerializer):
    """Serializer for VAT Returns"""
    
    class Meta:
        model = VATReturn
        fields = [
            'id', 'return_number', 'period', 'from_date', 'to_date', 'output_tax',
            'input_tax', 'net_payable', 'status', 'filed_date', 'paid_date',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'return_number', 'net_payable', 'created_at', 'updated_at']
    
    def validate(self, data):
        output_tax = data.get(
            'output_tax',
            self.instance.output_tax if self.instance else Decimal('0.00'),
        )
        input_tax = data.get(
            'input_tax',
            self.instance.input_tax if self.instance else Decimal('0.00'),
        )
        data['net_payable'] = output_tax - input_tax
        return data
    
    def create(self, validated_data):
        # Generate return number
        tenant = validated_data['tenant']
        last_return = VATReturn.objects.filter(tenant=tenant).order_by('-id').first()
        if last_return and last_return.return_number.startswith('VAT-'):
            try:
                last_num = int(last_return.return_number.split('-')[1])
                return_number = f"VAT-{last_num + 1:04d}"
            except:
                return_number = f"VAT-0001"
        else:
            return_number = f"VAT-0001"
        
        validated_data['return_number'] = return_number
        
        return super().create(validated_data)
