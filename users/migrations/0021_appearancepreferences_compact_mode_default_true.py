from django.db import migrations, models


def enable_compact_mode_default(apps, schema_editor):
    AppearancePreferences = apps.get_model("users", "AppearancePreferences")
    AppearancePreferences.objects.filter(compact_mode=False).update(compact_mode=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0020_appearancepreferences_navbar_position"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appearancepreferences",
            name="compact_mode",
            field=models.BooleanField(
                default=True,
                help_text="Enable compact display mode",
            ),
        ),
        migrations.RunPython(enable_compact_mode_default, noop_reverse),
    ]
