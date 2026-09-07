from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'tenant', 'user', 'category', 'priority', 'status', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['subject', 'message', 'tenant__name', 'user__email', 'user__username']
    readonly_fields = ['tenant', 'user', 'subject', 'category', 'priority', 'message', 'created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        from django.utils import timezone

        if change and 'status' in form.changed_data and obj.status in ('resolved', 'closed'):
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)
