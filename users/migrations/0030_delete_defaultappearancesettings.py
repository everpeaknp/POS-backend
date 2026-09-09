# Moves DefaultAppearanceSettings out of the 'users' app into 'setting'.
# State-only: the underlying 'default_appearance_settings' table and its
# data are left untouched — see setting/migrations for the matching
# state-only CreateModel that picks the table back up.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0029_defaultappearancesettings'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='DefaultAppearanceSettings'),
            ],
            database_operations=[],
        ),
    ]
