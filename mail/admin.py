import csv

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import escape, format_html

from mail.models import (
    EmailBranding, EmailLog, EmailQueue, EmailTemplate,
    MarketingCampaign, SmtpSettings,
)
from mail import services


class SmtpSettingsAdminForm(forms.ModelForm):
    smtp_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'width:100%;max-width:480px'}),
        label='SMTP password',
        help_text='Leave blank to keep the current password.',
    )

    class Meta:
        model = SmtpSettings
        fields = '__all__'
        exclude = ['password_encrypted']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['smtp_password'].initial = self.instance.get_password()

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get('smtp_password')
        if raw:
            instance.set_password(raw)
        if commit:
            instance.save()
        return instance


@admin.register(SmtpSettings)
class SmtpSettingsAdmin(admin.ModelAdmin):
    form = SmtpSettingsAdminForm
    change_form_template = 'admin/mail/smtp_change_form.html'

    readonly_fields = ['smtp_health', 'updated_at']

    fieldsets = (
        ('SMTP connection', {
            'fields': ('smtp_health', 'enabled', 'host', 'port', 'encryption', 'connection_timeout'),
        }),
        ('Authentication', {
            'fields': ('username', 'smtp_password'),
        }),
        ('Sender identity', {
            'fields': ('sender_name', 'sender_email', 'reply_to_email', 'default_signature'),
        }),
        ('Queue & delivery', {
            'fields': ('queue_enabled', 'retry_failed', 'max_retries', 'rate_limit_per_minute'),
        }),
        ('Meta', {'fields': ('updated_at',)}),
    )

    @admin.display(description='Connection status')
    def smtp_health(self, obj):
        if not obj.enabled:
            return format_html('<span style="color:#6b7280;">SMTP disabled</span>')
        ok, msg = services.test_smtp_connection()
        color = '#16a34a' if ok else '#dc2626'
        return format_html('<span style="color:{};">{}</span>', color, msg)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('test-connection/', self.admin_site.admin_view(self.test_connection), name='mail_smtp_test'),
            path('send-test/', self.admin_site.admin_view(self.send_test), name='mail_smtp_send_test'),
        ]
        return custom + urls

    def test_connection(self, request):
        ok, msg = services.test_smtp_connection()
        level = messages.SUCCESS if ok else messages.ERROR
        self.message_user(request, msg, level)
        return HttpResponseRedirect(reverse('admin:mail_smtpsettings_change', args=(1,)))

    def send_test(self, request):
        if request.method == 'POST':
            to_email = request.POST.get('to_email', request.user.email)
            ok, msg = services.send_test_email(to_email)
            level = messages.SUCCESS if ok else messages.ERROR
            self.message_user(request, msg, level)
            return HttpResponseRedirect(reverse('admin:mail_smtpsettings_change', args=(1,)))
        return render(request, 'admin/mail/send_test_email.html', {
            'title': 'Send test email',
            'default_email': request.user.email,
        })

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse('admin:mail_smtpsettings_change', args=(1,)))

    def has_add_permission(self, request):
        return not SmtpSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailBranding)
