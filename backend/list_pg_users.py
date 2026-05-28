from dotenv import load_dotenv
import os, psycopg2
load_dotenv('.env')
PG={'host':os.getenv('DB_HOST'),'port':int(os.getenv('DB_PORT')),'dbname':os.getenv('DB_NAME'),'user':os.getenv('DB_USER'),'password':os.getenv('DB_PASS')}
conn=psycopg2.connect(**PG)
cur=conn.cursor()
cur.execute("SELECT id,username,role FROM users ORDER BY id")
for r in cur.fetchall():
    print(r)
cur.close(); conn.close()
