from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.dynamic_permissions import DynamicModulePermission
from tenants.utils import get_request_tenant
from django.utils import timezone
from django.db.models import Q, Count, Sum, F
from .models import Vehicle, Delivery, DeliveryItem, MaterialRate, RentalEquipment, Rental
from .serializers import (
    VehicleSerializer,
    DeliveryListSerializer,
    DeliveryDetailSerializer,
    DeliveryCreateSerializer,
    DeliveryStatusUpdateSerializer,
    DeliveryItemSerializer,
    MaterialRateSerializer,
    RentalEquipmentSerializer,
    RentalSerializer,
    RentalReturnSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing delivery vehicles
    """
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    serializer_class = VehicleSerializer
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        return Vehicle.objects.filter(tenant=tenant).select_related('tenant')

    def perform_create(self, serializer):
        serializer.save(tenant=get_request_tenant(self.request.user))
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get list of available vehicles"""
        vehicles = self.get_queryset().filter(status='available')
        serializer = self.get_serializer(vehicles, many=True)
        return Response(serializer.data)


class DeliveryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing deliveries
    """
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        queryset = Delivery.objects.filter(
            tenant=tenant
        ).select_related(
            'customer',
            'invoice',
            'vehicle',
            'created_by'
        ).prefetch_related('items__product')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        if from_date:
            queryset = queryset.filter(scheduled_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(scheduled_date__lte=to_date)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(delivery_number__icontains=search) |
                Q(challan_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(driver_name__icontains=search)
            )
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DeliveryCreateSerializer
        elif self.action in ['retrieve', 'update', 'partial_update']:
            return DeliveryDetailSerializer
        return DeliveryListSerializer
    
    def perform_create(self, serializer):
        serializer.save(tenant=get_request_tenant(self.request.user), created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update delivery status with additional data"""
        delivery = self.get_object()
        serializer = DeliveryStatusUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        new_status = data['status']
        
        # Update status
        delivery.status = new_status
        
        # Set timestamps based on status
        if new_status == 'loaded' and not delivery.loading_started_at:
            delivery.loading_started_at = timezone.now()
        elif new_status == 'in_transit' and not delivery.dispatch_time:
            delivery.dispatch_time = timezone.now()
        elif new_status == 'delivered' and not delivery.delivery_completed_at:
            delivery.delivery_completed_at = timezone.now()
        
        # Update optional fields
        if 'driver_notes' in data:
            delivery.driver_notes = data['driver_notes']
        if 'failure_reason' in data:
            delivery.failure_reason = data['failure_reason']
        if 'customer_signature' in data:
            delivery.customer_signature = data['customer_signature']
        if 'delivery_photos' in data:
            delivery.delivery_photos = data['delivery_photos']
        
        # Update vehicle status
        if delivery.vehicle:
            if new_status in ['loaded', 'in_transit']:
                delivery.vehicle.status = 'on_delivery'
                delivery.vehicle.save()
            elif new_status in ['delivered', 'failed', 'cancelled']:
                delivery.vehicle.status = 'available'
                delivery.vehicle.save()
        
        delivery.save()
        
        serializer = DeliveryDetailSerializer(delivery)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        """Quick action to mark delivery as complete"""
        delivery = self.get_object()
        
        if delivery.status == 'delivered':
            return Response(
                {'error': 'Delivery is already marked as delivered'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        delivery.status = 'delivered'
        delivery.delivery_completed_at = timezone.now()
        
        if delivery.vehicle:
            delivery.vehicle.status = 'available'
            delivery.vehicle.save()
        
        delivery.save()
        
        serializer = DeliveryDetailSerializer(delivery)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a delivery"""
        delivery = self.get_object()
        
        if not delivery.can_be_cancelled():
            return Response(
                {'error': 'This delivery cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        delivery.status = 'cancelled'
        
        if delivery.vehicle and delivery.vehicle.status == 'on_delivery':
            delivery.vehicle.status = 'available'
            delivery.vehicle.save()
        
        delivery.save()
        
        serializer = DeliveryDetailSerializer(delivery)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get delivery statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'pending': queryset.filter(status='pending').count(),
            'in_transit': queryset.filter(status__in=['loaded', 'in_transit']).count(),
            'delivered': queryset.filter(status='delivered').count(),
            'failed': queryset.filter(status='failed').count(),
        }
        
        # Today's deliveries
        from datetime import date
        today = date.today()
        stats['today'] = queryset.filter(scheduled_date=today).count()
        stats['today_pending'] = queryset.filter(
            scheduled_date=today,
            status__in=['pending', 'scheduled']
        ).count()
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming deliveries (scheduled for today or future)"""
        from datetime import date
        today = date.today()
        
        deliveries = self.get_queryset().filter(
            scheduled_date__gte=today,
            status__in=['pending', 'scheduled', 'loaded']
        ).order_by('scheduled_date', 'scheduled_time')
        
        serializer = DeliveryListSerializer(deliveries, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def print_challan(self, request, pk=None):
        """Get delivery challan data for printing"""
        delivery = self.get_object()
        serializer = DeliveryDetailSerializer(delivery)
        return Response(serializer.data)


class DeliveryItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing delivery items
    """
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    serializer_class = DeliveryItemSerializer
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        return DeliveryItem.objects.filter(
            tenant=tenant
        ).select_related('delivery', 'product')

    def perform_create(self, serializer):
        serializer.save(tenant=get_request_tenant(self.request.user))


class MaterialRateViewSet(viewsets.ModelViewSet):
    """
    Daily rate board for volatile-price materials (rod, cement, sand, ...).
    Each POST is a new dated entry, not an overwrite, so the board keeps a
    history a shop can look back through and share as "today's rate".
    """
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    permission_module = 'hardware'
    serializer_class = MaterialRateSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        queryset = MaterialRate.objects.filter(
            tenant=tenant
        ).select_related('product', 'product__unit', 'created_by')

        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request.user)
        serializer.save(tenant=tenant, created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Today's rate board — the latest entry for each rated product."""
        # DISTINCT ON isn't portable across SQLite/Postgres, so pick the
        # latest-per-product in Python — the board is a handful of dated
        # materials at most, never large enough for this to matter.
        ordered = self.get_queryset().order_by('product_id', '-effective_date', '-created_at')
        latest_by_product = {}
        for rate in ordered:
            latest_by_product.setdefault(rate.product_id, rate)

        current_rates = sorted(latest_by_product.values(), key=lambda r: r.product.name)
        serializer = self.get_serializer(current_rates, many=True)
        return Response(serializer.data)


class RentalEquipmentViewSet(viewsets.ModelViewSet):
    """Catalogue of rentable tools/machines a hardware shop owns."""
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    permission_module = 'hardware'
    serializer_class = RentalEquipmentSerializer

    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        queryset = RentalEquipment.objects.filter(tenant=tenant)
        if self.request.query_params.get('active_only') == '1':
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=get_request_tenant(self.request.user))

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError

        if instance.rentals.filter(return_date__isnull=True).exists():
            raise ValidationError({'detail': 'Cannot delete equipment that is currently rented out.'})
        if instance.rentals.exists():
            # Rental rows PROTECT their equipment FK to preserve rental
            # history, so a hard delete would fail anyway — steer the user
            # to deactivating instead, which hides it from new rentals
            # without losing the record of what was rented before.
            raise ValidationError({
                'detail': 'This equipment has rental history and can\'t be deleted. '
                          'Deactivate it instead to hide it from new rentals.'
            })
        instance.delete()


class RentalViewSet(viewsets.ModelViewSet):
    """
    Equipment checkouts. Overdue items are surfaced via the `overdue`
    action rather than a stored status, so the list is always accurate
    without any scheduled task keeping it in sync.
    """
    permission_classes = [IsAuthenticated, DynamicModulePermission]
    permission_module = 'hardware'
    serializer_class = RentalSerializer

    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        queryset = Rental.objects.filter(tenant=tenant).select_related('equipment', 'customer')

        status_filter = self.request.query_params.get('status')
        if status_filter == 'active':
            queryset = queryset.filter(status='active')
        elif status_filter:
            queryset = queryset.filter(status=status_filter)

        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=get_request_tenant(self.request.user), created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Rentals still out and past their due date."""
        today = timezone.now().date()
        overdue_rentals = self.get_queryset().filter(status='active', due_date__lt=today)
        serializer = self.get_serializer(overdue_rentals, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        queryset = self.get_queryset()
        today = timezone.now().date()
        return Response({
            'active': queryset.filter(status='active').count(),
            'overdue': queryset.filter(status='active', due_date__lt=today).count(),
            'returned_this_month': queryset.filter(
                status='returned', return_date__year=today.year, return_date__month=today.month
            ).count(),
        })

    @action(detail=True, methods=['post'])
    def mark_returned(self, request, pk=None):
        """Quick action: close out a rental as returned (or damaged/lost)."""
        rental = self.get_object()

        if rental.status != 'active':
            return Response(
                {'error': 'This rental has already been closed out.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RentalReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        rental.return_date = data.get('return_date') or timezone.now().date()
        rental.status = data['status']
        if data.get('notes'):
            rental.notes = (rental.notes + '\n' if rental.notes else '') + data['notes']
        rental.save()

        return Response(RentalSerializer(rental).data)
