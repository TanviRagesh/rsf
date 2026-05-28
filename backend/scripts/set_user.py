import os
import sys
from dotenv import load_dotenv
load_dotenv('.env')
# Ensure the backend package root is on sys.path so imports like `from database import ...` work
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from ..database import get_db, close_db
from ..security import hash_password

USERNAME = os.getenv('NEW_USER_USERNAME', 'user')
PASSWORD = os.getenv('NEW_USER_PASSWORD', 'user@123')
EMAIL = os.getenv('NEW_USER_EMAIL', 'user@local')
ROLE = os.getenv('NEW_USER_ROLE', 'developer')

conn = get_db()
cur = conn.cursor()
# Check existing
cur.execute("SELECT id FROM users WHERE username=%s;", (USERNAME,))
row = cur.fetchone()
if row:
    uid = row.get('id') if isinstance(row, dict) else row[0]
    cur.execute("UPDATE users SET password_hash=%s, email=%s, role=%s WHERE id=%s;", (hash_password(PASSWORD), EMAIL, ROLE, uid))
    print('UPDATED', USERNAME)
else:
    cur.execute("INSERT INTO users (username,email,password_hash,role) VALUES (%s,%s,%s,%s) RETURNING id;", (USERNAME, EMAIL, hash_password(PASSWORD), ROLE))
    new = cur.fetchone()
    print('CREATED', USERNAME, 'id=', new.get('id') if isinstance(new, dict) else new[0])
close_db(conn)
