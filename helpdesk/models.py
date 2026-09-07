from django.conf import settings
from django.db import models

from utils.models import TenantModel


class SupportTicket(TenantModel):
    """A support request raised by a user within a tenant workspace."""

    CATEGORY_CHOICES = [
        ('bug', 'Bug report'),
        ('billing', 'Billing'),
        ('feature_request', 'Feature request'),
        ('account', 'Account & access'),
        ('other', 'Other'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='support_tickets',
    )
    subject = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    message = models.TextField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'support_tickets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'#{self.id} {self.subject}'
