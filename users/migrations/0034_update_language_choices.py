# Generated migration to update language choices and default

from django.db import migrations, models


def migrate_language(apps, schema_editor):
    """Migrate existing language values to new choices"""
    AppearancePreferences = apps.get_model('users', 'AppearancePreferences')
    # Convert old language values to new ones
    # en-US, en-GB -> en
    # Others -> en (default fallback)
    AppearancePreferences.objects.filter(language__startswith='en').update(language='en')
    AppearancePreferences.objects.filter(language__in=['es', 'fr', 'de', 'hi']).update(language='en')


def reverse_language(apps, schema_editor):
    """Reverse: revert language changes"""
    AppearancePreferences = apps.get_model('users', 'AppearancePreferences')
    # Just set everything back to en-US as a safe default
    AppearancePreferences.objects.all().update(language='en-US')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0033_update_navbar_position_default'),
    ]

    operations = [
        # Update model field choices and default
        migrations.AlterField(
            model_name='appearancepreferences',
            name='language',
            field=models.CharField(
                choices=[('en', 'English'), ('ne', 'नेपाली')],
                default='en',
                help_text='Preferred language',
                max_length=10,
            ),
        ),
        # Migrate existing data
        migrations.RunPython(
            code=migrate_language,
            reverse_code=reverse_language,
        ),
    ]
