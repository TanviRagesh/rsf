import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import get_db, close_db

conn = get_db(); cur = conn.cursor()
print('Inserting test channel partner...')
cur.execute("INSERT INTO channel_partners (name,phone,email,address) VALUES (%s,%s,%s,%s) RETURNING id;", ('CP Test','9999999999','cp@test.local','Test address'))
row = cur.fetchone()
cp_id = row['id'] if row else None
print('Inserted id=', cp_id)
cur.execute('SELECT id,name,phone,email FROM channel_partners WHERE id=%s;', (cp_id,))
print('Fetched:', cur.fetchone())
print('Updating name...')
cur.execute('UPDATE channel_partners SET name=%s WHERE id=%s;', ('CP Test Updated', cp_id))
cur.execute('SELECT name FROM channel_partners WHERE id=%s;', (cp_id,))
print('After update:', cur.fetchone())
print('Deleting...')
cur.execute('DELETE FROM channel_partners WHERE id=%s;', (cp_id,))
cur.execute('SELECT id FROM channel_partners WHERE id=%s;', (cp_id,))
print('Exists after delete:', cur.fetchone())
close_db(conn)
