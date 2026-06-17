from django.db import models
from django.db.models import Sum, F, Case, When
from django.core.validators import MinValueValidator
from decimal import Decimal
from utils.models import TenantModel


class Site(TenantModel):
    """
    Construction Site/Project - Central organizing unit
    Each site is its own financial and operational universe
    """
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
    ]
    
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=500)
    client_name = models.CharField(max_length=255, blank=True)
    
    # Budget & Financials
    allocated_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Timeline
    start_date = models.DateField()
    estimated_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Management
    manager = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        related_name='managed_sites',
        help_text='Employee assigned as site manager'
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    
    # Site-specific warehouse (each site has its own inventory)
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='construction_sites',
        help_text='Warehouse/storage location for this site'
    )
    
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'construction_sites'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'manager']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.location}"
    
    def get_material_cost(self):
        """Calculate total material cost from consumption logs"""
        from django.db.models import Sum, F
        total = self.material_consumptions.aggregate(
            total=Sum(F('quantity') * F('unit_cost'))
        )['total']
        return total or Decimal('0.00')
    
    def get_labor_cost(self):
        """Calculate total labor cost from attendance"""
        from django.db.models import Sum, F, Case, When
        
        # Calculate based on attendance status
        total = self.attendances.aggregate(
            total=Sum(
                Case(
                    When(status='present', then=F('worker__daily_wage')),
                    When(status='half_day', then=F('worker__daily_wage') / 2),
                    When(status='overtime', then=F('worker__daily_wage') * Decimal('1.5')),
                    default=Decimal('0.00'),
                    output_field=models.DecimalField()
                )
            )
        )['total']
        return total or Decimal('0.00')
    
    def get_other_expenses(self):
        """Calculate other expenses from daily logs"""
        total = self.daily_logs.aggregate(
            total=Sum('other_expenses')
        )['total']
        return total or Decimal('0.00')
    
    def get_actual_spend(self):
        """Calculate total actual spend"""
        return self.get_material_cost() + self.get_labor_cost() + self.get_other_expenses()
    
    def get_remaining_budget(self):
        """Calculate remaining budget"""
        return self.allocated_budget - self.get_actual_spend()
    
    def get_budget_percentage(self):
        """Calculate budget utilization percentage"""
        if self.allocated_budget > 0:
            return (self.get_actual_spend() / self.allocated_budget) * 100
        return Decimal('0.00')


class Worker(TenantModel):
    """
    Construction Worker - Mason, Laborer, Engineer, Supervisor
    """
    CATEGORY_CHOICES = [
        ('mason', 'Mason'),
        ('laborer', 'Laborer'),
        ('carpenter', 'Carpenter'),
        ('electrician', 'Electrician'),
        ('plumber', 'Plumber'),
        ('engineer', 'Engineer'),
        ('supervisor', 'Supervisor'),
        ('helper', 'Helper'),
        ('painter', 'Painter'),
        ('welder', 'Welder'),
        ('driver', 'Driver'),
        ('operator', 'Equipment Operator'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    daily_wage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Daily wage rate in NPR'
    )
    
    # Assignment
    assigned_site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workers'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Additional info
    id_number = models.CharField(max_length=50, blank=True, help_text='Citizenship/ID number')
    emergency_contact = models.CharField(max_length=20, blank=True)
    
    class Meta:
        db_table = 'construction_workers'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'assigned_site']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.category})"


class Attendance(TenantModel):
    """
    Daily Worker Attendance - Drives payroll calculation
    """
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('half_day', 'Half Day'),
        ('overtime', 'Overtime'),
    ]
    
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='construction_attendance_set'
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # Time tracking
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    
    # Calculated wage for this day
    wage_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Calculated wage for this attendance'
    )
    
    notes = models.TextField(blank=True)
    
    # Audit
    marked_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='marked_attendances'
    )
    
    class Meta:
        db_table = 'construction_attendance'
        ordering = ['-date', 'worker__name']
        unique_together = [['tenant', 'worker', 'site', 'date']]
        indexes = [
            models.Index(fields=['tenant', 'site', 'date']),
            models.Index(fields=['tenant', 'worker', 'date']),
        ]
    
    def __str__(self):
        return f"{self.worker.name} - {self.site.name} - {self.date} ({self.status})"
    
    def save(self, *args, **kwargs):
        """Auto-calculate wage amount based on status"""
        if self.status == 'present':
            self.wage_amount = self.worker.daily_wage
        elif self.status == 'half_day':
            self.wage_amount = self.worker.daily_wage / 2
        elif self.status == 'overtime':
            self.wage_amount = self.worker.daily_wage * Decimal('1.5')
        else:  # absent
            self.wage_amount = Decimal('0.00')
        
        super().save(*args, **kwargs)


