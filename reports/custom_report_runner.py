"""
Custom report field catalogs and execution engine.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum, Q, F
from django.db.models.functions import Coalesce
from django.utils import timezone


def _decimal(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "pk"):
        return str(value)
    return value


MODULE_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "sales": {
        "label": "Sales",
        "default_fields": ["date", "order_number", "customer", "total", "status"],
        "date_field": "date",
        "fields": {
            "date": {"label": "Date", "type": "date"},
            "order_number": {"label": "Order #", "type": "string"},
            "customer": {"label": "Customer", "type": "string"},
            "reference": {"label": "Reference", "type": "string"},
            "status": {"label": "Status", "type": "string"},
            "payment_type": {"label": "Payment Type", "type": "string"},
            "subtotal": {"label": "Subtotal", "type": "number"},
            "discount": {"label": "Discount", "type": "number"},
            "tax": {"label": "Tax", "type": "number"},
            "total": {"label": "Total", "type": "number"},
        },
    },
    "purchase": {
        "label": "Purchase",
        "default_fields": ["date", "po_number", "supplier", "total", "status"],
        "date_field": "date",
        "fields": {
            "date": {"label": "Date", "type": "date"},
            "po_number": {"label": "PO #", "type": "string"},
            "supplier": {"label": "Supplier", "type": "string"},
            "reference": {"label": "Reference", "type": "string"},
            "status": {"label": "Status", "type": "string"},
            "subtotal": {"label": "Subtotal", "type": "number"},
            "tax": {"label": "Tax", "type": "number"},
            "total": {"label": "Total", "type": "number"},
        },
    },
    "inventory": {
        "label": "Inventory",
        "default_fields": ["name", "sku", "category", "cost_price", "selling_price", "status"],
        "date_field": None,
        "fields": {
            "name": {"label": "Product", "type": "string"},
            "sku": {"label": "SKU", "type": "string"},
            "category": {"label": "Category", "type": "string"},
            "unit": {"label": "Unit", "type": "string"},
            "cost_price": {"label": "Cost Price", "type": "number"},
            "selling_price": {"label": "Selling Price", "type": "number"},
            "reorder_level": {"label": "Reorder Level", "type": "number"},
            "stock": {"label": "Stock Qty", "type": "number"},
            "status": {"label": "Status", "type": "string"},
        },
    },
    "accounting": {
        "label": "Accounting",
        "default_fields": ["date", "entry_number", "type", "description", "total_debit", "status"],
        "date_field": "date",
        "fields": {
            "date": {"label": "Date", "type": "date"},
            "entry_number": {"label": "Entry #", "type": "string"},
            "reference": {"label": "Reference", "type": "string"},
            "description": {"label": "Description", "type": "string"},
            "type": {"label": "Type", "type": "string"},
            "status": {"label": "Status", "type": "string"},
            "total_debit": {"label": "Total Debit", "type": "number"},
            "total_credit": {"label": "Total Credit", "type": "number"},
        },
    },
    "hr": {
        "label": "HR",
        "default_fields": ["name", "department", "designation", "employment_type", "basic_salary", "status"],
        "date_field": "join_date",
        "fields": {
            "name": {"label": "Employee", "type": "string"},
            "department": {"label": "Department", "type": "string"},
            "designation": {"label": "Designation", "type": "string"},
            "employment_type": {"label": "Employment Type", "type": "string"},
            "join_date": {"label": "Join Date", "type": "date"},
            "phone": {"label": "Phone", "type": "string"},
            "email": {"label": "Email", "type": "string"},
            "basic_salary": {"label": "Basic Salary", "type": "number"},
            "status": {"label": "Status", "type": "string"},
        },
    },
    "pos": {
        "label": "POS",
        "default_fields": ["date", "transaction_number", "customer", "payment_method", "total", "status"],
        "date_field": "date",
        "fields": {
            "date": {"label": "Date", "type": "date"},
            "transaction_number": {"label": "Transaction #", "type": "string"},
            "customer": {"label": "Customer", "type": "string"},
            "payment_method": {"label": "Payment Method", "type": "string"},
            "subtotal": {"label": "Subtotal", "type": "number"},
            "discount_amount": {"label": "Discount", "type": "number"},
            "tax_amount": {"label": "Tax", "type": "number"},
            "total": {"label": "Total", "type": "number"},
            "status": {"label": "Status", "type": "string"},
        },
    },
}

FILTER_OPERATORS = ["equals", "contains", "gt", "lt", "gte", "lte"]


def get_module_fields_catalog(module: str | None = None) -> dict[str, Any]:
    if module:
        config = MODULE_FIELD_CATALOG.get(module)
        if not config:
            return {}
        return {
            module: {
                "label": config["label"],
                "fields": [
                    {"key": key, **meta}
                    for key, meta in config["fields"].items()
                ],
                "default_fields": config["default_fields"],
                "filter_operators": FILTER_OPERATORS,
            }
        }
    return {
        mod: {
            "label": cfg["label"],
            "fields": [{"key": key, **meta} for key, meta in cfg["fields"].items()],
            "default_fields": cfg["default_fields"],
            "filter_operators": FILTER_OPERATORS,
        }
        for mod, cfg in MODULE_FIELD_CATALOG.items()
    }


def _parse_run_dates(from_date_str: str | None, to_date_str: str | None) -> tuple[date | None, date | None]:
    from_date = None
    to_date = None
    if from_date_str:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    if to_date_str:
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
    return from_date, to_date


def _apply_filter(qs, field_key: str, operator: str, value: Any, field_map: dict[str, str]):
    lookup = field_map.get(field_key, field_key)
    op = (operator or "equals").lower()
    if op == "contains":
        return qs.filter(**{f"{lookup}__icontains": value})
    if op == "gt":
        return qs.filter(**{f"{lookup}__gt": value})
    if op == "lt":
        return qs.filter(**{f"{lookup}__lt": value})
    if op == "gte":
        return qs.filter(**{f"{lookup}__gte": value})
    if op == "lte":
        return qs.filter(**{f"{lookup}__lte": value})
    return qs.filter(**{lookup: value})


def _row_from_sales(order, field_keys: list[str]) -> dict[str, Any]:
    mapping = {
        "date": order.date,
        "order_number": order.order_number,
        "customer": order.customer.name if order.customer_id else "",
        "reference": order.reference or "",
        "status": order.status,
        "payment_type": order.payment_type,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "tax": order.tax,
        "total": order.total,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _row_from_purchase(order, field_keys: list[str]) -> dict[str, Any]:
    mapping = {
        "date": order.date,
        "po_number": order.po_number,
        "supplier": order.supplier.name if order.supplier_id else "",
        "reference": order.reference or "",
        "status": order.status,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "total": order.total,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _row_from_product(product, field_keys: list[str]) -> dict[str, Any]:
    mapping = {
        "name": product.name,
        "sku": product.sku,
        "category": product.category.name if product.category_id else "",
        "unit": product.unit.name if product.unit_id else "",
        "cost_price": product.cost_price,
        "selling_price": product.selling_price,
        "reorder_level": product.reorder_level,
        "stock": product.get_total_stock(),
        "status": product.status,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _row_from_journal(entry, field_keys: list[str]) -> dict[str, Any]:
    mapping = {
        "date": entry.date,
        "entry_number": entry.entry_number,
        "reference": entry.reference or "",
        "description": entry.description,
        "type": entry.type,
        "status": entry.status,
        "total_debit": entry.total_debit,
        "total_credit": entry.total_credit,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _row_from_employee(employee, field_keys: list[str]) -> dict[str, Any]:
    mapping = {
        "name": employee.name,
        "department": employee.department.name if employee.department_id else "",
        "designation": employee.designation,
        "employment_type": employee.employment_type,
        "join_date": employee.join_date,
        "phone": employee.phone,
        "email": employee.email,
        "basic_salary": employee.basic_salary,
        "status": employee.status,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _row_from_pos(txn, field_keys: list[str]) -> dict[str, Any]:
    customer = txn.customer.name if txn.customer_id else (txn.customer_name or "Walk-in")
    mapping = {
        "date": txn.date.date() if hasattr(txn.date, "date") else txn.date,
        "transaction_number": txn.transaction_number,
        "customer": customer,
        "payment_method": txn.payment_method,
        "subtotal": txn.subtotal,
        "discount_amount": txn.discount_amount,
        "tax_amount": txn.tax_amount,
        "total": txn.total,
        "status": txn.status,
    }
    return {k: _serialize_value(mapping.get(k)) for k in field_keys}


def _build_chart_data(rows: list[dict[str, Any]], chart_config: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not chart_config:
        return None
    x_axis = chart_config.get("x_axis") or chart_config.get("xAxis")
    y_axis = chart_config.get("y_axis") or chart_config.get("yAxis") or "total"
    if not x_axis or not rows:
        return None
    chart_rows = []
    for row in rows[:50]:
        chart_rows.append({
            "name": str(row.get(x_axis, "")),
            "value": _decimal(row.get(y_axis, 0)),
        })
    return chart_rows


def run_custom_report(report, from_date_str: str | None = None, to_date_str: str | None = None) -> dict[str, Any]:
    from sales.models import SalesOrder
    from purchase.models import PurchaseOrder
    from inventory.models import Product
    from accounting.models import JournalEntry
    from hr.models import Employee
    from pos.models import POSTransaction

    module = report.module
    catalog = MODULE_FIELD_CATALOG.get(module)
    if not catalog:
        raise ValueError(f"Unsupported module: {module}")

    field_keys = list(report.fields or catalog["default_fields"])
    field_keys = [f for f in field_keys if f in catalog["fields"]]
    if not field_keys:
        field_keys = list(catalog["default_fields"])

    columns = [catalog["fields"][k]["label"] for k in field_keys]
    label_to_key = {catalog["fields"][k]["label"]: k for k in field_keys}

    from_date, to_date = _parse_run_dates(from_date_str, to_date_str)
    if not from_date and not to_date and catalog.get("date_field"):
        to_date = timezone.now().date()
        from_date = to_date - timedelta(days=90)

    tenant = report.tenant
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"total_rows": 0}

    if module == "sales":
        qs = SalesOrder.objects.filter(tenant=tenant).select_related("customer")
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)
        filter_map = {
            "customer": "customer__name",
            "status": "status",
            "payment_type": "payment_type",
            "order_number": "order_number",
        }
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "desc")
        if sort_field in {"date", "total", "status", "order_number"}:
            prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{prefix}{sort_field}")
        else:
            qs = qs.order_by("-date")
        for obj in qs[:500]:
            row = _row_from_sales(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        if "total" in field_keys:
            summary["total_amount"] = float(qs.aggregate(t=Coalesce(Sum("total"), Decimal("0")))["t"])

    elif module == "purchase":
        qs = PurchaseOrder.objects.filter(tenant=tenant).select_related("supplier")
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)
        filter_map = {"supplier": "supplier__name", "status": "status", "po_number": "po_number"}
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "desc")
        if sort_field in {"date", "total", "status", "po_number"}:
            prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{prefix}{sort_field}")
        else:
            qs = qs.order_by("-date")
        for obj in qs[:500]:
            row = _row_from_purchase(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        if "total" in field_keys:
            summary["total_amount"] = float(qs.aggregate(t=Coalesce(Sum("total"), Decimal("0")))["t"])

    elif module == "inventory":
        qs = Product.objects.filter(tenant=tenant).select_related("category", "unit")
        filter_map = {"name": "name", "sku": "sku", "status": "status", "category": "category__name"}
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "asc")
        if sort_field in {"name", "sku", "cost_price", "selling_price", "status"}:
            prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{prefix}{sort_field}")
        else:
            qs = qs.order_by("name")
        for obj in qs[:500]:
            row = _row_from_product(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        summary["product_count"] = qs.count()

    elif module == "accounting":
        qs = JournalEntry.objects.filter(tenant=tenant)
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)
        filter_map = {"status": "status", "type": "type", "entry_number": "entry_number"}
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "desc")
        if sort_field in {"date", "entry_number", "total_debit", "status"}:
            prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{prefix}{sort_field}")
        else:
            qs = qs.order_by("-date")
        for obj in qs[:500]:
            row = _row_from_journal(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        if "total_debit" in field_keys:
            summary["total_debit"] = float(qs.aggregate(t=Coalesce(Sum("total_debit"), Decimal("0")))["t"])

    elif module == "hr":
        qs = Employee.objects.filter(tenant=tenant).select_related("department")
        if from_date:
            qs = qs.filter(join_date__gte=from_date)
        if to_date:
            qs = qs.filter(join_date__lte=to_date)
        filter_map = {
            "department": "department__name",
            "status": "status",
            "employment_type": "employment_type",
            "name": "name",
        }
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "asc")
        if sort_field in {"name", "join_date", "basic_salary", "status"}:
            prefix = "-" if sort_order == "desc" else ""
            qs = qs.order_by(f"{prefix}{sort_field}")
        else:
            qs = qs.order_by("name")
        for obj in qs[:500]:
            row = _row_from_employee(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        if "basic_salary" in field_keys:
            summary["total_salary"] = float(qs.aggregate(t=Coalesce(Sum("basic_salary"), Decimal("0")))["t"])

    elif module == "pos":
        qs = POSTransaction.objects.filter(tenant=tenant).select_related("customer")
        if from_date:
            qs = qs.filter(date__date__gte=from_date)
        if to_date:
            qs = qs.filter(date__date__lte=to_date)
        filter_map = {
            "status": "status",
            "payment_method": "payment_method",
            "transaction_number": "transaction_number",
            "customer": "customer__name",
        }
        for flt in report.filters or []:
            if isinstance(flt, dict) and flt.get("field"):
                qs = _apply_filter(qs, flt["field"], flt.get("operator", "equals"), flt.get("value"), filter_map)
        sort_field = (report.sorting or {}).get("field")
        sort_order = (report.sorting or {}).get("order", "desc")
        if sort_field in {"date", "total", "status", "transaction_number"}:
            if sort_field == "date":
                order = "-date" if sort_order == "desc" else "date"
            else:
                prefix = "-" if sort_order == "desc" else ""
                order = f"{prefix}{sort_field}"
            qs = qs.order_by(order)
        else:
            qs = qs.order_by("-date")
        for obj in qs[:500]:
            row = _row_from_pos(obj, field_keys)
            rows.append({columns[i]: row[field_keys[i]] for i in range(len(field_keys))})
        if "total" in field_keys:
            summary["total_amount"] = float(qs.aggregate(t=Coalesce(Sum("total"), Decimal("0")))["t"])

    summary["total_rows"] = len(rows)

    # Grouping: aggregate by field if requested
    group_field = (report.grouping or {}).get("field")
    if group_field and group_field in catalog["fields"] and rows:
        grouped: dict[str, list[dict[str, Any]]] = {}
        col_label = catalog["fields"][group_field]["label"]
        for row in rows:
            key = str(row.get(col_label, "Unknown"))
            grouped.setdefault(key, []).append(row)
        grouped_rows = []
        amount_col = next((catalog["fields"][k]["label"] for k in field_keys if catalog["fields"][k]["type"] == "number"), None)
        for key, items in grouped.items():
            entry = {col_label: key, "Count": len(items)}
            if amount_col:
                entry[f"Total {amount_col}"] = sum(_decimal(i.get(amount_col, 0)) for i in items)
            grouped_rows.append(entry)
        rows = grouped_rows
        columns = list(grouped_rows[0].keys()) if grouped_rows else columns
        summary["total_rows"] = len(rows)
        summary["grouped_by"] = group_field

    chart_data = None
    if report.report_type in ("chart", "both"):
        keyed_rows = [{label_to_key.get(col, col): row[col] for col in row} for row in rows[:50]] if label_to_key else rows
        chart_data = _build_chart_data(keyed_rows, report.chart_config or {})

    return {
        "columns": columns,
        "rows": rows,
        "summary": summary,
        "chart_data": chart_data,
    }
