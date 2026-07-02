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
