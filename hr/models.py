from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from utils.models import TenantModel
from users.models import User


class Department(TenantModel):
    """Department model for HR management"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    head = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments'
    )
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        unique_together = [['tenant', 'name']]
    
    def __str__(self):
        return self.name
    
    @property
    def employee_count(self):
        return self.employees.filter(status='active').count()


class Employee(TenantModel):
    """Employee model for HR management"""
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Probation', 'Probation'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('terminated', 'Terminated'),
    ]
    
    # Personal Information
    name = models.CharField(max_length=255)
    dob = models.DateField(verbose_name='Date of Birth')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    
    # Employment Information
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='employees'
    )
    designation = models.CharField(max_length=255)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)
    join_date = models.DateField()
    
    # Salary Information
    basic_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Link to User account (optional)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profile'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
    
    def __str__(self):
        return f"{self.name} - {self.designation}"
    
    @property
    def pf_employee(self):
        """Calculate employee PF contribution (10%)"""
        return self.basic_salary * Decimal('0.10')
    
    @property
    def pf_employer(self):
        """Calculate employer PF contribution (10%)"""
        return self.basic_salary * Decimal('0.10')
    
    @property
    def total_pf(self):
        """Total PF contribution"""
        return self.pf_employee + self.pf_employer
    
    @property
    def gross_salary(self):
        """Gross salary including employer PF"""
        return self.basic_salary + self.pf_employer


class Attendance(TenantModel):
    """Attendance model for tracking employee attendance"""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half-day', 'Half Day'),
        ('leave', 'Leave'),
    ]
    
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='hr_attendance_set'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date', 'employee__name']
        verbose_name = 'Attendance'
        verbose_name_plural = 'Attendance Records'
        unique_together = [['tenant', 'employee', 'date']]
    
    def __str__(self):
        return f"{self.employee.name} - {self.date} - {self.status}"
    
    @property
    def hours_worked(self):
        """Calculate hours worked"""
        if self.check_in and self.check_out:
            from datetime import datetime, timedelta
            check_in_dt = datetime.combine(self.date, self.check_in)
            check_out_dt = datetime.combine(self.date, self.check_out)
            delta = check_out_dt - check_in_dt
            return delta.total_seconds() / 3600
        return None


class LeaveType(TenantModel):
    """Leave Type model for defining different types of leaves"""
    name = models.CharField(max_length=255)
    days_allowed = models.IntegerField(default=0, help_text='Number of days allowed per year')
    description = models.TextField(blank=True, null=True)
    is_paid = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Leave Type'
        verbose_name_plural = 'Leave Types'
        unique_together = [['tenant', 'name']]
    
    def __str__(self):
        return self.name


class LeaveRequest(TenantModel):
    """Leave Request model for employee leave applications"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='hr_leave_requests'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='leave_requests'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name='leave_requests'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approval tracking
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leave_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Leave Request'
        verbose_name_plural = 'Leave Requests'
    
    def __str__(self):
        return f"{self.employee.name} - {self.leave_type.name} ({self.start_date} to {self.end_date})"
    
    @property
    def days_requested(self):
        """Calculate number of days requested"""
        delta = self.end_date - self.start_date
        return delta.days + 1


class Payroll(TenantModel):
    """Payroll model for employee salary processing"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('paid', 'Paid'),
    ]
    
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='hr_payrolls'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='payrolls'
    )
    month = models.CharField(max_length=50)
    year = models.IntegerField()
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    processed_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-year', '-created_at']
        verbose_name = 'Payroll'
        verbose_name_plural = 'Payrolls'
        unique_together = [['tenant', 'employee', 'month', 'year']]
    
    def __str__(self):
        return f"{self.employee.name} - {self.month} {self.year}"
