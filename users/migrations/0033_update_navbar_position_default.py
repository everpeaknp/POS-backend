# Generated migration to update navbar_position default to 'top' and migrate existing data

from django.db import migrations, models


def migrate_navbar_position(apps, schema_editor):
    """Migrate existing navbar_position values from 'left' to 'top'"""
    AppearancePreferences = apps.get_model('users', 'AppearancePreferences')
    # Update all existing preferences that have 'left' to 'top'
    AppearancePreferences.objects.filter(navbar_position='left').update(navbar_position='top')


def reverse_navbar_position(apps, schema_editor):
    """Reverse: migrate from 'top' back to 'left'"""
    AppearancePreferences = apps.get_model('users', 'AppearancePreferences')
    # Revert: update all 'top' back to 'left'
    AppearancePreferences.objects.filter(navbar_position='top').update(navbar_position='left')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0020_appearancepreferences_navbar_position'),
    ]

    operations = [
        # Update model field default
        migrations.AlterField(
            model_name='appearancepreferences',
            name='navbar_position',
            field=models.CharField(
                choices=[('left', 'Left'), ('top', 'Top')],
                default='top',
                help_text='App bar position (left or top)',
                max_length=10,
            ),
        ),
        # Migrate existing data
        migrations.RunPython(
            code=migrate_navbar_position,
            reverse_code=reverse_navbar_position,
        ),
    ]
