from rest_framework import serializers
from .models import Account, JournalEntry, JournalLine, BankAccount, BankTransaction, TaxRule, VATReturn
from decimal import Decimal


class AccountSerializer(serializers.ModelSerializer):
    """Serializer for Chart of Accounts"""
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    
    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'type', 'sub_type', 'level', 'parent', 'parent_name',
            'balance', 'status', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'parent_name']
    
    def validate(self, data):
        # Ensure parent is of same type
        if data.get('parent'):
            if data['parent'].type != data['type']:
                raise serializers.ValidationError("Parent account must be of the same type")
        return data


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
        
        # Calculate totals
        total_debit = sum(line.get('debit', Decimal('0.00')) for line in lines)
        total_credit = sum(line.get('credit', Decimal('0.00')) for line in lines)
        
        if total_debit != total_credit:
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
        last_entry = JournalEntry.objects.filter(tenant=tenant).order_by('-id').first()
        if last_entry and last_entry.entry_number.startswith('JE-'):
            try:
                last_num = int(last_entry.entry_number.split('-')[1])
                entry_number = f"JE-{last_num + 1:04d}"
            except:
                entry_number = f"JE-0001"
        else:
            entry_number = f"JE-0001"
        
        validated_data['entry_number'] = entry_number
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
        read_only_fields = ['id', 'bank_account_name', 'journal_entry_number', 'created_at', 'updated_at']


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
        # Calculate net payable
        output_tax = data.get('output_tax', Decimal('0.00'))
        input_tax = data.get('input_tax', Decimal('0.00'))
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
