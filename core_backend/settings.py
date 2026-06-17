"""
Django settings for core_backend project.
"""

from pathlib import Path
from datetime import timedelta
import os
from decouple import config

# ============================================================================
# PYTHON 3.14 COMPATIBILITY PATCH
# ============================================================================
# Apply Django compatibility patch for Python 3.14
# This fixes: AttributeError: 'super' object has no attribute 'dicts'
# Remove this when upgrading to Django 5.1+ which has official Python 3.14 support
try:
    from . import django_py314_patch
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# CORS Settings
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000'
).split(',')

# Application definition
INSTALLED_APPS = [
    # Jazzmin must be before django.contrib.admin
    'jazzmin',
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    
    # Local apps - Core
    'core_backend',
    'tenants',
    'users',
    'utils',
    
    # Local apps - Business Modules
    'inventory',
    'sales',
    'purchase',
    'suppliers',
    'accounting',
    'construction',
    'reports',
    'hr',
    'pos',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'tenants.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'core_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core_backend.wsgi.application'

# Database
# Use SQLite for development if USE_SQLITE is True, otherwise PostgreSQL
USE_SQLITE = config('USE_SQLITE', default=True, cast=bool)

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='khata_db'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='postgres'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kathmandu'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files (User uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Authentication Backends - Use email for login
AUTHENTICATION_BACKENDS = [
    'users.backends.EmailBackend',  # Custom backend for email-based authentication
    'django.contrib.auth.backends.ModelBackend',  # Fallback to default
]

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.authentication.CustomJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=config('JWT_ACCESS_TOKEN_LIFETIME_HOURS', default=1, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')


# DRF Spectacular (Swagger/OpenAPI)
SPECTACULAR_SETTINGS = {
    'TITLE': 'Khata Business OS API',
    'DESCRIPTION': '''
# Khata Business OS - Multi-Tenant ERP API

## 🎯 Overview
Khata is a comprehensive multi-tenant SaaS ERP platform designed for businesses in Nepal.
It provides modules for inventory management, sales, purchases, accounting, construction,
HR, and point-of-sale operations.

## 🔐 Authentication

### Getting Started
1. **Register**: `POST /api/auth/register/` - Create a new account
2. **Login**: `POST /api/auth/login/` - Get JWT access and refresh tokens
3. **Authorize**: Click the 🔓 **Authorize** button above and enter: `Bearer <your_access_token>`
4. **Refresh**: `POST /api/auth/token/refresh/` - Get new token when expired (1 hour lifetime)

### Token Format
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### Token Lifetime
- **Access Token**: 1 hour
- **Refresh Token**: 7 days

## 🏢 Multi-Tenancy
- All data is automatically scoped to your organization (tenant)
- You can only access data belonging to your organization
- Tenant is determined from your JWT token
- No need to pass tenant ID in requests

## 📦 Modules

### Core Modules
- **Authentication**: User registration, login, profile management
- **Users**: User management with role-based access control
- **Tenants**: Organization management and invitations

### Business Modules
- **Inventory**: Products, categories, warehouses, stock management
- **Sales**: Customers, orders, quotations, invoices, credit management
- **Purchase**: Suppliers, purchase orders, purchase requests (3-step approval)
- **Accounting**: Chart of accounts, journal entries, financial reports
- **Construction**: Sites, workers, equipment, daily logs, material consumption
- **HR**: Employees, departments, attendance, leave, payroll
- **POS**: Point of sale, sessions, transactions, discounts
- **Reports**: Sales, purchase, inventory, financial, and custom reports

## 💰 Currency
All amounts are in **NPR (Nepali Rupees)** with 2 decimal places (paisa precision).

Example: `"amount": "1250.50"` = Rs. 1,250.50

## 📄 Pagination
List endpoints return paginated results:
- **Default**: 25 items per page
- **Parameters**: `?page=2&page_size=50`
- **Response includes**: `count`, `next`, `previous`, `results`

Example:
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/inventory/products/?page=3",
  "previous": "http://localhost:8000/api/inventory/products/?page=1",
  "results": [...]
}
```

## 🔍 Filtering & Search
Most list endpoints support:
- **Search**: `?search=keyword` - Full-text search
- **Filtering**: `?field=value` - Filter by field
- **Ordering**: `?ordering=field` or `?ordering=-field` (descending)

Examples:
- `?search=steel&status=active`
- `?category=2&ordering=-created_at`
- `?customer=5&status=Confirmed`

## ⚠️ Error Handling
The API uses standard HTTP status codes:

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Validation error or invalid data |
| 401 | Unauthorized | Authentication required or token expired |
| 403 | Forbidden | Permission denied |
| 404 | Not Found | Resource not found |
| 500 | Internal Server Error | Server error |

### Error Response Format
```json
{
  "error": "Insufficient stock. Available: 50.00",
  "detail": "Cannot complete operation",
  "field": "quantity"
}
```

### Validation Errors
```json
{
  "email": ["This field is required."],
  "quantity": ["Ensure this value is greater than 0."]
}
```

## 🎭 Roles & Permissions
- **Admin**: Full access to all modules
- **Manager**: Manage operations, approve requests
- **Supervisor**: Manage inventory and operations
- **Accountant**: Manage accounting and financial data
- **Cashier**: POS operations only
- **Viewer**: Read-only access

## 🚀 Quick Start Example

### 1. Register & Login
```bash
# Register
curl -X POST http://localhost:8000/api/auth/register/ \\
  -H "Content-Type: application/json" \\
  -d '{"username":"demo","email":"demo@example.com","password":"SecurePass123"}'

# Login
curl -X POST http://localhost:8000/api/auth/login/ \\
  -H "Content-Type: application/json" \\
  -d '{"username":"demo","password":"SecurePass123"}'
```

### 2. Use Token
```bash
curl -X GET http://localhost:8000/api/inventory/products/ \\
  -H "Authorization: Bearer <your_access_token>"
```

## 📚 Additional Resources
- **Swagger UI**: Interactive API testing (this page)
- **ReDoc**: Alternative documentation view at `/api/redoc/`
- **OpenAPI Schema**: Download at `/api/schema/`
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'SERVERS': [
        {'url': 'http://127.0.0.1:8000', 'description': 'Development server'},
        {'url': 'http://localhost:8000', 'description': 'Local server'},
    ],
    'TAGS': [
        {
            'name': 'Authentication',
            'description': '''
**User authentication and profile management**

Endpoints for user registration, login, token refresh, and profile management.

**Key Features:**
- JWT-based authentication
- Token refresh mechanism
- User profile CRUD operations
- Role-based access control
            '''
        },
        {
            'name': 'Users',
            'description': '''
**User management for organization members**

Manage users within your organization with role-based permissions.

**Available Roles:**
- Admin, Manager, Supervisor, Accountant, Cashier, Viewer

**Permissions:**
- Only admins and managers can create/update/delete users
- All authenticated users can view user list
            '''
        },
        {
            'name': 'Tenants',
            'description': '''
**Organization (tenant) management**

Manage organizations, invitations, and multi-tenant operations.

**Features:**
- Create and manage organizations
- Invite users to organizations
- Module-based access control
            '''
        },
        {
            'name': 'Inventory - Categories',
            'description': '''
**Product category management**

Organize products into hierarchical categories.

**Features:**
- Hierarchical category structure (parent-child)
- Category tree view
- Filter products by category
            '''
        },
        {
            'name': 'Inventory - Units',
            'description': '''
**Units of measure management**

Define units for measuring products (kg, ton, bag, piece, etc.).

**Unit Types:**
- Count (piece, box, dozen)
- Weight (kg, ton, gram)
- Length (meter, foot, inch)
- Volume (liter, gallon)
- Area (sqft, sqm)
            '''
        },
        {
            'name': 'Inventory - Warehouses',
            'description': '''
**Warehouse/storage location management**

Manage multiple warehouses and track stock by location.

**Features:**
- Multiple warehouse support
- Warehouse managers
- Stock summary per warehouse
- Active/inactive status
            '''
        },
        {
            'name': 'Inventory - Products',
            'description': '''
**Product management and stock tracking**

Complete product lifecycle management with stock tracking.

**Features:**
- Product CRUD operations
- Stock tracking by warehouse
- Low stock alerts (reorder level)
- Stock history
- Cost and selling price management
            '''
        },
        {
            'name': 'Inventory - Stocks',
            'description': '''
**Stock level monitoring (read-only)**

View current stock levels across all warehouses.

**Note:** Stock is updated through stock operations, not direct editing.
            '''
        },
        {
            'name': 'Inventory - Movements',
            'description': '''
**Stock movement history (read-only)**

Immutable audit trail of all stock changes.

**Movement Types:**
- In: Stock added to warehouse
- Out: Stock removed from warehouse
- Transfer: Stock moved between warehouses
- Adjustment: Stock correction
            '''
        },
        {
            'name': 'Inventory - Operations',
            'description': '''
**Stock operations (in/out/transfer/adjustment)**

Perform stock operations that update inventory levels.

**Operations:**
- **Stock In**: Add stock to warehouse
- **Stock Out**: Remove stock from warehouse (validates availability)
- **Transfer**: Move stock between warehouses
- **Adjustment**: Make corrections to stock levels

**Permissions:** Requires Supervisor or Admin role
            '''
        },
        {
            'name': 'Inventory - Reports',
            'description': '''
**Inventory reporting and analytics**

Generate inventory reports including stock summary, low stock, valuation, and movement reports.
            '''
        },
        {
            'name': 'Sales - Customers',
            'description': '''
**Customer management with credit tracking**

Manage customers with credit limit and balance tracking.

**Features:**
- Customer CRUD operations
- Credit limit management
- Current balance tracking
- Customer ledger
- Aging reports
- Payment terms
            '''
        },
        {
            'name': 'Sales - Orders',
            'description': '''
**Sales order management**

Create and manage sales orders with line items.

**Features:**
- Multi-line orders
- Stock validation
- Order status tracking
- Convert to invoice
- Credit sales support
            '''
        },
        {
            'name': 'Sales - Quotations',
            'description': '''
**Quotation management**

Create quotations and convert to sales orders.

**Features:**
- Multi-line quotations
- Validity period
- Convert to sales order
- Status tracking
            '''
        },
        {
            'name': 'Sales - Invoices',
            'description': '''
**Invoice management**

Generate and manage sales invoices.

**Features:**
- Invoice generation from orders
- Payment tracking
- Due date management
- Invoice status (Draft, Sent, Paid, Overdue)
            '''
        },
        {
            'name': 'Sales - Credit Notes',
            'description': '''
**Credit note management**

Issue credit notes for returns and adjustments.
            '''
        },
        {
            'name': 'Sales - Dashboard',
            'description': '''
**Sales dashboard and analytics**

Comprehensive sales dashboard with revenue charts, top products, and recent orders.
            '''
        },
        {
            'name': 'Purchase - Suppliers',
            'description': '''
**Supplier management**

Manage supplier information and contacts.
            '''
        },
        {
            'name': 'Purchase - Requests',
            'description': '''
**Purchase request management with 3-step approval**

Create purchase requests with multi-level approval workflow.

**Approval Workflow:**
1. Requester creates request
2. Supervisor approves
3. Manager approves
4. Convert to purchase order
            '''
        },
        {
            'name': 'Purchase - Orders',
            'description': '''
**Purchase order management**

Create and manage purchase orders to suppliers.

**Features:**
- Multi-line orders
- Receive items
- Track received quantities
- Order status tracking
            '''
        },
        {
            'name': 'Accounting - Accounts',
            'description': '''
**Chart of accounts management**

Manage the chart of accounts with hierarchical structure.

**Account Types:**
- Asset, Liability, Equity, Revenue, Expense
            '''
        },
        {
            'name': 'Accounting - Journal Entries',
            'description': '''
**Journal entry management**

Create and manage journal entries with debit/credit lines.

**Features:**
- Multi-line entries
- Balanced validation (debit = credit)
- Entry status tracking
            '''
        },
        {
            'name': 'Accounting - Reports',
            'description': '''
**Financial reports**

Generate financial reports including trial balance, profit & loss, and balance sheet.
            '''
        },
        {
            'name': 'Construction - Sites',
            'description': '''
**Construction site management**

Manage construction sites with budget and progress tracking.
            '''
        },
        {
            'name': 'Construction - Workers',
            'description': '''
**Construction worker management**

Manage construction workers and labor tracking.
            '''
        },
        {
            'name': 'Construction - Equipment',
            'description': '''
**Construction equipment management**

Track construction equipment and usage.
            '''
        },
        {
            'name': 'Construction - Daily Logs',
            'description': '''
**Daily construction logs**

Record daily activities, material consumption, and labor hours.
            '''
        },
        {
            'name': 'HR - Employees',
            'description': '''
**Employee management**

Manage employee information and records.
            '''
        },
        {
            'name': 'HR - Departments',
            'description': '''
**Department management**

Organize employees into departments.
            '''
        },
        {
            'name': 'HR - Attendance',
            'description': '''
**Attendance tracking**

Track employee attendance and working hours.
            '''
        },
        {
            'name': 'HR - Leave',
            'description': '''
**Leave management**

Manage employee leave requests and approvals.
            '''
        },
        {
            'name': 'HR - Payroll',
            'description': '''
**Payroll management**

Process employee payroll and salary payments.
            '''
        },
        {
            'name': 'POS - Sessions',
            'description': '''
**POS session management**

Manage point-of-sale sessions with opening and closing cash.
            '''
        },
        {
            'name': 'POS - Transactions',
            'description': '''
**POS transaction management**

Process point-of-sale transactions and sales.

**Payment Methods:**
- Cash, Card, UPI, Credit
            '''
        },
        {
            'name': 'POS - Discounts',
            'description': '''
**POS discount management**

Create and manage discounts for POS transactions.

**Discount Types:**
- Percentage, Fixed Amount
            '''
        },
        {
            'name': 'POS - Products',
            'description': '''
**Product search for POS**

Search products for POS transactions with barcode support.
            '''
        },
        {
            'name': 'POS - Reports',
            'description': '''
**POS reports and analytics**

Generate daily sales reports and POS analytics.
            '''
        },
        {
            'name': 'Reports',
            'description': '''
**Comprehensive reporting module**

Generate reports across all modules including sales, purchase, inventory, and financial reports.
            '''
        },
        {
            'name': 'Permissions',
            'description': '''
**Role-based permission management**

Manage permissions for different user roles.

**Permissions:** Only admins and managers can update permissions
            '''
        },
        {
            'name': 'Audit',
            'description': '''
**Audit log tracking**

View audit logs of all system activities.

**Permissions:** Only admins and managers can view audit logs
            '''
        },
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 3,
        'docExpansion': 'list',
        'syntaxHighlight': {
            'activate': True,
            'theme': 'monokai'
        },
    },
    'SECURITY': [
        {
            'bearerAuth': []
        }
    ],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': 'Enter your JWT token in the format: **Bearer &lt;token&gt;**'
            }
        },
        'schemas': {
            'Error': {
                'type': 'object',
                'properties': {
                    'error': {
                        'type': 'string',
                        'description': 'Error message',
                        'example': 'Insufficient stock. Available: 50.00'
                    },
                    'detail': {
                        'type': 'string',
                        'description': 'Detailed error description',
                        'example': 'Cannot complete the requested operation'
                    },
                    'field': {
                        'type': 'string',
                        'description': 'Field that caused the error (if applicable)',
                        'example': 'quantity'
                    }
                }
            },
            'ValidationError': {
                'type': 'object',
                'additionalProperties': {
                    'type': 'array',
                    'items': {'type': 'string'}
                },
                'example': {
                    'email': ['This field is required.'],
                    'quantity': ['Ensure this value is greater than 0.'],
                    'sku': ['Product with this SKU already exists.']
                }
            },
            'PaginatedResponse': {
                'type': 'object',
                'properties': {
                    'count': {
                        'type': 'integer',
                        'description': 'Total number of items',
                        'example': 150
                    },
                    'next': {
                        'type': 'string',
                        'nullable': True,
                        'description': 'URL to next page',
                        'example': 'http://localhost:8000/api/inventory/products/?page=2'
                    },
                    'previous': {
                        'type': 'string',
                        'nullable': True,
                        'description': 'URL to previous page',
                        'example': None
                    },
                    'results': {
                        'type': 'array',
                        'items': {},
                        'description': 'Array of results'
                    }
                }
            }
        }
    },
}




# ============================================================================
# JAZZMIN ADMIN THEME - Clean & Minimal Configuration
# ============================================================================

JAZZMIN_SETTINGS = {
    # Site branding
    "site_title": "KHATA Admin",
    "site_header": "KHATA",
    "site_brand": "KHATA Business OS",
    "site_logo": None,
    "site_icon": None,
    "welcome_sign": "Welcome to KHATA Business OS",
    "copyright": "KHATA © 2026",
    
    # Search
    "search_model": ["users.User", "tenants.Tenant", "inventory.Product", "sales.Customer"],
    
    # Top menu
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "API Docs", "url": "/api/docs/", "new_window": True},
    ],
    
    # User menu
    "usermenu_links": [
        {"model": "users.user"}
    ],
    
    # Side menu
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    
    # App ordering
    "order_with_respect_to": [
        "tenants",
        "users",
        "inventory",
        "sales",
        "purchase",
        "accounting",
        "construction",
        "hr",
        "reports",
    ],
    
    # Icons for models
    "icons": {
        "auth.User": "fas fa-user",
        "auth.Group": "fas fa-users",
        "users.User": "fas fa-user-tie",
        "tenants.Tenant": "fas fa-building",
        
        "inventory.Product": "fas fa-box",
        "inventory.Category": "fas fa-tags",
        "inventory.Warehouse": "fas fa-warehouse",
        "inventory.UnitOfMeasure": "fas fa-ruler",
        
        "sales.Customer": "fas fa-user-friends",
        "sales.SalesOrder": "fas fa-shopping-cart",
        "sales.Quotation": "fas fa-file-invoice",
        "sales.Invoice": "fas fa-file-invoice-dollar",
        
        "purchase.Supplier": "fas fa-truck",
        "purchase.PurchaseOrder": "fas fa-shopping-bag",
        "purchase.PurchaseRequest": "fas fa-clipboard-list",
        
        "accounting.Account": "fas fa-chart-pie",
        "accounting.JournalEntry": "fas fa-book-open",
        "accounting.BankAccount": "fas fa-university",
        
        "construction.Site": "fas fa-hard-hat",
        "construction.Worker": "fas fa-user-hard-hat",
        "construction.Equipment": "fas fa-tractor",
        
        "hr.Employee": "fas fa-id-card",
        "hr.Department": "fas fa-sitemap",
        "hr.Attendance": "fas fa-calendar-check",
        "hr.Payroll": "fas fa-money-bill-wave",
    },
    
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    
    # UI Tweaks
    "related_modal_active": False,
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
    
    # Change form format
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "horizontal_tabs",
        "users.user": "horizontal_tabs",
    },
    
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-white",
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-light-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": True,
    "theme": "flatly",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": False
}
