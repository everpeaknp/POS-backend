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


class SupportTicketMessage(models.Model):
    """
    One entry in a ticket's timeline: a chat message (from the requester or
    support staff) or a system-generated event (status change, reopen).
    Mirrors the conversation-thread model used by Zendesk/Freshdesk/Intercom
    — a single ordered feed instead of a separate "reply" field per ticket.
    """

    TYPE_MESSAGE = 'message'
    TYPE_STATUS_CHANGE = 'status_change'
    TYPE_SYSTEM = 'system'
    MESSAGE_TYPE_CHOICES = [
        (TYPE_MESSAGE, 'Message'),
        (TYPE_STATUS_CHANGE, 'Status change'),
        (TYPE_SYSTEM, 'System'),
    ]

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_ticket_messages',
    )
    is_staff = models.BooleanField(
        default=False,
        help_text='True if this entry was posted by support staff via /admin.',
    )
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default=TYPE_MESSAGE)
    body = models.TextField(blank=True, default='')
    attachment = models.FileField(upload_to='helpdesk/attachments/', null=True, blank=True)
    old_status = models.CharField(max_length=15, blank=True, default='')
    new_status = models.CharField(max_length=15, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'support_ticket_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
        ]

    def __str__(self):
        if self.message_type == self.TYPE_STATUS_CHANGE:
            return f'#{self.ticket_id} status: {self.old_status} -> {self.new_status}'
        who = 'Staff' if self.is_staff else 'User'
        return f'#{self.ticket_id} {who}: {self.body[:40]}'
