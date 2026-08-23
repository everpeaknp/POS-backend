import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
import django
django.setup()

from django.db import connection

token = '29a2e04ec5104c27ae2ea20639540554'
print(f"Testing token: {token}\n")

# First, check table names
print("=== Available tables ===")
table_names = connection.introspection.table_names()
finance_tables = [t for t in table_names if 'finance' in t and 'part' in t.lower()]
print(f"Finance/Party tables: {finance_tables}\n")

# Test the exact query
print("=== Testing raw SQL query ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT * FROM finance_parties_lenders WHERE share_token = %s", [token])
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    print(f"Columns: {columns}")
    print(f"Row: {row}\n")

# If not found, try alternative table names
if not row:
    print("=== Token not found in finance_parties_lenders, trying alternatives ===")
    for table in finance_tables:
        if 'party' in table.lower():
            print(f"Trying table: {table}")
            with connection.cursor() as cursor:
                try:
                    cursor.execute(f"SELECT * FROM {table} WHERE share_token = %s", [token])
                    columns = [col[0] for col in cursor.description]
                    row = cursor.fetchone()
                    if row:
                        print(f"  FOUND! Row: {row}")
                        break
                    else:
                        print(f"  Not found in this table")
                except Exception as e:
                    print(f"  Error: {e}")

# Also check if the token even exists at all
print("\n=== Checking all party tokens ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT id, name, share_token FROM finance_parties_lenders LIMIT 5")
    for row in cursor.fetchall():
        print(f"  ID: {row[0]}, Name: {row[1]}, Token: {row[2]}")
