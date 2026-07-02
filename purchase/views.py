from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.utils import timezone
from .models import (
    Supplier, PurchaseRequest, PurchaseOrder,
    PurchaseInvoice, DebitNote
)
from .serializers import (
    SupplierSerializer, PurchaseRequestSerializer, PurchaseRequestCreateSerializer,
    PurchaseOrderSerializer, PurchaseOrderCreateSerializer,
    PurchaseInvoiceSerializer, DebitNoteSerializer
)


@extend_schema_view(
    list=extend_schema(
        description="List all suppliers for the current tenant",
        tags=["Purchase - Suppliers"]
    ),
    retrieve=extend_schema(
        description="Get supplier details",
        tags=["Purchase - Suppliers"]
    ),
    create=extend_schema(
        description="Create a new supplier",
        tags=["Purchase - Suppliers"]
    ),
    update=extend_schema(
        description="Update supplier details",
        tags=["Purchase - Suppliers"]
    ),
    partial_update=extend_schema(
        description="Partially update supplier",
        tags=["Purchase - Suppliers"]
    ),
    destroy=extend_schema(
        description="Delete a supplier",
        tags=["Purchase - Suppliers"]
    ),
)
class SupplierViewSet(viewsets.ModelViewSet):
    """ViewSet for Supplier CRUD operations"""
    def get_queryset(self):
        """Filter by current tenant"""
        return Supplier.objects.filter(tenant=self.request.user.tenant)
    
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'type', 'payment_terms']
    search_fields = ['name', 'phone', 'email', 'pan']
    ordering_fields = ['name', 'created_at', 'total_purchased']
    ordering = ['-created_at']
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating supplier"""
        serializer.save(tenant=self.request.user.tenant)



@extend_schema_view(
    list=extend_schema(
        description="List all purchase requests for the current tenant",
        tags=["Purchase - Requests"]
    ),
    retrieve=extend_schema(
        description="Get purchase request details with line items",
        tags=["Purchase - Requests"]
    ),
    create=extend_schema(
        description="Create a new purchase request with line items",
        tags=["Purchase - Requests"],
        request=PurchaseRequestCreateSerializer
    ),
    update=extend_schema(
        description="Update purchase request",
        tags=["Purchase - Requests"],
        request=PurchaseRequestCreateSerializer
    ),
    partial_update=extend_schema(
        description="Partially update purchase request",
        tags=["Purchase - Requests"]
    ),
    destroy=extend_schema(
        description="Delete a purchase request",
        tags=["Purchase - Requests"]
    ),
)
class PurchaseRequestViewSet(viewsets.ModelViewSet):
    """ViewSet for Purchase Request CRUD operations with 3-step approval workflow"""
    def get_queryset(self):
        """Filter by current tenant"""
        return PurchaseRequest.objects.filter(tenant=self.request.user.tenant).select_related(
        'requested_by', 'approved_by'
    ).prefetch_related('lines__product')
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'priority', 'department']
    search_fields = ['request_number', 'requested_by__username', 'department']
    ordering_fields = ['date', 'created_at', 'required_by', 'estimated_amount']
    ordering = ['-date', '-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PurchaseRequestCreateSerializer
        return PurchaseRequestSerializer
    
    def perform_create(self, serializer):
        # Set requested_by to current user and tenant
        serializer.save(requested_by=self.request.user, tenant=self.request.user.tenant)
    
    @extend_schema(
        description="Approve a purchase request (Step 2 of 3-step workflow)",
        tags=["Purchase - Requests"],
        request=None,
        responses={200: PurchaseRequestSerializer}
    )
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a purchase request"""
        purchase_request = self.get_object()
        
        if purchase_request.status != 'Pending Approval':
            return Response(
                {'error': 'Only pending requests can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase_request.status = 'Approved'
        purchase_request.approved_by = request.user
        purchase_request.approved_at = timezone.now()
        purchase_request.save()
        
        serializer = self.get_serializer(purchase_request)
        return Response(serializer.data)
    
    @extend_schema(
        description="Reject a purchase request",
        tags=["Purchase - Requests"],
        request={'application/json': {
            'type': 'object',
            'properties': {'reason': {'type': 'string'}}
        }},
        responses={200: PurchaseRequestSerializer}
    )
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a purchase request"""
        purchase_request = self.get_object()
        
        if purchase_request.status not in ['Pending Approval', 'Draft']:
            return Response(
                {'error': 'Only pending or draft requests can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('reason', '')
        if not reason:
            return Response(
                {'error': 'Rejection reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase_request.status = 'Rejected'
        purchase_request.rejection_reason = reason
        purchase_request.save()
        
        serializer = self.get_serializer(purchase_request)
        return Response(serializer.data)
    
    @extend_schema(
        description="Convert approved purchase request to purchase order (Step 3 of 3-step workflow)",
        tags=["Purchase - Requests"],
        request={'application/json': {
            'type': 'object',
            'properties': {
                'supplier': {'type': 'string'},
                'expected_delivery_date': {'type': 'string', 'format': 'date'}
            }
        }},
        responses={201: PurchaseOrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def convert_to_po(self, request, pk=None):
        """Convert approved purchase request to purchase order"""
        purchase_request = self.get_object()
        
        if purchase_request.status != 'Approved':
            return Response(
                {'error': 'Only approved requests can be converted to PO'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        supplier_id = request.data.get('supplier')
        expected_delivery_date = request.data.get('expected_delivery_date')
        
        if not supplier_id or not expected_delivery_date:
            return Response(
                {'error': 'Supplier and expected delivery date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate PO number
        last_po = PurchaseOrder.objects.filter(
            tenant=request.user.tenant
        ).order_by('-id').first()
        if last_po:
            last_num = int(last_po.po_number.split('-')[1])
            po_number = f"PO-{str(last_num + 1).zfill(4)}"
        else:
            po_number = "PO-0001"
        
        # Get supplier
        try:
            supplier = Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return Response(
                {'error': 'Supplier not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create purchase order
        purchase_order = PurchaseOrder.objects.create(
            tenant=request.user.tenant,
            po_number=po_number,
            date=purchase_request.date,
            supplier=supplier,
            expected_delivery_date=expected_delivery_date,
            payment_terms=supplier.payment_terms,
            status='Draft',
            purchase_request=purchase_request,
            created_by=request.user
        )
        
        # Copy lines from purchase request to purchase order
        from .models import PurchaseOrderLine
        for pr_line in purchase_request.lines.all():
            PurchaseOrderLine.objects.create(
                tenant=request.user.tenant,
                purchase_order=purchase_order,
                product=pr_line.product,
                description=pr_line.description,
                quantity=pr_line.quantity,
                unit_price=pr_line.estimated_unit_price,
                tax_percent=13  # Default VAT
            )
        
        purchase_order.calculate_totals()
        
        # Update purchase request status
        purchase_request.status = 'Converted to PO'
        purchase_request.save()
        
        serializer = PurchaseOrderSerializer(purchase_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



@extend_schema_view(
    list=extend_schema(
        description="List all purchase orders for the current tenant",
        tags=["Purchase - Orders"]
    ),
    retrieve=extend_schema(
        description="Get purchase order details with line items",
        tags=["Purchase - Orders"]
    ),
    create=extend_schema(
        description="Create a new purchase order with line items",
        tags=["Purchase - Orders"],
        request=PurchaseOrderCreateSerializer
    ),
    update=extend_schema(
        description="Update purchase order",
        tags=["Purchase - Orders"],
        request=PurchaseOrderCreateSerializer
    ),
    partial_update=extend_schema(
        description="Partially update purchase order",
        tags=["Purchase - Orders"]
    ),
    destroy=extend_schema(
        description="Delete a purchase order",
        tags=["Purchase - Orders"]
    ),
)
class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Purchase Order CRUD operations"""
    def get_queryset(self):
        """Filter by current tenant"""
        return PurchaseOrder.objects.filter(tenant=self.request.user.tenant).select_related(
        'supplier', 'purchase_request', 'created_by'
    ).prefetch_related('lines__product')
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'supplier']
    search_fields = ['po_number', 'reference', 'supplier__name']
    ordering_fields = ['date', 'created_at', 'expected_delivery_date', 'total']
    ordering = ['-date', '-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PurchaseOrderCreateSerializer
        return PurchaseOrderSerializer
    
    def create(self, request, *args, **kwargs):
        """Override create to add better error logging"""
        print(f"[PO Create] Request data: {request.data}")
        print(f"[PO Create] User: {request.user}")
        print(f"[PO Create] Tenant: {request.user.tenant}")
        
        try:
            serializer = self.get_serializer(data=request.data)
            print(f"[PO Create] Serializer created")
            
            if not serializer.is_valid():
                print(f"[PO Create] Validation errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            print(f"[PO Create] Serializer is valid, performing create")
            self.perform_create(serializer)
            
            print(f"[PO Create] Create successful")
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
        except Exception as e:
            import traceback
            print(f"[PO Create Exception] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': str(e), 'type': type(e).__name__},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def perform_create(self, serializer):
        from django.utils import timezone
        tenant = self.request.user.tenant
        
        # Generate po_number
        count = PurchaseOrder.objects.filter(tenant=tenant).count() + 1
        po_number = f"PO-{timezone.now().year}-{count:05d}"
        
        try:
            serializer.save(created_by=self.request.user, tenant=tenant, po_number=po_number)
        except Exception as e:
            import traceback
            print(f"[PO Create Error] {str(e)}")
            print(traceback.format_exc())
            raise
    
    @extend_schema(
        description="Update purchase order status",
        tags=["Purchase - Orders"],
        request={'application/json': {
            'type': 'object',
            'properties': {'status': {'type': 'string'}}
        }},
        responses={200: PurchaseOrderSerializer}
    )
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update the status of a purchase order"""
        purchase_order = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(PurchaseOrder.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase_order.status = new_status
        purchase_order.save()
        
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data)
    
    @extend_schema(
        description="Receive items from purchase order",
        tags=["Purchase - Orders"],
        request={'application/json': {
            'type': 'object',
            'properties': {
                'items': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'line_id': {'type': 'string'},
                            'quantity': {'type': 'number'}
                        }
                    }
                }
            }
        }},
        responses={200: PurchaseOrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def receive_items(self, request, pk=None):
        """Receive items from a purchase order"""
        purchase_order = self.get_object()
        items = request.data.get('items', [])
        default_warehouse_id = request.data.get('warehouse_id')
        
        if not items:
            return Response(
                {'error': 'Items array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .models import PurchaseOrderLine
        from inventory.services import apply_purchase_receive_stock
        from django.db import transaction as db_transaction
        
        try:
            with db_transaction.atomic():
                for item in items:
                    line_id = item.get('line_id')
                    quantity = item.get('quantity')
                    warehouse_id = item.get('warehouse_id') or default_warehouse_id
                    
                    if not line_id or not quantity:
                        continue
                    
                    try:
                        line = PurchaseOrderLine.objects.get(
                            id=line_id,
                            purchase_order=purchase_order
                        )
                    except PurchaseOrderLine.DoesNotExist:
                        return Response(
                            {'error': f'Invalid line id: {line_id}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    receive_qty = float(quantity)
                    if receive_qty <= 0:
                        continue
                    
                    new_received = float(line.received_quantity) + receive_qty
                    if new_received > float(line.quantity):
                        return Response(
                            {'error': f'Received quantity exceeds ordered quantity for {line.product.name}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    apply_purchase_receive_stock(
                        purchase_order,
                        line,
                        receive_qty,
                        performed_by=request.user,
                        warehouse_id=warehouse_id,
                    )
                    
                    line.received_quantity = new_received
                    line.save(update_fields=['received_quantity'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        all_lines = purchase_order.lines.all()
        fully_received = all(
            line.received_quantity >= line.quantity for line in all_lines
        )
        partially_received = any(
            line.received_quantity > 0 for line in all_lines
        )
        
        if fully_received:
            purchase_order.status = 'Received'
        elif partially_received:
            purchase_order.status = 'Partially Received'
        
        purchase_order.save()
        
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data)



@extend_schema_view(
    list=extend_schema(
        description="List all purchase invoices for the current tenant",
        tags=["Purchase - Invoices"]
    ),
    retrieve=extend_schema(
        description="Get purchase invoice details",
        tags=["Purchase - Invoices"]
    ),
    create=extend_schema(
        description="Create a new purchase invoice",
        tags=["Purchase - Invoices"]
    ),
    update=extend_schema(
        description="Update purchase invoice",
        tags=["Purchase - Invoices"]
    ),
    partial_update=extend_schema(
        description="Partially update purchase invoice",
        tags=["Purchase - Invoices"]
    ),
    destroy=extend_schema(
        description="Delete a purchase invoice",
        tags=["Purchase - Invoices"]
    ),
)
class PurchaseInvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for Purchase Invoice CRUD operations"""
    def get_queryset(self):
        """Filter by current tenant"""
        return PurchaseInvoice.objects.filter(tenant=self.request.user.tenant).select_related(
        'supplier', 'purchase_order', 'created_by'
    )
    serializer_class = PurchaseInvoiceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'supplier']
    search_fields = ['invoice_number', 'supplier__name']
    ordering_fields = ['date', 'due_date', 'created_at', 'amount']
    ordering = ['-date', '-created_at']
    
    def perform_create(self, serializer):
        # Pass tenant to serializer for invoice_number generation
        serializer.save(created_by=self.request.user, tenant=self.request.user.tenant)
    
    @extend_schema(
        description="Record payment for a purchase invoice",
        tags=["Purchase - Invoices"],
        request={'application/json': {
            'type': 'object',
            'properties': {'amount': {'type': 'number'}}
        }},
        responses={200: PurchaseInvoiceSerializer}
    )
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record a payment for a purchase invoice"""
        invoice = self.get_object()
        payment_amount = request.data.get('amount')
        
        if not payment_amount:
            return Response(
                {'error': 'Payment amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            payment_amount = float(payment_amount)
        except ValueError:
            return Response(
                {'error': 'Invalid payment amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if payment_amount <= 0:
            return Response(
                {'error': 'Payment amount must be positive'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if invoice.paid_amount + payment_amount > invoice.amount:
            return Response(
                {'error': 'Payment amount exceeds invoice balance'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invoice.paid_amount += payment_amount
        
        # Update status based on payment
        if invoice.paid_amount >= invoice.amount:
            invoice.status = 'Paid'
        elif invoice.paid_amount > 0:
            invoice.status = 'Partially Paid'
        
        invoice.save()

        from purchase.accounting_integration import post_purchase_invoice_payment
        post_purchase_invoice_payment(invoice, payment_amount)
        
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        description="List all debit notes for the current tenant",
        tags=["Purchase - Debit Notes"]
    ),
    retrieve=extend_schema(
        description="Get debit note details",
        tags=["Purchase - Debit Notes"]
    ),
    create=extend_schema(
        description="Create a new debit note",
        tags=["Purchase - Debit Notes"]
    ),
    update=extend_schema(
        description="Update debit note",
        tags=["Purchase - Debit Notes"]
    ),
    partial_update=extend_schema(
        description="Partially update debit note",
        tags=["Purchase - Debit Notes"]
    ),
    destroy=extend_schema(
        description="Delete a debit note",
        tags=["Purchase - Debit Notes"]
    ),
)
class DebitNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for Debit Note CRUD operations"""
    def get_queryset(self):
        """Filter by current tenant"""
        return DebitNote.objects.filter(tenant=self.request.user.tenant).select_related(
        'supplier', 'invoice', 'created_by'
    )
    serializer_class = DebitNoteSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'supplier', 'invoice', 'reason']
    search_fields = ['debit_note_number', 'supplier__name']
    ordering_fields = ['date', 'created_at', 'amount']
    ordering = ['-date', '-created_at']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, tenant=self.request.user.tenant)
