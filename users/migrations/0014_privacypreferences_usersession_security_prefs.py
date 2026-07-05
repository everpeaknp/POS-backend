from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_appearancepreferences_date_calendar_system'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreferences',
            name='login_alerts',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='notificationpreferences',
            name='security_log_exports',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='PrivacyPreferences',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('profile_visibility', models.CharField(choices=[('everyone', 'Everyone'), ('organization', 'Organization Only'), ('private', 'Private')], default='organization', max_length=20)),
                ('activity_status', models.BooleanField(default=True)),
                ('search_indexing', models.BooleanField(default=False)),
                ('data_retention_years', models.IntegerField(choices=[(1, '1 Year'), (5, '5 Years'), (0, 'Forever')], default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='privacy_preferences', to='users.user')),
            ],
            options={
                'db_table': 'privacy_preferences',
            },
        ),
        migrations.CreateModel(
            name='UserSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('refresh_jti', models.CharField(db_index=True, max_length=255, unique=True)),
                ('device', models.CharField(max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('location', models.CharField(default='Unknown Location', max_length=255)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_active', models.DateTimeField(auto_now=True)),
                ('is_revoked', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='users.user')),
            ],
            options={
                'db_table': 'user_sessions',
                'ordering': ['-last_active'],
            },
        ),
    ]
