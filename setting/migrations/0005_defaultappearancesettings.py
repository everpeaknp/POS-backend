# Moves DefaultAppearanceSettings into the 'setting' app so it appears
# under /admin/setting/ instead of /admin/users/. State-only: the
# 'default_appearance_settings' table already exists (created by
# users.0029) and is reused as-is — no data is touched.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('setting', '0004_sitesettings_cloudinary_api_key_and_more'),
        ('users', '0030_delete_defaultappearancesettings'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='DefaultAppearanceSettings',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('theme', models.CharField(choices=[('light', 'Light'), ('dark', 'Dark'), ('system', 'System')], default='light', help_text='Default interface theme for new users', max_length=10)),
                        ('navbar_position', models.CharField(choices=[('left', 'Left'), ('top', 'Top')], default='top', help_text='Default app bar position for new users (left or top)', max_length=10)),
                        ('accent_color', models.CharField(blank=True, default='#8B5CF6', help_text='Default accent color for new users (hex code, e.g., #3B82F6)', max_length=7, null=True)),
                        ('sidebar_color', models.CharField(blank=True, default='#0F172A', help_text='Default sidebar background color for new users (hex code)', max_length=7, null=True)),
                        ('navbar_color', models.CharField(blank=True, help_text='Default navbar/icon-rail background color for new users (hex code)', max_length=7, null=True)),
                        ('border_radius', models.CharField(blank=True, default='1rem', help_text='Default global border radius for new users (CSS length, e.g. 0.625rem)', max_length=20, null=True)),
                        ('compact_mode', models.BooleanField(default=False, help_text='Default compact display mode for new users')),
                        ('smooth_animations', models.BooleanField(default=True, help_text='Default smooth animations setting for new users')),
                        ('high_contrast', models.BooleanField(default=False, help_text='Default high contrast mode for new users')),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name': 'Default Appearance Settings',
                        'verbose_name_plural': 'Default Appearance Settings',
                        'db_table': 'default_appearance_settings',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
