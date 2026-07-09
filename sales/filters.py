"""Sales API filters."""

import django_filters

from .models import Customer, SalesOrder, Quotation, Invoice, CreditNote, PaymentReceived


class CommaSeparatedInFilter(django_filters.CharFilter):
    """Accept comma-separated values for __in lookups (e.g. status=Sent,Paid)."""

    def filter(self, qs, value):
        if not value:
            return qs
        values = [v.strip() for v in value.split(',') if v.strip()]
        if not values:
            return qs
        return qs.filter(**{f'{self.field_name}__in': values})


class SalesOrderFilterSet(django_filters.FilterSet):
    status = CommaSeparatedInFilter(field_name='status')

    class Meta:
        model = SalesOrder
        fields = ['customer', 'status']


class InvoiceFilterSet(django_filters.FilterSet):
    status = CommaSeparatedInFilter(field_name='status')

    class Meta:
        model = Invoice
        fields = ['customer', 'status']


class QuotationFilterSet(django_filters.FilterSet):
    status = CommaSeparatedInFilter(field_name='status')

    class Meta:
        model = Quotation
        fields = ['customer', 'status']
