import requests, re, sys

LOGIN_URL = 'http://127.0.0.1:5000/login'
USERNAME = 'tester'
PASSWORD = 'tester@123'

s = requests.Session()
try:
    r = s.get(LOGIN_URL, timeout=5)
except Exception as e:
    print('ERROR_FETCH', e)
    sys.exit(2)

m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
if not m:
    print('NO_CSRF')
    sys.exit(3)

token = m.group(1)
payload = {'username': USERNAME, 'password': PASSWORD, 'csrf_token': token}
resp = s.post(LOGIN_URL, data=payload, allow_redirects=False)
print('STATUS', resp.status_code)
print('LOCATION', resp.headers.get('Location'))
print('COOKIES', s.cookies.get_dict())
print('TEXT_PREVIEW', resp.text[:400].replace('\n',' '))
if resp.status_code == 302 and resp.headers.get('Location'):
    print('LOGIN_OK')
    sys.exit(0)
else:
    print('LOGIN_FAILED')
    sys.exit(1)
