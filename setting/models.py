from django.db import models


class DefaultAppearanceSettings(models.Model):
    """
    Site-wide default appearance settings applied to newly registered users.
    Singleton model — only one row is ever expected to exist (pk=1).
    Configured by platform admins via /admin.
    """

    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    ]

    NAVBAR_POSITION_CHOICES = [
        ('left', 'Left'),
        ('top', 'Top'),
    ]

    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='light',
        help_text='Default interface theme for new users'
    )

    navbar_position = models.CharField(
        max_length=10,
        choices=NAVBAR_POSITION_CHOICES,
        default='top',
        help_text='Default app bar position for new users (left or top)'
    )

    accent_color = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        default='#8B5CF6',
        help_text='Default accent color for new users (hex code, e.g., #3B82F6)'
    )

    sidebar_color = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        default='#0F172A',
        help_text='Default sidebar background color for new users (hex code)'
    )

    navbar_color = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        help_text='Default navbar/icon-rail background color for new users (hex code)'
    )

    border_radius = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default='1rem',
        help_text='Default global border radius for new users (CSS length, e.g. 0.625rem)'
    )

    compact_mode = models.BooleanField(
        default=False,
        help_text='Default compact display mode for new users'
    )

    smooth_animations = models.BooleanField(
        default=True,
        help_text='Default smooth animations setting for new users'
    )

    high_contrast = models.BooleanField(
        default=False,
        help_text='Default high contrast mode for new users'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'default_appearance_settings'
        verbose_name = 'Default Appearance Settings'
        verbose_name_plural = 'Default Appearance Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Default Appearance Settings"


class GoogleOAuthSettings(models.Model):
    """Singleton platform settings for Google sign-in on login and signup."""

    enabled = models.BooleanField(
        default=False,
        help_text='Allow users to sign in with Google on /auth/login and /auth/signup',
    )
    client_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='OAuth 2.0 Client ID from Google Cloud Console (Web application)',
    )
    client_secret_encrypted = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_google_oauth_settings'
        verbose_name = 'Google sign-in'
        verbose_name_plural = 'Google sign-in'

    def __str__(self):
        state = 'Enabled' if self.enabled else 'Disabled'
        return f'Google OAuth — {state}'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    def set_client_secret(self, raw_secret: str):
        from mail.encryption import encrypt_value
        self.client_secret_encrypted = encrypt_value(raw_secret) if raw_secret else ''

    def get_client_secret(self) -> str:
        from mail.encryption import decrypt_value
        return decrypt_value(self.client_secret_encrypted)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EsewaSettings(models.Model):
    """Singleton platform settings for eSewa subscription payments."""

    enabled = models.BooleanField(
        default=True,
        help_text='Enable eSewa payments for subscription billing',
    )
    use_sandbox = models.BooleanField(
        default=True,
        help_text='Use eSewa test/sandbox environment (disable for live payments)',
    )
    product_code = models.CharField(
        max_length=100,
        blank=True,
        help_text='Merchant product code from eSewa (e.g. EPAYTEST for sandbox)',
    )
    secret_key = models.CharField(
        max_length=255,
        blank=True,
        help_text='eSewa HMAC secret key — keep confidential',
    )
    frontend_url = models.URLField(
        blank=True,
        help_text='Customer app base URL (e.g. http://localhost:3000)',
    )
    success_url = models.URLField(
        blank=True,
        help_text='Where eSewa redirects after successful payment. Leave blank to auto-use {frontend}/settings/billing/success',
    )
    failure_url = models.URLField(
        blank=True,
        help_text='Where eSewa redirects after failed/cancelled payment. Leave blank to auto-use {frontend}/settings/billing/failure',
    )
    payment_url = models.URLField(
        blank=True,
        help_text='eSewa payment form POST URL. Leave blank for sandbox/production default.',
    )
    status_url = models.URLField(
        blank=True,
        help_text='eSewa transaction verification API URL. Leave blank for sandbox/production default.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_esewa_settings'
        verbose_name = 'eSewa integration'
        verbose_name_plural = 'eSewa integration'

    def __str__(self):
        mode = 'Sandbox' if self.use_sandbox else 'Production'
        state = 'Enabled' if self.enabled else 'Disabled'
        return f'eSewa — {state} ({mode})'

    def delete(self, *args, **kwargs):
        pass

    def _base_frontend_url(self) -> str:
        from django.conf import settings as django_settings
        return (self.frontend_url or getattr(django_settings, 'FRONTEND_URL', '')).rstrip('/')

    def resolved_success_url(self) -> str:
        return self.success_url or (
            f'{self._base_frontend_url()}/settings/billing/success'
            if self._base_frontend_url() else ''
        )

    def resolved_failure_url(self) -> str:
        return self.failure_url or (
            f'{self._base_frontend_url()}/settings/billing/failure'
            if self._base_frontend_url() else ''
        )

    def resolved_payment_url(self) -> str:
        from billing.esewa_config import ESEWA_PRODUCTION, ESEWA_SANDBOX
        if self.payment_url:
            return self.payment_url
        endpoints = ESEWA_SANDBOX if self.use_sandbox else ESEWA_PRODUCTION
        return endpoints['payment_url']

    def resolved_status_url(self) -> str:
        from billing.esewa_config import ESEWA_PRODUCTION, ESEWA_SANDBOX
        if self.status_url:
            return self.status_url
        endpoints = ESEWA_SANDBOX if self.use_sandbox else ESEWA_PRODUCTION
        return endpoints['status_url']

    def save(self, *args, **kwargs):
        self.pk = 1
        base = self._base_frontend_url()
        if base and not self.success_url:
            self.success_url = f'{base}/settings/billing/success'
        if base and not self.failure_url:
            self.failure_url = f'{base}/settings/billing/failure'
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        from django.conf import settings as django_settings

        frontend = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'enabled': True,
                'use_sandbox': True,
                'product_code': getattr(django_settings, 'ESEWA_PRODUCT_CODE', 'EPAYTEST'),
                'secret_key': getattr(django_settings, 'ESEWA_SECRET_KEY', ''),
                'frontend_url': frontend,
                'success_url': f'{frontend}/settings/billing/success',
                'failure_url': f'{frontend}/settings/billing/failure',
            },
        )
        return obj


