from decimal import Decimal
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from tenants.models import Tenant
from pos.models import POSTransaction, POSTransactionLine
from pos.serializers import POSRefundCreateSerializer
from inventory.models import Product, Warehouse, UnitOfMeasure

from tenants.middleware import set_current_tenant

User = get_user_model()


class POSRefundCalculationTests(SimpleTestCase):
    def test_refund_amount_uses_discounted_line_total(self):
        line = POSTransactionLine(
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            discount_amount=Decimal("20"),
            line_total=Decimal("180"),
        )

        refund_quantity = Decimal("1")
        expected_refund_amount = Decimal("90")

        self.assertEqual(
            line.get_refund_amount(refund_quantity),
            expected_refund_amount,
        )


class POSRefundSerializerTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="POS Test Tenant")
        set_current_tenant(self.tenant)
        self.user = User.objects.create_user(
            username="testcashier",
            email="cashier@example.com",
            password="password",
            tenant=self.tenant
        )
        self.warehouse = Warehouse.objects.create(
            tenant=self.tenant,
            name="Main Warehouse"
        )
        self.unit = UnitOfMeasure.objects.create(
            tenant=self.tenant,
            name="pieces",
            abbreviation="pcs",
            type="count"
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Rice",
            sku="R123",
            unit=self.unit,
            selling_price=Decimal("13.00")
        )
        self.transaction = POSTransaction.objects.create(
            tenant=self.tenant,
            transaction_number="POS-000003",
            subtotal=Decimal("13.00"),
            total=Decimal("13.00"),
            payment_method="cash",
            amount_paid=Decimal("13.00"),
            status="completed",
            cashier=self.user,
            warehouse=self.warehouse
        )
        self.line = POSTransactionLine.objects.create(
            tenant=self.tenant,
            transaction=self.transaction,
            product=self.product,
            product_name="Rice",
            product_sku="R123",
            quantity=Decimal("1.00"),
            unit_price=Decimal("13.00"),
            line_total=Decimal("13.00")
        )

    def tearDown(self):
        set_current_tenant(None)
        super().tearDown()

    def test_refund_serializer_validation_succeeds_with_valid_line_and_tenant(self):
        # Create a mock request object with the user context
        from types import SimpleNamespace
        request = SimpleNamespace(user=self.user)
        
        # Test input data matching the structure passed by POS frontend
        data = {
            "original_transaction": self.transaction.id,
            "lines": [
                {
                    "original_line": self.line.id,
                    "quantity": 1.00
                }
            ],
            "refund_method": "cash",
            "reason": "Customer request"
        }
        
        serializer = POSRefundCreateSerializer(data=data, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated_data = serializer.validated_data
        self.assertEqual(validated_data['original_transaction'], self.transaction)
        self.assertEqual(validated_data['lines'][0]['original_line'], self.line)


