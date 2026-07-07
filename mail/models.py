from django.conf import settings
from django.db import models
from django.utils import timezone

from mail.encryption import decrypt_value, encrypt_value


class SmtpSettings(models.Model):
    ENCRYPTION_CHOICES = [
        ('starttls', 'STARTTLS'),
        ('ssl', 'SSL/TLS'),
        ('none', 'None'),
    ]

    enabled = models.BooleanField(default=False)
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, blank=True)
    password_encrypted = models.TextField(blank=True)
    sender_name = models.CharField(max_length=255, default='KHATA')
    sender_email = models.EmailField(blank=True)
    reply_to_email = models.EmailField(blank=True)
    encryption = models.CharField(max_length=20, choices=ENCRYPTION_CHOICES, default='starttls')
    connection_timeout = models.PositiveIntegerField(default=30, help_text='Seconds')
    queue_enabled = models.BooleanField(default=True)
    retry_failed = models.BooleanField(default=True)
    max_retries = models.PositiveIntegerField(default=3)
    rate_limit_per_minute = models.PositiveIntegerField(default=60)
    default_signature = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mail_smtp_settings'
        verbose_name = 'SMTP settings'
        verbose_name_plural = 'SMTP Settings'

    def __str__(self):
        return f'SMTP — {"Enabled" if self.enabled else "Disabled"} ({self.host or "not configured"})'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    def set_password(self, raw_password: str):
        self.password_encrypted = encrypt_value(raw_password) if raw_password else ''

    def get_password(self) -> str:
        return decrypt_value(self.password_encrypted)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EmailBranding(models.Model):
    company_name = models.CharField(max_length=255, default='KHATA')
    logo_url = models.URLField(
        blank=True,
        help_text='Public URL to logo image (recommended 180×48 PNG)',
    )
    primary_color = models.CharField(max_length=7, default='#22C55E')
    secondary_color = models.CharField(max_length=7, default='#111827')
    footer_text = models.TextField(
        blank=True,
        default='© KHATA Business OS. All rights reserved.',
    )
    unsubscribe_url = models.URLField(blank=True)
    website_url = models.URLField(blank=True)
    support_email = models.EmailField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    marketing_emails_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mail_branding'
        verbose_name = 'Email branding'
        verbose_name_plural = 'Email Branding'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        from django.conf import settings as django_settings
        frontend = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'website_url': frontend,
                'unsubscribe_url': f'{frontend}/settings/notifications',
            },
        )
        return obj


class EmailTemplate(models.Model):
    CATEGORY_CHOICES = [
        ('invitation', 'Invitation'),
        ('welcome', 'Welcome / Registration'),
        ('verification', 'Email Verification'),
        ('acceptance', 'Invitation Accepted'),
        ('marketing', 'Marketing'),
        ('transactional', 'Transactional'),
        ('billing', 'Billing & Subscriptions'),
        ('custom', 'Custom'),
    ]

    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='custom')
    subject = models.CharField(max_length=255)
    html_body = models.TextField(help_text='HTML with variables: {{first_name}}, {{invitation_link}}, etc.')
    text_body = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, help_text='System templates cannot be deleted')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mail_templates'
        ordering = ['category', 'name']
        verbose_name = 'Email template'
        verbose_name_plural = 'Email templates'

    def __str__(self):
        return f'{self.name} ({self.slug})'


class MarketingCampaign(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled'),
    ]
    SEGMENT_CHOICES = [
        ('all_users', 'All users'),
        ('tenant_admins', 'Organization admins'),
        ('tenant_managers', 'Managers'),
        ('active_tenants', 'Active organizations'),
        ('custom', 'Custom email list'),
    ]

    name = models.CharField(max_length=255)
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT, related_name='campaigns')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    segment = models.CharField(max_length=30, choices=SEGMENT_CHOICES, default='all_users')
    custom_recipients = models.TextField(
        blank=True,
        help_text='Comma-separated emails when segment is Custom',
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    subject_override = models.CharField(max_length=255, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mail_campaigns'
        ordering = ['-created_at']
        verbose_name = 'Marketing campaign'
        verbose_name_plural = 'Marketing campaigns'

    def __str__(self):
        return f'{self.name} ({self.status})'


class EmailQueue(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('paused', 'Paused'),
    ]

    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    text_body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    priority = models.PositiveSmallIntegerField(default=5)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    scheduled_for = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True)
    template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey(MarketingCampaign, on_delete=models.SET_NULL, null=True, blank=True)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mail_queue'
        ordering = ['priority', 'scheduled_for']
        verbose_name = 'Email queue'
        verbose_name_plural = 'Email queues'
        indexes = [
            models.Index(fields=['status', 'scheduled_for']),
        ]


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('bounced', 'Bounced'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('unsubscribed', 'Unsubscribed'),
        ('spam', 'Spam Complaint'),
    ]

    tracking_id = models.UUIDField(unique=True, editable=False)
    to_email = models.EmailField(db_index=True)
    subject = models.CharField(max_length=255)
    template_slug = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    error_message = models.TextField(blank=True)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
    )
    campaign = models.ForeignKey(MarketingCampaign, on_delete=models.SET_NULL, null=True, blank=True)
    invitation_id = models.PositiveIntegerField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    open_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mail_logs'
        ordering = ['-created_at']
        verbose_name = 'Email log'
        verbose_name_plural = 'Email logs'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['to_email']),
        ]

    def __str__(self):
        return f'{self.to_email} — {self.subject} ({self.status})'