class EmailBrandingAdmin(admin.ModelAdmin):
    readonly_fields = ['updated_at']
    fieldsets = (
        ('Brand', {'fields': ('company_name', 'logo_url', 'primary_color', 'secondary_color')}),
        ('Footer & links', {'fields': ('footer_text', 'website_url', 'support_email', 'unsubscribe_url', 'social_links')}),
        ('Marketing', {'fields': ('marketing_emails_enabled',)}),
        ('Meta', {'fields': ('updated_at',)}),
    )

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse('admin:mail_emailbranding_change', args=(1,)))

    def has_add_permission(self, request):
        return not EmailBranding.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    change_form_template = 'admin/mail/emailtemplate_change_form.html'
    list_display = ['name', 'slug', 'category', 'is_active', 'is_system', 'updated_at']
    list_filter = ['category', 'is_active', 'is_system']
    search_fields = ['name', 'slug', 'subject']
    readonly_fields = ['is_system', 'created_at', 'updated_at', 'email_preview']
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'category', 'is_active', 'is_system')}),
        ('Content', {
            'fields': ('subject', 'html_body', 'text_body', 'email_preview'),
            'description': (
                'Variables: {{first_name}}, {{last_name}}, {{email}}, {{company_name}}, '
                '{{verification_link}}, {{invitation_link}}, {{dashboard_url}}, {{unsubscribe_link}}, '
                '{{organization_name}}, {{plan_name}}, {{amount_display}}, {{period_end}}, '
                '{{billing_url}}, {{transaction_uuid}}, {{payment_method}}, {{failure_reason}}'
            ),
        }),
        ('Meta', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Preview')
    def email_preview(self, obj):
        if not obj or not obj.pk:
            return format_html(
                '<p style="color:#6b7280;margin:0;">Save the template to see a live preview with sample data.</p>'
            )
        preview_url = reverse('admin:mail_emailtemplate_preview', args=[obj.pk])
        return format_html(
            '<div id="email-template-preview" data-preview-url="{}">'
            '<p style="margin:0 0 8px;color:#374151;font-size:13px;">'
            '<strong>Subject:</strong> <span id="email-preview-subject">—</span></p>'
            '<p style="margin:0 0 10px;">'
            '<button type="button" class="button" id="email-preview-refresh">Refresh preview</button>'
            '<span style="margin-left:10px;color:#6b7280;font-size:12px;">'
            'Renders current editor content with sample placeholder data</span></p>'
            '<iframe id="email-preview-frame" title="Email preview" '
            'style="width:100%;min-height:520px;border:1px solid #d1d5db;border-radius:8px;background:#fff;">'
            '</iframe></div>',
            preview_url,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/preview/',
                self.admin_site.admin_view(self.preview_template),
                name='mail_emailtemplate_preview',
            ),
        ]
        return custom + urls

    def preview_template(self, request, object_id):
        obj = get_object_or_404(EmailTemplate, pk=object_id)

        subject = obj.subject
        html_body = obj.html_body
        if request.method == 'POST':
            import json
            try:
                payload = json.loads(request.body.decode('utf-8'))
                subject = payload.get('subject', subject)
                html_body = payload.get('html_body', html_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        try:
            rendered_subject, rendered_html = services.render_email_preview(subject, html_body)
        except Exception as exc:
            if request.method == 'POST' and request.GET.get('meta') == '1':
                return JsonResponse({'error': str(exc)}, status=400)
            error_html = (
                '<html><body style="font-family:sans-serif;padding:24px;color:#dc2626;">'
                f'<h2>Template error</h2><pre>{escape(str(exc))}</pre></body></html>'
            )
            error_response = HttpResponse(error_html, content_type='text/html')
            error_response['X-Frame-Options'] = 'SAMEORIGIN'
            return error_response

        if request.method == 'POST' and request.GET.get('meta') == '1':
            return JsonResponse({'subject': rendered_subject})

        banner = (
            '<div style="background:#f3f4f6;border-bottom:1px solid #e5e7eb;padding:12px 16px;'
            'font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;color:#111827;">'
            f'<strong>Subject:</strong> {escape(rendered_subject)}</div>'
        )
        lower = rendered_html.lower()
        if '<body' in lower:
            idx = lower.find('<body')
            end = lower.find('>', idx)
            if end != -1:
                rendered_html = rendered_html[: end + 1] + banner + rendered_html[end + 1 :]
            else:
                rendered_html = banner + rendered_html
        else:
            rendered_html = (
                '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
                f'{banner}{rendered_html}</body></html>'
            )

        response = HttpResponse(rendered_html, content_type='text/html; charset=utf-8')
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'template', 'segment', 'status', 'scheduled_at', 'sent_at', 'created_at']
    list_filter = ['status', 'segment']
    search_fields = ['name']
    actions = ['duplicate_campaign', 'send_campaign_now', 'export_campaign_analytics']

    @admin.action(description='Duplicate selected campaigns')
    def duplicate_campaign(self, request, queryset):
        for c in queryset:
            MarketingCampaign.objects.create(
                name=f'{c.name} (copy)',
                template=c.template,
                segment=c.segment,
                custom_recipients=c.custom_recipients,
                subject_override=c.subject_override,
                status='draft',
                created_by=request.user,
            )

    @admin.action(description='Send campaign now')
    def send_campaign_now(self, request, queryset):
        for campaign in queryset:
            try:
                count = services.launch_campaign(campaign)
                self.message_user(request, f'Sent "{campaign.name}" to {count} recipients.', messages.SUCCESS)
            except Exception as exc:
                self.message_user(request, f'Failed "{campaign.name}": {exc}', messages.ERROR)

    @admin.action(description='Export campaign analytics (CSV)')
    def export_campaign_analytics(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="campaign-analytics.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'campaign', 'status', 'recipients', 'delivered', 'opened', 'clicked',
            'failed', 'bounced', 'unsubscribed', 'spam',
        ])
        for campaign in queryset:
            stats = services.campaign_analytics(campaign)
            writer.writerow([
                stats['campaign'], stats['status'], stats['recipients'], stats['delivered'],
                stats['opened'], stats['clicked'], stats['failed'], stats['bounced'],
                stats['unsubscribed'], stats['spam'],
            ])
        return response


@admin.register(EmailQueue)
class EmailQueueAdmin(admin.ModelAdmin):
    list_display = ['to_email', 'subject', 'status', 'retry_count', 'scheduled_for', 'sent_at']
    list_filter = ['status']
    search_fields = ['to_email', 'subject']
    readonly_fields = ['created_at', 'sent_at', 'last_error']
    actions = ['retry_failed_queue', 'pause_queue']

    @admin.action(description='Retry failed / re-queue')
    def retry_failed_queue(self, request, queryset):
        updated = queryset.filter(status='failed').update(status='queued', retry_count=0)
        self.message_user(request, f'Re-queued {updated} emails.')

    @admin.action(description='Pause selected')
    def pause_queue(self, request, queryset):
        queryset.update(status='paused')


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['to_email', 'subject', 'status', 'template_slug', 'open_count', 'click_count', 'created_at']
    list_filter = ['status', 'category', 'template_slug']
    search_fields = ['to_email', 'subject']
    readonly_fields = ['tracking_id', 'created_at', 'opened_at', 'clicked_at', 'metadata']
    date_hierarchy = 'created_at'
    actions = ['retry_as_new']

    @admin.action(description='Retry failed (re-queue)')
    def retry_as_new(self, request, queryset):
        for log in queryset.filter(status='failed'):
            EmailQueue.objects.create(
                to_email=log.to_email,
                subject=log.subject,
                html_body=log.metadata.get('html_body', log.subject),
                status='queued',
                metadata={'log_id': str(log.tracking_id)},
            )
