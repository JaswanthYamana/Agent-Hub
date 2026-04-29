from core.models import Trace

def compute_risk(trace: Trace) -> dict:
    """Computes risk score (0-100) and risk level from an agent trace based on anomalies."""
    score = 0
    anomalies = trace.anomalies or []
    
    # Simple mapping of anomaly types to risk weights
    weights = {
        "GOAL_HIJACKING": 40,
        "DATA_EXFILTRATION": 40,
        "PROMPT_INJECTION": 30,
        "SCHEMA_POISONING": 30,
        "MEMORY_POISON": 25,
        "UNAUTHORIZED_TOOL": 20,
        "HALLUCINATED_OUTPUT": 15,
        "WORKFLOW_DEVIATION": 10,
        "REASONING_LOOP": 10,
        "API_LATENCY": 5,
        "PAYLOAD_ANOMALY": 15,
        "UNUSUAL_PARAMETERS": 10,
        "UNUSUAL_DURATION": 5
    }
    
    for anomaly in anomalies:
        t = anomaly.get("type", "")
        # Add the weight if known, otherwise base score of 5 for unknown anomalies
        score += weights.get(t, 5)
            
    # Cap score at 100
    score = min(score, 100)
    
    # Strata determination
    if score >= 60:
        level = "CRITICAL"
    elif score >= 30:
        level = "HIGH RISK"
    elif score >= 10:
        level = "LOW RISK"
    else:
        level = "SAFE"
        
    return {
        "risk_score": score,
        "risk_level": level
    }
