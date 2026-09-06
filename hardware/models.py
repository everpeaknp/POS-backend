from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from utils.models import TenantModel


class Vehicle(TenantModel):
    """
    Delivery vehicles for hardware shop
    Track trucks, pickups, tempos used for deliveries
    """
    VEHICLE_TYPE_CHOICES = [
        ('truck', 'Truck'),
        ('pickup', 'Pickup'),
        ('tempo', 'Tempo'),
        ('van', 'Van'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('on_delivery', 'On Delivery'),
        ('maintenance', 'Under Maintenance'),
        ('inactive', 'Inactive'),
    ]
    
    vehicle_number = models.CharField(
        max_length=20,
        help_text='Vehicle registration number (e.g., BA 1 KHA 1234)'
    )
    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPE_CHOICES,
        default='truck'
    )
    capacity_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Load capacity in kilograms'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available'
    )
    
    # Maintenance tracking
    last_service_date = models.DateField(null=True, blank=True)
    next_service_due = models.DateField(null=True, blank=True)
    
    # Ownership
    is_owned = models.BooleanField(
        default=True,
        help_text='True if owned by company, False if rented/hired'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hardware_vehicles'
        ordering = ['vehicle_number']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'vehicle_number']),
        ]
        unique_together = [['tenant', 'vehicle_number']]
    
    def __str__(self):
        return f"{self.vehicle_number} ({self.vehicle_type})"