class DailyLog(TenantModel):
    """
    Daily Site Log - Supervisor's daily report
    Immutable after 24 hours
    """
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='daily_logs'
    )
    date = models.DateField()
    
    # Work description
    work_description = models.TextField(help_text='Description of work done today')
    progress_notes = models.TextField(blank=True)
    
    # Progress photos (stored as JSON array of URLs)
    progress_photos = models.JSONField(default=list, blank=True)
    
    # Weather conditions
    weather = models.CharField(max_length=100, blank=True)
    
    # Other expenses (equipment rental, fuel, etc.)
    other_expenses = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    other_expenses_description = models.TextField(blank=True)
    
    # Audit
    submitted_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_logs'
    )
    
    # Manager review
    reviewed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_logs'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    manager_comments = models.TextField(blank=True)
    
    class Meta:
        db_table = 'construction_daily_logs'
        ordering = ['-date']
        unique_together = [['tenant', 'site', 'date']]
        indexes = [
            models.Index(fields=['tenant', 'site', 'date']),
        ]
    
    def __str__(self):
        return f"{self.site.name} - {self.date}"
    
    def is_editable(self):
        """
        Check if log can be edited (within 24 hours of creation)
        SRS 4.6: Logs are immutable after 24 hours
        """
        from django.utils import timezone
        from datetime import timedelta
        
        time_since_creation = timezone.now() - self.created_at
        return time_since_creation < timedelta(hours=24)
    
    def get_hours_until_immutable(self):
        """Get hours remaining until log becomes immutable"""
        from django.utils import timezone
        from datetime import timedelta
        
        time_since_creation = timezone.now() - self.created_at
        hours_passed = time_since_creation.total_seconds() / 3600
        hours_remaining = 24 - hours_passed
        
        return max(0, hours_remaining)


