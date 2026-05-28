import os
import sys
from dotenv import load_dotenv
load_dotenv('.env')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
	sys.path.insert(0, BASE_DIR)

from ..database import get_db, close_db

conn = get_db()
cur = conn.cursor()
cur.execute("DELETE FROM notifications WHERE title=%s;", ('Temp validation notification',))
removed = cur.rowcount
close_db(conn)
print('REMOVED', removed)
