"""Ordered teardown of tenant-scoped data before deleting a tenant."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

from .membership_models import UserTenantMembership

# Most dependent models first to satisfy PROTECT foreign keys.
TENANT_MODEL_DELETE_ORDER = [
    # Sales - most dependent first
    "sales.PaymentReceived",
    "sales.CustomerLedger",
    
    # Accounting journal lines before entries
    "accounting.JournalLine",
    "accounting.BankTransaction",
    
    # POS - transaction lines and related before transactions
    "pos.POSRefundLine",
    "pos.POSRefund",
    "pos.POSPayment",
    "pos.POSTransactionLine",
    "pos.POSTransaction",
    "pos.POSHeldOrder",
    "pos.POSCashMovement",
    
    # Sales - invoices and orders
    "sales.CreditNote",
    "sales.Invoice",
    "sales.QuotationLine",
    "sales.Quotation",
    "sales.SalesOrderLine",
    "sales.SalesOrder",
    
    # Purchase
    "purchase.DebitNote",
    "purchase.PurchaseInvoice",
    "purchase.PurchaseOrderLine",
    "purchase.PurchaseOrder",
    "purchase.PurchaseRequestLine",
    "purchase.PurchaseRequest",
    
    # Accounting
    "accounting.JournalEntry",
    "accounting.BankAccount",
    "accounting.TaxRule",
    "accounting.VATReturn",
    
    # Finance (Personal Finance module)
    "finance.PartyTransactionShare",
    "finance.PartyTransaction",
    "finance.FinanceBill",
    "finance.FinanceBudget",
    "finance.FinanceTransaction",
    "finance.PartyLender",
    "finance.FinanceCategory",
    "finance.FinanceAccount",
    
    # Inventory
    "inventory.StockMovement",
    "inventory.Stock",
    "inventory.CustomerSpecificPrice",
    "inventory.PriceHistory",
    "inventory.BulkPricing",
    "inventory.Product",
    "inventory.Warehouse",
    "inventory.Category",
    "inventory.UnitOfMeasure",
    
    # Payment methods (before Accounts due to PROTECT FK)
    "accounting.PaymentMethod",
    
    # Master data
    "sales.Customer",
    "purchase.Supplier",
    "accounting.Account",
    
    # Construction
    "construction.MaterialConsumption",
    "construction.EquipmentUsageLog",
    "construction.DailyLog",
    "construction.Attendance",
    "construction.Worker",
    "construction.Equipment",
    "construction.Site",
    
    # POS settings and reports
    "pos.POSSettings",
    "pos.POSSession",
    "pos.POSDiscount",
    "pos.POSDailySalesReport",
    
    # HR
    "hr.Payroll",
    "hr.LeaveRequest",
    "hr.Attendance",
    "hr.Employee",
    "hr.LeaveType",
    "hr.Department",
    
    # Other
    "reports.CustomReport",
    "users.Notification",
    "users.RolePermission",
    "users.AuditLog",
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
