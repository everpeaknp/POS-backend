from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setting', '0002_esewasettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(default='KHATA', max_length=120)),
                ('tagline', models.CharField(
                    blank=True,
                    help_text='Short subtitle shown in auth pages and marketing surfaces.',
                    max_length=255,
                )),
                ('logo', models.ImageField(
                    blank=True,
                    help_text='Recommended PNG/SVG, ~180×48px.',
                    null=True,
                    upload_to='site/',
                )),
                ('favicon', models.ImageField(
                    blank=True,
                    help_text='Square icon, 32×32 or 64×64 PNG/ICO.',
                    null=True,
                    upload_to='site/',
                )),
                ('seo_title', models.CharField(
                    blank=True,
                    help_text='Default browser tab title (falls back to site name).',
                    max_length=70,
                )),
                ('meta_description', models.CharField(
                    blank=True,
                    help_text='Default meta description for search engines.',
                    max_length=320,
                )),
                ('meta_keywords', models.CharField(
                    blank=True,
                    help_text='Comma-separated SEO keywords.',
                    max_length=255,
                )),
                ('og_image', models.ImageField(
                    blank=True,
                    help_text='Open Graph image for social sharing (1200×630 recommended).',
                    null=True,
                    upload_to='site/',
                )),
                ('allow_search_indexing', models.BooleanField(
                    default=True,
                    help_text='When disabled, adds noindex guidance for public pages.',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Site settings',
                'verbose_name_plural': 'Site settings',
                'db_table': 'setting_site_settings',
            },
        ),
    ]
