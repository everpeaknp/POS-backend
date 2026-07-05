"""
Notification Models for User Alerts
Supports budget alerts, system notifications, and user messages
"""

from django.db import models
from utils.models import TenantModel


class Notification(TenantModel):
    """
    User notifications for alerts, messages, and system events
    Used for budget alerts, task reminders, system messages, etc.
    """
    
    NOTIFICATION_TYPES = [
        ('budget_alert', 'Budget Alert'),
        ('task_reminder', 'Task Reminder'),
        ('system_message', 'System Message'),
        ('user_message', 'User Message'),
        ('approval_request', 'Approval Request'),
        ('status_update', 'Status Update'),
    ]
    
    LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('success', 'Success'),
    ]
    
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default='system_message'
    )
    
    level = models.CharField(
        max_length=20,
        choices=LEVELS,
        default='info'
    )
    
    # Reference to related object (optional)
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        help_text='Model name (e.g., construction_site, sales_order)'
    )
    reference_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='ID of the related object'
    )
    
    # Additional data (JSON)
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional notification data'
    )
    
    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Action URL (optional)
    action_url = models.CharField(
        max_length=500,
        blank=True,
        help_text='URL to navigate when notification is clicked'
    )
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'user', '-created_at']),
            models.Index(fields=['tenant', 'user', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['level']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.get_full_name()}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class NotificationPreferences(models.Model):
    """
    User notification preferences for email and push notifications
    """
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Email preferences
    email_order_updates = models.BooleanField(default=True)
    email_payment_reminders = models.BooleanField(default=True)
    email_inventory_alerts = models.BooleanField(default=True)
    email_team_activity = models.BooleanField(default=True)
    
    # Push notification preferences
    push_desktop = models.BooleanField(default=False)
    push_mobile = models.BooleanField(default=False)
    push_sound = models.BooleanField(default=False)

    # Security notification preferences
    login_alerts = models.BooleanField(default=True)
    security_log_exports = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_preferences'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.username}"