class SiteSettings(models.Model):
    """Singleton public site identity, branding, and SEO defaults."""

    site_name = models.CharField(max_length=120, default='KHATA')
    tagline = models.CharField(
        max_length=255,
        blank=True,
        help_text='Short subtitle shown in auth pages and marketing surfaces.',
    )
    logo = models.ImageField(
        upload_to='site/',
        null=True,
        blank=True,
        help_text='Recommended PNG/SVG, ~180×48px.',
    )
    favicon = models.ImageField(
        upload_to='site/',
        null=True,
        blank=True,
        help_text='Square icon, 32×32 or 64×64 PNG/ICO.',
    )
    seo_title = models.CharField(
        max_length=70,
        blank=True,
        help_text='Default browser tab title (falls back to site name).',
    )
    meta_description = models.CharField(
        max_length=320,
        blank=True,
        help_text='Default meta description for search engines.',
    )
    meta_keywords = models.CharField(
        max_length=255,
        blank=True,
        help_text='Comma-separated SEO keywords.',
    )
    og_image = models.ImageField(
        upload_to='site/',
        null=True,
        blank=True,
        help_text='Open Graph image for social sharing (1200×630 recommended).',
    )
    allow_search_indexing = models.BooleanField(
        default=True,
        help_text='When disabled, adds noindex guidance for public pages.',
    )
    
    # Cloudinary Configuration
    use_cloudinary = models.BooleanField(
        default=False,
        help_text='Enable Cloudinary for image storage (cloud-based CDN)',
    )
    cloudinary_cloud_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Your Cloudinary cloud name',
    )
    cloudinary_api_key = models.CharField(
        max_length=100,
        blank=True,
        help_text='Your Cloudinary API key',
    )
    cloudinary_api_secret = models.CharField(
        max_length=100,
        blank=True,
        help_text='Your Cloudinary API secret (stored securely)',
    )
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'setting_site_settings'
        verbose_name = 'Site settings'
        verbose_name_plural = 'Site settings'

    def __str__(self):
        return f'Site — {self.site_name}'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'site_name': 'KHATA',
                'tagline': "Nepal's Business Operating System",
                'seo_title': "Khata — Nepal's Business Operating System",
                'meta_description': 'Multi-tenant ERP platform for Nepali businesses.',
            },
        )
        return obj
