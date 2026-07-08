from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_invited_email(apps, schema_editor):
    OrganizationInvitation = apps.get_model('tenants', 'OrganizationInvitation')
    for invitation in OrganizationInvitation.objects.select_related('invited_user').iterator():
        if invitation.invited_user_id and invitation.invited_user and invitation.invited_user.email:
            OrganizationInvitation.objects.filter(pk=invitation.pk).update(
                invited_email=invitation.invited_user.email.lower()
            )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0012_organizationinvitation_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationinvitation',
            name='invited_email',
            field=models.EmailField(
                blank=True,
                db_index=True,
                default='',
                help_text='Email address invited (supports users who have not signed up yet)',
                max_length=254,
            ),
        ),
        migrations.AlterField(
            model_name='organizationinvitation',
            name='invited_user',
            field=models.ForeignKey(
                blank=True,
                help_text='User being invited (null until they register)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='received_invitations',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='organizationinvitation',
            index=models.Index(fields=['invited_email', 'status'], name='organizatio_invited_8f2a1c_idx'),
        ),
        migrations.RunPython(backfill_invited_email, migrations.RunPython.noop),
    ]
