# Generated migration to backfill share_token for existing parties

from django.db import migrations
import uuid


def backfill_share_tokens(apps, schema_editor):
    """Generate share_token for all existing PartyLender records that don't have one"""
    PartyLender = apps.get_model('finance', 'PartyLender')
    updated = 0
    for party in PartyLender.objects.filter(share_token__isnull=True):
        party.share_token = uuid.uuid4().hex
        party.save(update_fields=['share_token'])
        updated += 1
    print(f"Backfilled share_token for {updated} parties")


def reverse_backfill(apps, schema_editor):
    """Reverse: set share_token to NULL for records that were backfilled"""
    PartyLender = apps.get_model('finance', 'PartyLender')
    PartyLender.objects.all().update(share_token=None)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_add_share_token_to_party_lender'),
    ]

    operations = [
        migrations.RunPython(backfill_share_tokens, reverse_backfill),
    ]
