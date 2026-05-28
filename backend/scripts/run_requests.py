import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from backend.app import app

print('RUNNING TEST REQUESTS')
with app.test_client() as client:
    print('\n1) GET /api/v1/health')
    resp = client.get('/api/v1/health')
    print('Status:', resp.status_code)
    try:
        print('JSON:', resp.get_json())
    except Exception:
        print('Body:', resp.get_data(as_text=True))

    print('\n2) POST /offers/api/calculate (simulate session)')
    # set minimal session values to satisfy login_required and role checks
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['location_id'] = None
        # set test CSRF token as tests do
        sess['_csrf_token'] = 'test-csrf-token'

    payload = {'course_id': 1, 'offer_id': None}
    try:
        resp = client.post('/offers/api/calculate', json=payload, headers={"X-CSRF-Token": 'test-csrf-token'})
        print('Status:', resp.status_code)
        try:
            print('JSON:', resp.get_json())
        except Exception:
            print('Body:', resp.get_data(as_text=True))
    except Exception as exc:
        print('Request raised exception:', exc)
        import traceback
        traceback.print_exc()

    print('\n3) GET /whatsapp/api/templates')
    try:
        resp = client.get('/whatsapp/api/templates')
        print('Status:', resp.status_code)
        try:
            print('JSON:', resp.get_json())
        except Exception:
            print('Body:', resp.get_data(as_text=True))
    except Exception as exc:
        print('Request raised exception:', exc)
        import traceback
        traceback.print_exc()
    
    print('\n4) GET /api/v1/users (API, requires auth/session)')
    try:
        resp = client.get('/api/v1/users')
        print('Status:', resp.status_code)
        try:
            print('JSON:', resp.get_json())
        except Exception:
            print('Body:', resp.get_data(as_text=True))
    except Exception as exc:
        print('Request raised exception:', exc)
        import traceback
        traceback.print_exc()
