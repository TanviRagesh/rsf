import os
import re
import sys
from dotenv import load_dotenv
load_dotenv('.env')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app
from ..database import get_db, close_db
from ..webservices.notifications import create_notification


def login_session(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'user'
        sess['role'] = 'developer'
        sess['location_id'] = None
        sess['login_ip'] = '127.0.0.1'
        sess['login_ua'] = 'pytest'
        sess['session_fingerprint'] = ''
        sess['_csrf_token'] = 'csrf-test-token'
        sess.permanent = True


def main():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM courses ORDER BY id LIMIT 1;')
    course = cur.fetchone()
    cur.execute('SELECT id FROM offers ORDER BY id LIMIT 1;')
    offer = cur.fetchone()
    close_db(conn, commit=False)

    with app.test_client() as client:
        login_session(client)

        add_resp = client.get('/inquiries/add')
        print('add_status', add_resp.status_code)
        html = add_resp.get_data(as_text=True)
        print('fees_readonly', 'id="fees_total"' in html and 'readonly' in html)
        print('fees_placeholder', 'Auto-calculated from course and offer' in html)

        if course:
            payload = {'course_id': course['id'], 'offer_id': offer['id'] if offer else None}
            calc_resp = client.post(
                '/offers/api/calculate',
                json=payload,
                headers={'X-CSRF-Token': 'csrf-test-token'},
            )
            print('calc_status', calc_resp.status_code)
            print('calc_body', calc_resp.get_json())

        create_notification('Temp validation notification', 'Validate timestamp output', 'developer')
        snap_resp = client.get('/notifications/snapshot')
        print('snapshot_status', snap_resp.status_code)
        snap = snap_resp.get_json() or {}
        items = snap.get('notifications') or []
        print('snapshot_count', snap.get('count'))
        if items:
            created_at = items[0].get('created_at', '')
            print('sample_created_at', created_at)
            print('created_at_matches', bool(re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', created_at)))


if __name__ == '__main__':
    main()
