"""
Appearance preferences models for user interface customization
"""
from django.db import models
from django.conf import settings


class AppearancePreferences(models.Model):
    """
    User appearance and interface preferences
    """
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    ]
    
    LANGUAGE_CHOICES = [
        ('en-US', 'English (US)'),
        ('en-GB', 'English (UK)'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('hi', 'Hindi'),
    ]
    
    TIMEZONE_CHOICES = [
        ('UTC', 'UTC (GMT+0:00)'),
        ('America/New_York', 'Eastern Time (GMT-5:00)'),
        ('America/Chicago', 'Central Time (GMT-6:00)'),
        ('America/Denver', 'Mountain Time (GMT-7:00)'),
        ('America/Los_Angeles', 'Pacific Time (GMT-8:00)'),
        ('Europe/London', 'London (GMT+0:00)'),
        ('Europe/Paris', 'Paris (GMT+1:00)'),
        ('Asia/Dubai', 'Dubai (GMT+4:00)'),
        ('Asia/Kolkata', 'IST (GMT+5:30)'),
        ('Asia/Singapore', 'Singapore (GMT+8:00)'),
        ('Asia/Tokyo', 'Tokyo (GMT+9:00)'),
        ('Australia/Sydney', 'Sydney (GMT+10:00)'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='appearance_preferences'
    )
    
    # Theme settings
    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='light',
        help_text='Interface theme preference'
    )
    
    # Localization settings
    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en-US',
        help_text='Preferred language'
    )
    
    timezone = models.CharField(
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='UTC',
        help_text='Preferred timezone'
    )
    
    # Display settings
    compact_mode = models.BooleanField(
        default=False,
        help_text='Enable compact display mode'
    )
    
    smooth_animations = models.BooleanField(
        default=True,
        help_text='Enable smooth animations'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_appearance_preferences'
        verbose_name = 'Appearance Preference'
        verbose_name_plural = 'Appearance Preferences'
    
    def __str__(self):
        return f"Appearance preferences for {self.user.username}"
