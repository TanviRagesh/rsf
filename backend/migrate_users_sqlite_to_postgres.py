"""Migrate users from backend/heavy_dev.db (SQLite) into PostgreSQL using credentials in .env
"""
import os
from dotenv import load_dotenv
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

BASE = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE, '.env'))

DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite')
if DB_ENGINE != 'postgres':
    print('DB_ENGINE is not postgres in .env; aborting')
    raise SystemExit(2)

PG = {
    'host': os.getenv('DB_HOST','localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'dbname': os.getenv('DB_NAME','inquiry_db'),
    'user': os.getenv('DB_USER','postgres'),
    'password': os.getenv('DB_PASS',''),
}

SQLITE_PATH = os.path.join(BASE, 'heavy_dev.db')
if not os.path.exists(SQLITE_PATH):
    print('SQLite DB not found at', SQLITE_PATH)
    raise SystemExit(3)

# Read users from sqlite
sconn = sqlite3.connect(SQLITE_PATH)
sconn.row_factory = sqlite3.Row
scur = sconn.cursor()
scur.execute('SELECT id,username,email,password_hash,role,location_id,failed_login_attempts,locked_until,last_failed_login_at,created_at FROM users')
rows = [dict(r) for r in scur.fetchall()]
print(f'Found {len(rows)} users in sqlite')

# Connect to postgres
conn = psycopg2.connect(**PG)
cur = conn.cursor()

# Insert users into postgres; use ON CONFLICT (username) DO NOTHING
records = []
for r in rows:
    # Avoid inserting free-form timestamp/text fields that may not parse in Postgres.
    records.append((r.get('id'), r.get('username'), r.get('email'), r.get('password_hash'), r.get('role') or 'teacher', r.get('location_id'), r.get('failed_login_attempts') or 0))

# Insert only safe columns; let Postgres set defaults for timestamp fields.
sql = '''INSERT INTO users (id,username,email,password_hash,role,location_id,failed_login_attempts)
VALUES %s
ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username, email=EXCLUDED.email, password_hash=EXCLUDED.password_hash, role=EXCLUDED.role
'''

if records:
    execute_values(cur, sql, records)
conn.commit()
print('Migrated users to Postgres')
cur.close()
conn.close()
sconn.close()
