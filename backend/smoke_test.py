from app import app
app.testing = True
with app.test_client() as c:
    r = c.get('/')
    print(f'GET / {r.status_code}')
    r2 = c.get('/login')
    print(f'GET /login {r2.status_code}')
    ra = c.post('/api/v1/auth/login', json={'username':'localtester','password':'testpass'})
    print(f'/api login {ra.status_code} {ra.get_data(as_text=True)[:400]}')
