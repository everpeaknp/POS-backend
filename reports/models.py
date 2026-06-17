from django.db import models
from utils.models import TenantModel


class CustomReport(TenantModel):
    """
    Custom report builder model
    Allows users to create, save, and run custom reports
    """
    REPORT_TYPE_CHOICES = [
        ('table', 'Table'),
        ('chart', 'Chart'),
        ('both', 'Both'),
    ]
    
    SCHEDULE_CHOICES = [
        ('none', 'None'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    MODULE_CHOICES = [
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('inventory', 'Inventory'),
        ('accounting', 'Accounting'),
        ('hr', 'HR'),
        ('pos', 'POS'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES, default='table')
    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    
    # Report configuration stored as JSON
    fields = models.JSONField(default=list, help_text="Selected fields for the report")
    filters = models.JSONField(default=list, help_text="Filter conditions")
    grouping = models.JSONField(default=dict, help_text="Grouping configuration")
    sorting = models.JSONField(default=dict, help_text="Sorting configuration")
    chart_config = models.JSONField(default=dict, help_text="Chart configuration")
    
    # Scheduling
    schedule = models.CharField(max_length=20, choices=SCHEDULE_CHOICES, default='none')
    last_run = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='custom_reports')
    is_shared = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'custom_reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'module']),
            models.Index(fields=['tenant', 'created_by']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.module})"
