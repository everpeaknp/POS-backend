import os
import requests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
import django
django.setup()

# Test the HTTP endpoint
token = '29a2e04ec5104c27ae2ea20639540554'
url = f'http://localhost:8000/api/finance/public-party-share/{token}/'

print(f"Testing endpoint: {url}\n")

try:
    response = requests.get(url)
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
