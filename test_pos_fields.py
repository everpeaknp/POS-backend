#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_backend.settings')
django.setup()

from django.db import connection

cursor = connection.cursor()
cursor.execute("PRAGMA table_info(pos_transaction_lines)")
print("Table schema for pos_transaction_lines:")
print("-" * 80)
for row in cursor.fetchall():
    print(f"Column: {row[1]}, Type: {row[2]}, NotNull: {row[3]}, Default: {row[4]}")
