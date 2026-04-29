from typing import Any, Dict, List, Optional
from core.models import Trace, SpanKind, SemanticAttributes

def extract_execution_sequence(trace: Trace) -> List[Dict[str, Any]]:
    """Extract ordered tool execution sequence."""
    seq = []
    # Assumes spans are chronologically ordered.
    for s in trace.spans:
        if s.kind == SpanKind.TOOL:
            seq.append({
                "span_id": s.span_id,
                "tool": s.attributes.get(SemanticAttributes.TOOL_NAME, s.name),
                "params": s.attributes.get(SemanticAttributes.INPUT_PARAMS, {}),
                "status": s.status.value if hasattr(s.status, "value") else str(s.status)
            })
    return seq

def compare_traces(baseline: Trace, attacked: Trace) -> Dict[str, Any]:
    """Find the exact point of divergence between two execution sequences."""
    seq_base = extract_execution_sequence(baseline)
    seq_attack = extract_execution_sequence(attacked)
    
    divergence_point = None
    divergence_reason = None
    
    min_len = min(len(seq_base), len(seq_attack))
    for i in range(min_len):
        b = seq_base[i]
        a = seq_attack[i]
        
        if b["tool"] != a["tool"]:
            divergence_point = i
            divergence_reason = f"Tool mismatch: expected {b['tool']}, found {a['tool']}"
            break
        if b["params"] != a["params"]:
            divergence_point = i
            divergence_reason = f"Parameter mismatch on {b['tool']}"
            break
            
    if divergence_point is None and len(seq_base) != len(seq_attack):
        divergence_point = min_len
        if len(seq_attack) > len(seq_base):
            divergence_reason = "Attacked trace has extra unexpected steps"
        else:
            divergence_reason = "Attacked trace ended prematurely missing expected steps"
            
    return {
        "baseline_sequence": seq_base,
        "attacked_sequence": seq_attack,
        "divergence_index": divergence_point,
        "divergence_reason": divergence_reason,
        "is_diverged": divergence_point is not None
    }
