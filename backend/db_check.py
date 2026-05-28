import os,sys
from dotenv import load_dotenv
load_dotenv('.env')
import psycopg2
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        connect_timeout=5
    )
    print('OK - connected, server_version:', conn.server_version)
    conn.close()
except Exception as e:
    print('ERROR:', type(e).__name__, e)
    sys.exit(1)
