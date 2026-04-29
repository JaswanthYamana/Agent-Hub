import traceback
import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

print("--- Testing /api/redteam/run ---")
trace_id_a = None
try:
    payload = {
        "target_scenario": "normal",
        "attack_type": "idpi",
        "agent_target": "demo",
        "intensity": "medium"
    }
    r = requests.post(f"{BASE_URL}/redteam/run", json=payload)
    print("Status:", r.status_code)
    try:
        data = r.json()
        trace_id_a = data.get("attacked_trace_id")
        print("Attacked Trace ID:", trace_id_a)
    except Exception:
        print("Raw Response:", r.text[:300])
except Exception:
    traceback.print_exc()

print("\n--- Testing invalid scenario ---")
try:
    payload = {"task": "test", "scenario": "fake_scenario", "agent_target": "demo"}
    r = requests.post(f"{BASE_URL}/execute", json=payload)
    print("Status:", r.status_code)
    try:
        print("Response:", r.json())
    except:
        print("Text:", r.text[:300])
except Exception:
    traceback.print_exc()

print("\n--- Testing goal_hijacking ---")
trace_id_b = None
try:
    payload = {"task": "Book me a flight", "scenario": "goal_hijacking", "agent_target": "demo"}
    r = requests.post(f"{BASE_URL}/execute", json=payload, stream=True)
    print("Status:", r.status_code)
    
    # Read the streaming response chunks to find the trace_id
    for line in r.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith('event: complete'):
                continue
            if decoded_line.startswith('data: '):
                try:
                    data2 = json.loads(decoded_line[6:])
                    if 'trace' in data2:
                        trace_id_b = data2["trace"]["trace_id"]
                        attack_active = data2["trace"].get("attack_active")
                        print("Goal Hijacking Trace ID:", trace_id_b)
                        print("Attack Active:", attack_active)
                except Exception:
                    pass
except Exception:
    traceback.print_exc()

if trace_id_a:
    print("\n--- Testing /evaluate-span (Span-Level LLM Judge) ---")
    try:
        tr = requests.get(f"{BASE_URL}/traces/{trace_id_a}")
        if tr.status_code == 200:
            spans = tr.json().get("spans", [])
            span_id = spans[0]["span_id"] if spans else "default"
            ev = requests.post(f"{BASE_URL}/traces/{trace_id_a}/evaluate-span", json={"span_id": span_id})
            print("Evaluate Status:", ev.status_code)
            if ev.status_code == 200:
                print("Verdict:", ev.json().get("verdict"))
    except Exception:
        traceback.print_exc()

    print("\n--- Testing Behavioral Risk Scoring ---")
    try:
        risk = requests.get(f"{BASE_URL}/traces/{trace_id_a}/risk")
        print("Risk Status:", risk.status_code)
        print("Risk Response:", risk.json())
    except Exception:
        traceback.print_exc()

if trace_id_a and trace_id_b:
    print("\n--- Testing Trace Divergence Analyzer ---")
    try:
        payload = {"trace_id_a": trace_id_b, "trace_id_b": trace_id_a}
        comp = requests.post(f"{BASE_URL}/traces/compare", json=payload)
        print("Compare Status:", comp.status_code)
        if comp.status_code == 200:
            print("Diverged:", comp.json().get("divergence", {}).get("is_diverged"))
    except Exception as e:
        traceback.print_exc()
