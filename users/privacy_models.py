from django.db import models


class PrivacyPreferences(models.Model):
    VISIBILITY_CHOICES = [
        ('everyone', 'Everyone'),
        ('organization', 'Organization Only'),
        ('private', 'Private'),
    ]

    RETENTION_CHOICES = [
        (1, '1 Year'),
        (5, '5 Years'),
        (0, 'Forever'),
    ]

    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='privacy_preferences',
    )
    profile_visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='organization',
    )
    activity_status = models.BooleanField(default=True)
    search_indexing = models.BooleanField(default=False)
    data_retention_years = models.IntegerField(
        choices=RETENTION_CHOICES,
        default=1,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'privacy_preferences'

    def __str__(self):
        return f"Privacy preferences for {self.user.username}"
