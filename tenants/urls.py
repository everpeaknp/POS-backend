from django.urls import path
from .views import (
    TenantViewSet,
    OrganizationInvitationViewSet,
    preview_invitation,
    accept_invitation_by_token,
)

urlpatterns = [
    # Tenant CRUD - using slug as lookup field
    path('', TenantViewSet.as_view({'get': 'list', 'post': 'create'}), name='tenant-list'),

    # Custom tenant actions (must come before slug routes)
    path('current/', TenantViewSet.as_view({'get': 'current'}), name='tenant-current'),
    path('update_current/', TenantViewSet.as_view({'patch': 'update_current'}), name='tenant-update-current'),
    path('profile/', TenantViewSet.as_view({'get': 'profile'}), name='tenant-profile'),

    # Invitations (must come before tenant slug routes to avoid conflicts)
    path('invitations/', OrganizationInvitationViewSet.as_view({'get': 'list', 'post': 'create'}), name='invitation-list'),
    path('invitations/sent/', OrganizationInvitationViewSet.as_view({'get': 'sent'}), name='invitation-sent'),
    path('invitations/received/', OrganizationInvitationViewSet.as_view({'get': 'received'}), name='invitation-received'),
    path('invitations/by-token/<uuid:token>/', preview_invitation, name='invitation-preview'),
    path('invitations/by-token/<uuid:token>/accept/', accept_invitation_by_token, name='invitation-accept-token'),
    path('invitations/<int:pk>/', OrganizationInvitationViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='invitation-detail'),
    path('invitations/<int:pk>/respond/', OrganizationInvitationViewSet.as_view({'post': 'respond'}), name='invitation-respond'),
    path('invitations/<int:pk>/cancel/', OrganizationInvitationViewSet.as_view({'post': 'cancel'}), name='invitation-cancel'),

    # Tenant detail routes with slug (must come AFTER specific routes like invitations/)
    path('<slug:slug>/', TenantViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='tenant-detail'),
    path('<slug:slug>/activate_module/', TenantViewSet.as_view({'post': 'activate_module'}), name='tenant-activate-module'),
    path('<slug:slug>/deactivate_module/', TenantViewSet.as_view({'post': 'deactivate_module'}), name='tenant-deactivate-module'),
    path('<slug:slug>/switch/', TenantViewSet.as_view({'post': 'switch'}), name='tenant-switch'),
]
