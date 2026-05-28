import os
from dotenv import load_dotenv
load_dotenv('.env')
import psycopg2, psycopg2.extras

conn = psycopg2.connect(host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'), dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASS'))
cur = conn.cursor()
cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id;")
rows = cur.fetchall()
if not rows:
    print('NO_USERS')
else:
    for r in rows:
        print(r)
conn.close()
