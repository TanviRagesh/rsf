import traceback
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from app import app
    app.testing = True
    # In some setups, session might need a permanent session to keep the CSRF token
    with app.test_client() as c:
        print('--- API LOGIN ---')
        r = c.post('/api/v1/auth/login', json={'username':'localtester','password':'testpass'})
        print(f'API status: {r.status_code}')
        print(r.get_data(as_text=True))
        
        print('\n--- UI LOGIN ---')
        # Using a session object to keep cookies across requests
        # First request to get the login page and the CSRF token
        g = c.get('/login')
        print(f'GET /login status: {g.status_code}')
        
        # If it redirects to /dashboard, it means we are already logged in
        if g.status_code == 302:
             print(f"Redirected to: {g.headers.get('Location')}")
             # Let's try to logout first or clear session
             c.get('/logout') # Assuming there's a /logout
             g = c.get('/login')
             print(f'GET /login status after logout: {g.status_code}')

        html = g.get_data(as_text=True)
        
        import re
        # Look for the CSRF token in the HTML
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        token = m.group(1) if m else None
        print(f'CSRF token found: {bool(token)}')
        
        data = {'username':'localtester','password':'testpass'}
        if token:
            data['csrf_token'] = token
            
        r2 = c.post('/login', data=data, follow_redirects=True)
        print(f'POST /login status: {r2.status_code}')
        print('Final URL:', r2.request.url)
        print('Response body snippet:')
        print(r2.get_data(as_text=True)[:500])
except Exception:
    traceback.print_exc()
