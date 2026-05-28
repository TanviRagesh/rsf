import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '')))
from backend.app import app

print('1) GET /api/v1/health')
with app.test_client() as client:
    resp = client.get('/api/v1/health')
    print('Status:', resp.status_code)
    try:
        print('JSON:', json.dumps(resp.get_json(), indent=2))
    except Exception:
        print('Body:', resp.get_data(as_text=True)[:2000])

print('\n2) POST /offers/api/calculate (simulate session+CSRF)')
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['_csrf_token'] = 'test-csrf-token'
    payload = {'course_id': 1, 'offer_id': None}
    resp = client.post('/offers/api/calculate', json=payload, headers={'X-CSRF-Token': 'test-csrf-token'})
    print('Status:', resp.status_code)
    try:
        print('JSON:', json.dumps(resp.get_json(), indent=2))
    except Exception:
        print('Body:', resp.get_data(as_text=True)[:2000])
