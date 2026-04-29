import urllib.request
import json
import time

def get_json(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode('utf-8'))

def post_json(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode('utf-8'))

print('Triggering baseline...')
b_res = post_json('http://localhost:8000/api/execute', {'task': 'Book a flight', 'scenario': 'normal'})
b_id = b_res['trace_id']
print('Baseline:', b_id)

print('Triggering attack...')
a_res = post_json('http://localhost:8000/api/execute', {'task': 'Book a flight', 'scenario': 'goal_hijacking'})
a_id = a_res['trace_id']
print('Attack:', a_id)

print('Waiting 10s...')
time.sleep(10)

print('\nFetching Risk:')
try:
    risk = get_json(f'http://localhost:8000/api/traces/{a_id}/risk')
    print('Risk:', json.dumps(risk, indent=2))
except Exception as e:
    print('Risk Error:', e)

print('\nFetching Compare:')
try:
    comp = get_json(f'http://localhost:8000/api/replay/compare?baseline_id={b_id}&attacked_id={a_id}')
    print('Compare Data Contains:')
    for k, v in comp.items():
        if isinstance(v, list):
            print(f' - {k}: {len(v)} items')
        else:
            print(f' - {k}: {v}')
except Exception as e:
    print('Compare Error:', e)