class MaterialConsumption(TenantModel):
    """
    Material Consumption Log - Links to DailyLog and Inventory
    CRITICAL: Automatically decreases inventory.Stock when saved
    """
    daily_log = models.ForeignKey(
        DailyLog,
        on_delete=models.CASCADE,
        related_name='material_consumptions',
        null=True,
        blank=True,
        help_text='Optional: Link to daily log if consumed as part of daily reporting'
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='material_consumptions'
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='construction_consumptions'
    )
    
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Cost per unit at time of consumption'
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='quantity * unit_cost'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'construction_material_consumption'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'site']),
            models.Index(fields=['tenant', 'daily_log']),
            models.Index(fields=['tenant', 'product']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} @ {self.site.name}"
    
    def save(self, *args, **kwargs):
        """
        Auto-calculate total cost and update inventory stock
        """
        # Calculate total cost
        self.total_cost = self.quantity * self.unit_cost
        
        # Check if this is a new record (not an update)
        is_new = self.pk is None
        
        super().save(*args, **kwargs)
        
        # Update inventory stock (only for new records)
        if is_new:
            self._update_inventory_stock()
    
    def _update_inventory_stock(self):
        """
        Complete Material Usage Flow (SRS 6.1):
        1. Decrease inventory stock for the site's warehouse
        2. Create stock movement record for audit trail
        3. Calculate cost and update site budget
        4. Create accounting journal entry (Dr: Construction Expense, Cr: Inventory Asset)
        5. Check budget threshold and send manager alert if needed
        """
        from inventory.models import Stock, StockMovement
        from accounting.services import record_material_consumption
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            # STEP 1: Update Inventory - Deduct from site warehouse
            stock, created = Stock.objects.get_or_create(
                tenant=self.tenant,
                product=self.product,
                warehouse=self.site.warehouse,
                defaults={'quantity': Decimal('0.00')}
            )
            
            # Decrease stock quantity
            stock.quantity -= self.quantity
            stock.save()
            
            # STEP 2: Create Stock Movement (Audit Trail)
            performed_by = None
            if self.daily_log and self.daily_log.submitted_by:
                performed_by = self.daily_log.submitted_by
            
            notes = f'Material consumption at {self.site.name}'
            if self.daily_log:
                notes += f' - Daily log: {self.daily_log.date}'
            if self.notes:
                notes += f' - {self.notes}'
            
            StockMovement.objects.create(
                tenant=self.tenant,
                product=self.product,
                warehouse=self.site.warehouse,
                movement_type='out',
                quantity=self.quantity,
                reference_type='construction_consumption',
                reference_id=self.id,
                reason=f'Material consumption at {self.site.name}',
                notes=notes,
                performed_by=performed_by
            )
            
            # STEP 3: Cost Calculation (already done in save() - self.total_cost)
            # The cost is calculated as: quantity * unit_cost
            # This updates the site's actual spend automatically via get_material_cost()
            
            # STEP 4: Create Accounting Journal Entry
            # Dr: Construction Expense (increases expense)
            # Cr: Inventory Asset (decreases asset)
            try:
                record_material_consumption(
                    site=self.site,
                    product=self.product,
                    quantity=self.quantity,
                    unit_cost=self.unit_cost,
                    reference=f'MC-{self.id}',
                    tenant=self.tenant
                )
            except Exception as e:
                # Log error but don't fail the transaction
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to create journal entry for material consumption {self.id}: {e}")
            
            # STEP 5: Budget Update & Manager Alert
            # Check if budget threshold exceeded (80%+)
            self._check_budget_alert()
    
    def _check_budget_alert(self):
        """
        Check if site budget has exceeded 80% threshold and send alert to manager.
        This implements the "Manager alert" step from SRS 6.1 Material Usage Flow.
        """
        # Get current budget percentage
        budget_percentage = self.site.get_budget_percentage()
        
        # Check if budget is 80% or more
        if budget_percentage >= 80:
            self._send_budget_alert(budget_percentage)
    
    def _send_budget_alert(self, budget_percentage):
        """
        Send budget alert notification to site manager.
        Creates a notification record that will be displayed in the dashboard.
        """
        from users.models import Notification
        
        # Get site manager
        manager = self.site.manager
        if not manager or not manager.user:
            return  # No manager assigned or no user linked, skip alert
        
        # Determine alert level
        if budget_percentage >= 100:
            alert_level = 'critical'
            message = f"🚨 CRITICAL: Site '{self.site.name}' has EXCEEDED budget ({budget_percentage:.1f}%)"
        elif budget_percentage >= 90:
            alert_level = 'warning'
            message = f"⚠️ WARNING: Site '{self.site.name}' budget at {budget_percentage:.1f}%"
        else:
            alert_level = 'info'
            message = f"ℹ️ NOTICE: Site '{self.site.name}' budget at {budget_percentage:.1f}%"
        
        # Create notification
        try:
            Notification.objects.create(
                tenant=self.tenant,
                user=manager.user,  # Send to the manager's user account
                title=f"Budget Alert: {self.site.name}",
                message=message,
                notification_type='budget_alert',
                level=alert_level,
                reference_type='construction_site',
                reference_id=self.site.id,
                data={
                    'site_id': self.site.id,
                    'site_name': self.site.name,
                    'budget_percentage': float(budget_percentage),
                    'allocated_budget': float(self.site.allocated_budget),
                    'actual_spend': float(self.site.get_actual_spend()),
                    'material_consumption_id': self.id,
                    'product_name': self.product.name,
                    'quantity': float(self.quantity),
                    'cost': float(self.total_cost)
                }
            )
        except Exception as e:
            # Log error but don't fail the transaction
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create budget alert notification: {e}")


class Equipment(TenantModel):
    """
    Construction Equipment - Owned or Rented
    """
    TYPE_CHOICES = [
        ('owned', 'Owned'),
        ('rented', 'Rented'),
    ]
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
    ]
    
    name = models.CharField(max_length=255)
    equipment_type = models.CharField(max_length=100, help_text='e.g., Excavator, Mixer, Crane')
    ownership_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    # Cost
    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Purchase cost if owned'
    )
    rental_cost_per_day = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Daily rental cost if rented'
    )
    
    # Assignment
    assigned_site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Details
    registration_number = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'construction_equipment'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'assigned_site']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.equipment_type})"


class EquipmentUsageLog(TenantModel):
    """
    Equipment Usage Log - Track hours used per day
    """
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='equipment_usage_logs'
    )
    daily_log = models.ForeignKey(
        DailyLog,
        on_delete=models.CASCADE,
        related_name='equipment_usage_logs',
        null=True,
        blank=True
    )
    
    date = models.DateField()
    hours_used = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    # Cost calculation
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Calculated cost for this usage'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'construction_equipment_usage'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['tenant', 'site', 'date']),
            models.Index(fields=['tenant', 'equipment', 'date']),
        ]
    
    def __str__(self):
        return f"{self.equipment.name} - {self.site.name} - {self.date}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate cost based on equipment type"""
        if self.equipment.ownership_type == 'rented' and self.equipment.rental_cost_per_day:
            # For rented equipment, calculate based on hours (assuming 8-hour day)
            self.cost = (self.equipment.rental_cost_per_day / 8) * self.hours_used
        else:
            # For owned equipment, cost is 0 (depreciation handled separately)
            self.cost = Decimal('0.00')
        
        super().save(*args, **kwargs)
