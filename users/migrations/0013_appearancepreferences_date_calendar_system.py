from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_appearancepreferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='appearancepreferences',
            name='date_calendar_system',
            field=models.CharField(
                choices=[('AD', 'Gregorian (AD)'), ('BS', 'Bikram Sambat (BS)')],
                default='AD',
                help_text='Preferred calendar for displaying dates',
                max_length=2,
            ),
        ),
    ]
