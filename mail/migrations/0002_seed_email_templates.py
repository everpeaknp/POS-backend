from django.db import migrations


def seed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('mail', 'EmailTemplate')
    EmailBranding = apps.get_model('mail', 'EmailBranding')
    SmtpSettings = apps.get_model('mail', 'SmtpSettings')

    EmailBranding.objects.get_or_create(pk=1)
    SmtpSettings.objects.get_or_create(pk=1)

    base_style = """
<style>
body{margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
.wrapper{width:100%;background:#f3f4f6;padding:32px 16px;}
.card{max-width:600px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.06);}
.header{background:{{ branding.primary_color|default:'#22C55E' }};padding:28px 32px;text-align:center;color:#fff;font-size:22px;font-weight:700;}
.body{padding:32px;color:#374151;font-size:15px;line-height:1.65;}
.body h1{color:#111827;font-size:22px;margin:0 0 16px;}
.btn{display:inline-block;background:{{ branding.primary_color|default:'#22C55E' }};color:#fff!important;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:600;margin:20px 0;}
.muted{color:#6b7280;font-size:13px;}
.security{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-top:24px;font-size:13px;}
.footer{padding:24px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;font-size:12px;color:#9ca3af;}
</style>
"""

    templates = [
        {
            'slug': 'invitation',
            'name': 'Organization Invitation',
            'category': 'invitation',
            'subject': "You're invited to join {{ company_name }} on KHATA",
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:company_name }}</div>
<div class="body">
<h1>You're invited to join {{ company_name }}</h1>
<p>Hi {{ first_name }},</p>
<p><strong>{{ inviter_name }}</strong> has invited you to join <strong>{{ company_name }}</strong> on KHATA as <strong>{{ role }}</strong>.</p>
{% if custom_message %}<p style="background:#f0fdf4;border-left:4px solid #22C55E;padding:12px 16px;">{{ custom_message }}</p>{% endif %}
<p><a href="{{ invitation_link }}" class="btn">Accept invitation</a></p>
<p class="muted">This invitation expires on {{ expires_at }}.</p>
<div class="security"><strong>Security note:</strong> KHATA will never ask for your password by email.</div>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p><p><a href="{{ unsubscribe_link }}">Unsubscribe</a></p></div>
</div></div>""",
            'is_system': True,
        },
        {
            'slug': 'welcome',
            'name': 'Welcome / Registration',
            'category': 'welcome',
            'subject': 'Welcome to KHATA, {{ first_name }}!',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>Welcome aboard, {{ first_name }}!</h1>
<p>Your KHATA account is ready. Manage inventory, sales, accounting, and more from one place.</p>
<p><a href="{{ dashboard_url }}" class="btn">Go to dashboard</a></p>
<p class="muted">Need help? Contact us at {{ branding.support_email|default:'support@khata.app' }}.</p>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p></div>
</div></div>""",
            'is_system': True,
        },
        {
            'slug': 'verification',
            'name': 'Email Verification',
            'category': 'verification',
            'subject': 'Verify your KHATA email',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>Verify your email</h1>
<p>Hi {{ first_name }}, please confirm your email address to secure your account.</p>
<p><a href="{{ verification_link }}" class="btn">Verify email</a></p>
<p class="muted">If you didn't create a KHATA account, ignore this email.</p>
<div class="security"><strong>Security note:</strong> This link expires in 24 hours.</div>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p></div>
</div></div>""",
            'is_system': True,
        },
        {
            'slug': 'acceptance',
            'name': 'Invitation Accepted',
            'category': 'acceptance',
            'subject': 'You joined {{ company_name }} on KHATA',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>You're now part of {{ company_name }}</h1>
<p>Hi {{ first_name }}, you've successfully joined <strong>{{ company_name }}</strong> as <strong>{{ role }}</strong>.</p>
<p><a href="{{ dashboard_url }}" class="btn">Open dashboard</a></p>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p></div>
</div></div>""",
            'is_system': True,
        },
    ]

    for data in templates:
        EmailTemplate.objects.update_or_create(
            slug=data['slug'],
            defaults={
                'name': data['name'],
                'category': data['category'],
                'subject': data['subject'],
                'html_body': data['html_body'].strip(),
                'text_body': '',
                'is_active': True,
                'is_system': data['is_system'],
            },
        )


def unseed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('mail', 'EmailTemplate')
    EmailTemplate.objects.filter(slug__in=['invitation', 'welcome', 'verification', 'acceptance']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_email_templates, unseed_email_templates),
    ]
