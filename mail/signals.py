"""Wire transactional emails to domain events."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='tenants.OrganizationInvitation')
def send_invitation_email_on_create(sender, instance, created, **kwargs):
    if not created or instance.status != 'pending':
        return
    from mail.services import dispatch_invitation_email
    dispatch_invitation_email(instance)
