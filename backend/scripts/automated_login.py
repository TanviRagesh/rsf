import requests
import re

s = requests.Session()
base = 'http://127.0.0.1:5000'
resp = s.get(base + '/login')
print('GET /login', resp.status_code)
# extract csrf_token using regex
match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', resp.text)
csrf_val = match.group(1) if match else ''
print('csrf:', csrf_val)
# post login
payload = {
    'username':'user',
    'password':'user@123',
    'csrf_token': csrf_val
}
resp2 = s.post(base + '/login', data=payload, allow_redirects=False)
print('POST /login', resp2.status_code)
if 'Location' in resp2.headers:
    print('Redirect to', resp2.headers['Location'])
# now request dashboard
resp3 = s.get(base + '/dashboard')
print('GET /dashboard', resp3.status_code)
print(resp3.text[:400])
