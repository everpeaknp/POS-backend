"""Sales ↔ inventory stock integration."""

from inventory.services import apply_sales_order_stock, reverse_sales_order_stock
from sales.accounting_integration import post_sales_order_cogs, reverse_sales_order_cogs


def handle_sales_order_status_change(sales_order, old_status, new_status, performed_by=None, warehouse_id=None):
    """
    Apply or reverse stock when sales order status changes.
    Stock is deducted on Confirmed/Delivered; restored when cancelled.
    """
    if new_status in ('Confirmed', 'Delivered') and old_status == 'Draft':
        apply_sales_order_stock(sales_order, performed_by=performed_by, warehouse_id=warehouse_id)
        post_sales_order_cogs(sales_order)
        return

    if new_status == 'Cancelled' and old_status in ('Confirmed', 'Delivered'):
        reverse_sales_order_stock(sales_order, performed_by=performed_by)
        reverse_sales_order_cogs(sales_order)
