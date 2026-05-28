import sys, os, traceback

proj_root = os.path.abspath(os.path.dirname(__file__))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
print('Using project root:', proj_root)

try:
    from backend.app import app
except Exception:
    print('Failed to import backend.app')
    traceback.print_exc()
    raise

app.testing = True
app.debug = True

print('Diagnostic: GET /dashboard')
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
    try:
        resp = client.get('/dashboard')
        print('Status:', resp.status_code)
        print('Response (first 8000 chars):')
        print(resp.get_data(as_text=True)[:8000])
    except Exception:
        traceback.print_exc()
