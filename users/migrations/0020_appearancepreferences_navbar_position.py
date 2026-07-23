from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0019_usersession"),
    ]

    operations = [
        migrations.AddField(
            model_name="appearancepreferences",
            name="navbar_position",
            field=models.CharField(
                choices=[("left", "Left"), ("top", "Top")],
                default="left",
                help_text="Main navigation position (left sidebar or top bar)",
                max_length=10,
            ),
        ),
    ]
