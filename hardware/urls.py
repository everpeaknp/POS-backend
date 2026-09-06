from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet, DeliveryViewSet, DeliveryItemViewSet, MaterialRateViewSet,
    RentalEquipmentViewSet, RentalViewSet,
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'deliveries', DeliveryViewSet, basename='delivery')
router.register(r'delivery-items', DeliveryItemViewSet, basename='delivery-item')
router.register(r'material-rates', MaterialRateViewSet, basename='material-rate')
router.register(r'rental-equipment', RentalEquipmentViewSet, basename='rental-equipment')
router.register(r'rentals', RentalViewSet, basename='rental')

urlpatterns = [
    path('', include(router.urls)),
]
