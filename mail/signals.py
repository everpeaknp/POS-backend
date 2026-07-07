"""Wire transactional emails to domain events."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from tenants.invitation_models import OrganizationInvitation

logger = logging.getLogger(__name__)


@receiver(post_save, sender=OrganizationInvitation)
def send_invitation_email_on_create(sender, instance, created, **kwargs):
    if not created or instance.status != 'pending':
        return
    try:
        from mail.services import dispatch_invitation_email

        dispatch_invitation_email(instance)
    except Exception:
        logger.exception('Failed to send invitation email for invitation %s', instance.pk)