class Delivery(TenantModel):
    """
    Delivery tracking for hardware materials
    Links to invoice and tracks delivery status from loading to completion
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('loaded', 'Loaded on Vehicle'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('partial', 'Partially Delivered'),
        ('failed', 'Failed Delivery'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Link to invoice
    invoice = models.ForeignKey(
        'sales.Invoice',
        on_delete=models.PROTECT,
        related_name='deliveries',
        help_text='Invoice for which materials are being delivered'
    )
    
    # Delivery identification
    delivery_number = models.CharField(
        max_length=50,
        unique=True,
        help_text='Unique delivery tracking number'
    )
    challan_number = models.CharField(
        max_length=50,
        blank=True,
        help_text='Delivery challan number'
    )
    
    # Customer & Location
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.PROTECT,
        related_name='hardware_deliveries'
    )
    delivery_address = models.TextField(
        help_text='Full delivery address including landmarks'
    )
    customer_contact_name = models.CharField(
        max_length=255,
        blank=True,
        help_text='Contact person at delivery site'
    )
    customer_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text='Phone number at delivery site'
    )
    
    # Schedule
    scheduled_date = models.DateField(
        help_text='Date when delivery is scheduled'
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        help_text='Approximate delivery time'
    )
    
    # Actual delivery tracking
    loading_started_at = models.DateTimeField(null=True, blank=True)
    dispatch_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Time when vehicle left for delivery'
    )
    delivery_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Time when delivery was completed'
    )
    
    # Vehicle & Driver
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries'
    )
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Charges
    transport_charge = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Transport/freight charge for this delivery'
    )
    loading_charge = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Loading/unloading labour charge'
    )
    
    # Documentation
    delivery_notes = models.TextField(
        blank=True,
        help_text='Special instructions or notes for delivery'
    )
    driver_notes = models.TextField(
        blank=True,
        help_text='Notes added by driver during delivery'
    )
    
    # Proof of delivery
    customer_signature = models.ImageField(
        upload_to='hardware/delivery_signatures/%Y/%m/',
        null=True,
        blank=True,
        help_text='Customer signature on delivery challan'
    )
    delivery_photos = models.JSONField(
        default=list,
        blank=True,
        help_text='Photos of delivered materials (list of URLs)'
    )
    
    # Failure tracking
    failure_reason = models.TextField(
        blank=True,
        help_text='Reason if delivery failed'
    )
    
    # Created by
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_deliveries'
    )
    
    class Meta:
        db_table = 'hardware_deliveries'
        ordering = ['-scheduled_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'customer']),
            models.Index(fields=['tenant', 'invoice']),
            models.Index(fields=['tenant', 'scheduled_date']),
            models.Index(fields=['delivery_number']),
        ]
    
    def __str__(self):
        return f"Delivery {self.delivery_number} - {self.customer.name}"
    
    def get_total_charges(self):
        """Calculate total delivery charges"""
        return self.transport_charge + self.loading_charge
    
    def can_be_edited(self):
        """Check if delivery can still be edited"""
        return self.status in ['pending', 'scheduled']
    
    def can_be_cancelled(self):
        """Check if delivery can be cancelled"""
        return self.status not in ['delivered', 'cancelled']


class DeliveryItem(TenantModel):
    """
    Individual items in a delivery
    Tracks quantity ordered vs delivered (for partial deliveries)
    """
    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='delivery_items'
    )
    
    # Quantities
    ordered_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Quantity as per invoice'
    )
    delivered_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Actual quantity delivered'
    )
    damaged_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Quantity damaged during transit'
    )
    
    # Unit details from invoice
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Unit price from invoice'
    )
    
    notes = models.TextField(
        blank=True,
        help_text='Notes about this item in delivery'
    )
    
    class Meta:
        db_table = 'hardware_delivery_items'
        ordering = ['delivery', 'product__name']
        indexes = [
            models.Index(fields=['tenant', 'delivery']),
            models.Index(fields=['tenant', 'product']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.delivered_quantity}/{self.ordered_quantity}"
    
    def is_fully_delivered(self):
        """Check if item is fully delivered"""
        return self.delivered_quantity >= self.ordered_quantity
    
    def get_pending_quantity(self):
        """Get quantity still pending delivery"""
        return max(Decimal('0.00'), self.ordered_quantity - self.delivered_quantity)
    
    def get_line_total(self):
        """Calculate line total for delivered quantity"""
        return self.delivered_quantity * self.unit_price


class MaterialRate(TenantModel):
    """
    Daily rate entry for a volatile-price material (rod, cement, sand, etc.).
    Nepali hardware shops re-quote these day to day — sometimes multiple
    times a day — and share "today's rate" with contractors, so each save
    is kept as a dated history entry rather than overwriting a single field.
    """
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='rate_history',
    )
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Rate for this product as of effective_date'
    )
    unit_label = models.CharField(
        max_length=50,
        blank=True,
        help_text='Display unit for the rate, e.g. "per kg", "per bori" (defaults to the product unit)'
    )
    effective_date = models.DateField(
        help_text='Date this rate applies from'
    )
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_rates_posted',
    )

    class Meta:
        db_table = 'hardware_material_rates'
        ordering = ['-effective_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'product', '-effective_date']),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.rate} ({self.effective_date})"


class RentalEquipment(TenantModel):
    """
    Catalogue entry for a rentable tool/machine (drill, cement mixer,
    scaffolding, etc.) — hardware shops rent these out to contractors
    day-to-day alongside selling materials.
    """
    CATEGORY_CHOICES = [
        ('power_tool', 'Power Tool'),
        ('machinery', 'Machinery'),
        ('scaffolding', 'Scaffolding'),
        ('measuring', 'Measuring Equipment'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=255, help_text='e.g. "Cement Mixer", "Drill Machine"')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    total_units = models.PositiveIntegerField(
        default=1,
        help_text='How many of this item the shop owns'
    )
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Default rent charged per day per unit'
    )
    deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Default refundable security deposit per unit'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Turn off to hide from "new rental" without deleting rental history'
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'hardware_rental_equipment'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'category']),
        ]

    def __str__(self):
        return self.name

    def units_out(self):
        """Units currently checked out (not yet returned)."""
        return self.rentals.filter(return_date__isnull=True).aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

    def units_available(self):
        return max(0, self.total_units - self.units_out())


class Rental(TenantModel):
    """
    A single check-out of one or more units of a RentalEquipment to a
    customer. Overdue is derived from due_date rather than stored, so
    nothing needs a background job to flip status — it's always correct
    at read time.
    """
    STATUS_CHOICES = [
        ('active', 'Rented Out'),
        ('returned', 'Returned'),
        ('damaged', 'Returned Damaged'),
        ('lost', 'Lost / Not Returned'),
    ]

    equipment = models.ForeignKey(
        RentalEquipment,
        on_delete=models.PROTECT,
        related_name='rentals'
    )
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.PROTECT,
        related_name='hardware_rentals'
    )
    quantity = models.PositiveIntegerField(default=1)
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Rate at the time of rental (may differ from current equipment default)'
    )
    deposit_collected = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    checkout_date = models.DateField(default=timezone.now)
    due_date = models.DateField(help_text='Expected return date')
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hardware_rentals_created'
    )

    class Meta:
        db_table = 'hardware_rentals'
        ordering = ['-checkout_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'due_date']),
            models.Index(fields=['tenant', 'customer']),
        ]

    def __str__(self):
        return f"{self.equipment.name} x{self.quantity} -> {self.customer.name}"

    def is_overdue(self):
        return self.status == 'active' and self.due_date < timezone.now().date()

    def days_rented(self):
        """Whole days the item has been (or was) out, minimum 1."""
        end = self.return_date or timezone.now().date()
        return max(1, (end - self.checkout_date).days + 1)

    def get_total_charge(self):
        return self.daily_rate * self.quantity * self.days_rented()
