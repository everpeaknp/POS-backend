# POS-backend

## Run on Windows

`python` is often not on PATH. Use the **`py`** launcher instead:

```powershell
cd backend
py manage.py runserver
```

Or use the helper scripts:

```powershell
.\run-server.ps1
# or
.\manage.ps1 migrate
.\manage.ps1 runserver
```

```cmd
run-server.bat
```

If you prefer `python manage.py ...`, install Python from [python.org](https://www.python.org/downloads/) and check **"Add python.exe to PATH"**, or disable the Microsoft Store alias under **Settings → Apps → Advanced app settings → App execution aliases**.

## Platform admin (`/admin`)

Django admin is the **internal KHATA control plane** (organizations, users, audit logs)—not the customer product.

- **Customer app:** Next.js frontend + REST APIs
- **Platform admin:** `/admin` — **superusers only**

Create a platform operator account:

```powershell
py manage.py createsuperuser
```

Tenant/customer users should stay **non-staff** and use the frontend only.

### eSewa billing (subscription payments)

**Configure in Platform Admin:** `/admin` → **Settings** → **eSewa integration**

| Field | Description |
|-------|-------------|
| Enabled | Turn eSewa checkout on/off |
| Use sandbox | Test vs production eSewa endpoints |
| Product code | Merchant code from eSewa (`EPAYTEST` for sandbox) |
| Secret key | HMAC secret from eSewa |
| Frontend URL | Customer app URL for payment callbacks |

Env vars (optional fallback if DB fields are empty):

```env
FRONTEND_URL=http://localhost:3000
ESEWA_PRODUCT_CODE=EPAYTEST
ESEWA_SECRET_KEY=8gBm/:&EnhH.1/q
```

API: `GET /api/billing/overview/`, `POST /api/billing/checkout/`, `POST /api/billing/verify/`
