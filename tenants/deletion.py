"""Ordered teardown of tenant-scoped data before deleting a tenant."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

from .membership_models import UserTenantMembership

# Most dependent models first to satisfy PROTECT foreign keys.
TENANT_MODEL_DELETE_ORDER = [
    "sales.PaymentReceived",
    "sales.CustomerLedger",
    "accounting.JournalLine",
    "accounting.BankTransaction",
    "pos.POSTransactionLine",
    "pos.POSTransaction",
    "sales.CreditNote",
    "sales.Invoice",
    "sales.QuotationLine",
    "sales.Quotation",
    "sales.SalesOrderLine",
    "sales.SalesOrder",
    "purchase.DebitNote",
    "purchase.PurchaseInvoice",
    "purchase.PurchaseOrderLine",
    "purchase.PurchaseOrder",
    "purchase.PurchaseRequestLine",
    "purchase.PurchaseRequest",
    "accounting.JournalEntry",
    "accounting.BankAccount",
    "accounting.TaxRule",
    "accounting.VATReturn",
    "inventory.StockMovement",
    "inventory.Stock",
    "inventory.CustomerSpecificPrice",
    "inventory.PriceHistory",
    "inventory.BulkPricing",
    "inventory.Product",
    "inventory.Warehouse",
    "inventory.Category",
    "inventory.UnitOfMeasure",
    "sales.Customer",
    "purchase.Supplier",
    "accounting.Account",
    "construction.MaterialConsumption",
    "construction.EquipmentUsageLog",
    "construction.DailyLog",
    "construction.Attendance",
    "construction.Worker",
    "construction.Equipment",
    "construction.Site",
    "pos.POSSession",
    "pos.POSDiscount",
    "pos.POSDailySalesReport",
    "hr.Payroll",
    "hr.LeaveRequest",
    "hr.Attendance",
    "hr.Employee",
    "hr.LeaveType",
    "hr.Department",
    "reports.CustomReport",
    "users.Notification",
    "users.RolePermission",
    "billing.BillingPayment",
    "billing.Subscription",
    "tenants.OrganizationInvitation",
]


def delete_tenant(instance) -> None:
    """Delete all data for a tenant, then the tenant record itself."""
    User = get_user_model()

    with transaction.atomic():
        for label in TENANT_MODEL_DELETE_ORDER:
            try:
                model = apps.get_model(label)
            except LookupError:
                continue

            if not any(f.name == "tenant" for f in model._meta.fields):
                continue

            model.objects.filter(tenant=instance).delete()

        User.objects.filter(tenant=instance).update(tenant=None)
        UserTenantMembership.objects.filter(tenant=instance).delete()
        instance.delete()
