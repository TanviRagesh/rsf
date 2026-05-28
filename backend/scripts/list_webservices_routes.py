from backend.app import app

rules = sorted(app.url_map.iter_rules(), key=lambda r: r.rule)
print('REGISTERED ROUTES AND METHODS')
for rule in rules:
    methods = ','.join(sorted([m for m in rule.methods if m not in ('HEAD','OPTIONS')]))
    print(f"{rule.rule:40} {methods:30} -> {rule.endpoint}")

print('\nSAMPLE HEALTH CHECK')
with app.test_client() as client:
    resp = client.get('/api/v1/health', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    print('GET /api/v1/health', resp.status_code)
    try:
        print(resp.get_json())
    except Exception:
        print(resp.get_data(as_text=True))
