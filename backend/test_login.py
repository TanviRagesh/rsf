import requests, json
url='http://127.0.0.1:5000/api/v1/auth/login'
print('POST', url)
try:
    resp = requests.post(url, json={'username':'localtester','password':'testpass'}, timeout=5)
    print('status', resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text[:800])
except Exception as e:
    print(f'Error: {e}')
