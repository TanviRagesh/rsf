import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
import psycopg2
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST','localhost'),
        port=int(os.getenv('DB_PORT','5432')),
        dbname=os.getenv('DB_NAME','inquiry_db'),
        user=os.getenv('DB_USER','postgres'),
        password=os.getenv('DB_PASS',''),
        connect_timeout=5,
    )
    cur = conn.cursor()
    cur.execute('SELECT version()')
    print('OK', cur.fetchone())
    cur.close()
    conn.close()
except Exception as e:
    print('ERROR', e)
