from django.db import migrations


BILLING_TEMPLATE_SLUGS = [
    'billing-plan-activated',
    'billing-payment-success',
    'billing-payment-failed',
]


def seed_billing_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('mail', 'EmailTemplate')

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
.detail{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:20px 0;font-size:14px;}
.detail dt{color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-top:10px;}
.detail dt:first-child{margin-top:0;}
.detail dd{margin:4px 0 0;color:#111827;font-weight:600;}
.warn{background:#fef2f2;border-left:4px solid #ef4444;padding:12px 16px;border-radius:8px;color:#991b1b;}
.footer{padding:24px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;font-size:12px;color:#9ca3af;}
</style>
"""

    templates = [
        {
            'slug': 'billing-plan-activated',
            'name': 'Billing — Plan activated',
            'category': 'billing',
            'subject': '{{ organization_name }} is now on the {{ plan_name }} plan',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>Your plan is active</h1>
<p>Hi {{ first_name }},</p>
<p><strong>{{ organization_name }}</strong> has been switched to the <strong>{{ plan_name }}</strong> plan on KHATA.</p>
<dl class="detail">
<dt>Plan</dt><dd>{{ plan_name }}</dd>
<dt>Monthly price</dt><dd>{{ amount_display }}</dd>
{% if period_end %}<dt>Current period ends</dt><dd>{{ period_end }}</dd>{% endif %}
</dl>
<p><a href="{{ billing_url }}" class="btn">View billing</a></p>
<p class="muted">You can manage your subscription anytime from Settings → Billing.</p>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p><p><a href="{{ unsubscribe_link }}">Notification preferences</a></p></div>
</div></div>""",
        },
        {
            'slug': 'billing-payment-success',
            'name': 'Billing — Payment successful',
            'category': 'billing',
            'subject': 'Payment received for {{ plan_name }} — {{ organization_name }}',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>Payment successful</h1>
<p>Hi {{ first_name }},</p>
<p>We received your payment and activated the <strong>{{ plan_name }}</strong> plan for <strong>{{ organization_name }}</strong>.</p>
<dl class="detail">
<dt>Amount paid</dt><dd>{{ amount_display }}</dd>
<dt>Plan</dt><dd>{{ plan_name }}</dd>
<dt>Transaction ID</dt><dd>{{ transaction_uuid }}</dd>
{% if period_end %}<dt>Subscription valid until</dt><dd>{{ period_end }}</dd>{% endif %}
<dt>Payment method</dt><dd>{{ payment_method }}</dd>
</dl>
<p><a href="{{ billing_url }}" class="btn">View billing & receipt</a></p>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p><p><a href="{{ unsubscribe_link }}">Notification preferences</a></p></div>
</div></div>""",
        },
        {
            'slug': 'billing-payment-failed',
            'name': 'Billing — Payment failed',
            'category': 'billing',
            'subject': 'Payment could not be completed for {{ plan_name }}',
            'html_body': base_style + """
<div class="wrapper"><div class="card">
<div class="header">{{ branding.company_name|default:'KHATA' }}</div>
<div class="body">
<h1>Payment not completed</h1>
<p>Hi {{ first_name }},</p>
<p>Your payment for the <strong>{{ plan_name }}</strong> plan for <strong>{{ organization_name }}</strong> could not be completed.</p>
{% if failure_reason %}<div class="warn">{{ failure_reason }}</div>{% endif %}
<dl class="detail">
<dt>Amount</dt><dd>{{ amount_display }}</dd>
<dt>Transaction ID</dt><dd>{{ transaction_uuid }}</dd>
</dl>
<p>You can try again from your billing settings. No charges were applied to your subscription.</p>
<p><a href="{{ billing_url }}" class="btn">Try again</a></p>
</div>
<div class="footer"><p>{{ branding.footer_text }}</p><p><a href="{{ unsubscribe_link }}">Notification preferences</a></p></div>
</div></div>""",
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
                'is_system': True,
            },
        )


def unseed_billing_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('mail', 'EmailTemplate')
    EmailTemplate.objects.filter(slug__in=BILLING_TEMPLATE_SLUGS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0002_seed_email_templates'),
    ]

    operations = [
        migrations.RunPython(seed_billing_email_templates, unseed_billing_email_templates),
    ]
