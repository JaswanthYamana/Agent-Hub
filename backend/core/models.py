"""
core/models.py – Canonical domain models for the AI Agent Observability Platform.

Follows OpenTelemetry GenAI semantic conventions v1.37+ (AGENT, CHAIN, TOOL,
RETRIEVER, LLM, CLIENT span kinds) as defined in the research document.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enumerations ───────────────────────────────────────────────────────────

class SpanKind(str, Enum):
    AGENT     = "AGENT"       # Agent reasoning / decision node
    TOOL      = "TOOL"        # External tool / API call
    CHAIN     = "CHAIN"       # Orchestration wrapper
    RETRIEVER = "RETRIEVER"   # RAG / knowledge-base fetch
    LLM       = "LLM"         # Underlying LLM inference
    CLIENT    = "CLIENT"      # Remote service (e.g. AWS Bedrock)
    INTERNAL  = "INTERNAL"    # In-process orchestration step


class SpanStatus(str, Enum):
    PENDING     = "PENDING"
    OK          = "OK"
    ERROR       = "ERROR"
    HALLUCINATED = "HALLUCINATED"   # Claimed success without execution
    ANOMALOUS   = "ANOMALOUS"       # Behaviourally suspicious


class SemanticAttributes(str, Enum):
    TOOL_NAME = "tool.name"
    INPUT_PARAMS = "tool.input_params"
    OUTPUT = "tool.output"


class AnomalyType(str, Enum):
    REASONING_LOOP       = "REASONING_LOOP"
    WRONG_TOOL_SELECTION = "WRONG_TOOL_SELECTION"
    WRONG_PARAMETERS     = "WRONG_PARAMETERS"
    SKIPPED_STEP         = "SKIPPED_STEP"
    HALLUCINATED_OUTPUT  = "HALLUCINATED_OUTPUT"
    PROMPT_INJECTION     = "PROMPT_INJECTION"
    UNAUTHORIZED_TOOL    = "UNAUTHORIZED_TOOL"
    EXCESSIVE_STEPS      = "EXCESSIVE_STEPS"
    PARTIAL_COMPLETION   = "PARTIAL_COMPLETION"
    SCHEMA_POISONING     = "SCHEMA_POISONING"
    ABNORMAL_LATENCY     = "ABNORMAL_LATENCY"
    STATISTICAL_OUTLIER  = "STATISTICAL_OUTLIER"  # derived from DB baselines
    WORKFLOW_DEVIATION   = "WORKFLOW_DEVIATION"    # actual tool sequence diverges from optimal
    GOAL_HIJACKING       = "GOAL_HIJACKING"        # agent deviates toward attacker-defined goal


class AttackType(str, Enum):
    IDPI            = "idpi"            # Indirect Prompt Injection
    SCHEMA_POISON   = "schema_poison"   # MCP / tool-manifest injection
    TOOL_FUZZING    = "tool_fuzzing"    # Contradictory schemas
    MEMORY_POISON   = "memory_poison"   # RAG backdoor (AgentPoison pattern)
    GOAL_HIJACKING  = "goal_hijacking"  # Redirect agent to attacker-defined objective
    JAILBREAK       = "jailbreak"       # Override safety constraints via adversarial prompt
    CONTEXT_OVERFLOW = "context_overflow"  # Force-truncate safety context via long inputs


# ── Span ───────────────────────────────────────────────────────────────────

class SpanEvent(BaseModel):
    timestamp: float
    name: str
    attributes: Dict[str, Any] = {}


class Span(BaseModel):
    span_id:        str = Field(default_factory=lambda: uuid.uuid4().hex)
    trace_id:       str
    parent_span_id: Optional[str] = None

    kind:   SpanKind
    name:   str

    start_time:  float
    end_time:    Optional[float] = None
    duration_ms: Optional[float] = None

    status:        SpanStatus = SpanStatus.PENDING
    attributes:    Dict[str, Any] = {}
    events:        List[SpanEvent] = []
    error_message: Optional[str] = None
    # Structured error classification (e.g. TimeoutError, AuthError)
    error_type:    Optional[str] = None

    contains_injection: bool = False
    injection_payload:  Optional[str] = None

    # Platform metadata
    service_name:        str = "demo-agent"
    environment:         str = "development"  # development | staging | production
    agent_version:       Optional[str] = None  # semver of the agent releasing this span
    project_id:          str = "default"
    session_id:          Optional[str] = None
    # Identifies the agent instance that emitted this span (for multi-agent tracing)
    agent_id:            Optional[str] = None
    token_usage:         Dict[str, int] = {}
    # LLM-specific fields (populated for SpanKind.LLM spans)
    model_name:          Optional[str] = None  # e.g. "gpt-4o", "claude-3-5-sonnet"
    # Structured error category (e.g. TimeoutError, AuthError, RateLimitError)
    error_category:      Optional[str] = None
    # Arbitrary resource-level attributes (host, k8s pod, region, etc.)
    resource_attributes: Dict[str, Any] = {}


# ── Trace ──────────────────────────────────────────────────────────────────

class Trace(BaseModel):
    trace_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = "default"
    session_id: Optional[str] = None
    source:     str = "demo_agent"

    task:     str
    scenario: str
    tags:     List[str] = []

    start_time:  float
    end_time:    Optional[float] = None
    duration_ms: Optional[float] = None

    spans:           List[Span] = []
    total_steps:     int = 0
    tool_call_count: int = 0
    error_count:     int = 0
    token_usage:     Dict[str, int] = {}

    anomalies: List[Dict[str, Any]] = []
    metrics:   Dict[str, Any] = {}

    attack_active:   bool = False
    attack_type:     Optional[str] = None
    attack_succeeded: bool = False

    risk_score: Optional[int] = None
    risk_level: Optional[str] = None

    completed:          bool = False
    success:            bool = False
    partial_completion: bool = False
    final_summary:      str = ""
    root_span_id:       Optional[str] = None


# ── Evaluation ─────────────────────────────────────────────────────────────

class JudgeAssessment(BaseModel):
    span_id:   str
    span_name: str
    span_kind: SpanKind
    criterion: str
    score:     float        # 0.0 – 1.0
    verdict:   str          # PASS | WARN | FAIL
    explanation:    str
    recommendation: Optional[str] = None


class JudgeVerdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class LLMJudgeResult(BaseModel):
    """Structured verdict from a real-LLM evaluation of a full trace."""
    trace_id:               str
    tool_selection:         str   # PASS | WARN | FAIL
    parameter_correctness:  str   # PASS | WARN | FAIL
    reasoning_faithfulness: str   # PASS | WARN | FAIL
    workflow_order:         str   # PASS | WARN | FAIL
    task_completion:        str   # PASS | WARN | FAIL
    explanation:            str
    confidence_score:       Optional[float] = None   # 0.0 – 1.0, if provided by model
    source:                 str = "llm"              # "llm" | "rule_based"
    judge_backend:          str = "llm"              # "llm" | "rule_based_fallback"
    model:                  Optional[str]  = None    # e.g. "gpt-4o", "claude-3-5-sonnet"
    created_at:             float = Field(default_factory=time.time)

    @property
    def overall_verdict(self) -> str:
        verdicts = [
            self.tool_selection, self.parameter_correctness,
            self.reasoning_faithfulness, self.workflow_order, self.task_completion,
        ]
        if any(v == "FAIL" for v in verdicts): return "FAIL"
        if any(v == "WARN" for v in verdicts): return "WARN"
        return "PASS"


class EvaluationReport(BaseModel):
    trace_id: str
    task:     str
    scenario: str

    pass_k:                  Optional[float] = None
    tool_selection_accuracy: float = 0.0
    parameter_correctness:   float = 0.0
    task_completion_rate:    float = 0.0
    workflow_correctness:    float = 0.0   # sequence similarity vs optimal path (0-1)
    attack_resistance:       float = 1.0   # 1 - mean ASR across red-team runs (0-1)
    goal_success:            bool  = False
    attack_success_rate:     Optional[float] = None

    anomalies_detected:  List[Dict[str, Any]] = []
    judge_assessments:   List[JudgeAssessment] = []
    llm_judge_result:    Optional["LLMJudgeResult"] = None   # populated when LLM judge ran

    overall_reliability_score: float = 0.0
    recommendations:           List[str] = []


# ── Graph ──────────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    span_id:     str
    name:        str
    kind:        SpanKind
    status:      SpanStatus
    start_time:  float
    end_time:    Optional[float] = None
    duration_ms: Optional[float] = None
    depth:       int = 0
    attributes:  Dict[str, Any] = {}


class GraphEdge(BaseModel):
    source: str   # parent span_id
    target: str   # child span_id
    label:  Optional[str] = None


class ExecutionGraph(BaseModel):
    trace_id:      str
    nodes:         List[GraphNode] = []
    edges:         List[GraphEdge] = []
    has_cycles:    bool = False
    cycle_spans:   List[str] = []
    critical_path: List[str] = []
    max_depth:     int = 0
    stats:         Dict[str, Any] = {}


# ── Baselines ──────────────────────────────────────────────────────────────

class BaselineStats(BaseModel):
    project_id:   str = "default"
    span_name:    str
    metric:       str
    mean:         float
    std:          float
    p50:          float
    p95:          float
    p99:          float
    sample_count: int
    computed_at:  float = Field(default_factory=time.time)


# ── Red-Team ───────────────────────────────────────────────────────────────

class RedTeamRequest(BaseModel):
    attack_type:     AttackType
    target_scenario: str = "normal"
    intensity:       str = "medium"    # low | medium | high
    agent_target:    str = "demo"      # demo | real | external



class AttackResult(BaseModel):
    attack_id:   str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp:   float = Field(default_factory=time.time)
    attack_type: str
    intensity:   str
    description: str

    baseline_metrics: Dict[str, Any] = {}
    attacked_metrics: Dict[str, Any] = {}
    baseline_trace_id: Optional[str] = None
    attacked_trace_id: Optional[str] = None

    attack_success_rate: float = 0.0
    reliability_delta:   float = 0.0
    platform_detection:  bool  = False
    anomalies_detected:  List[Dict[str, Any]] = []
    injection_payload:   str = ""
    countermeasures:     List[str] = []


# ── API request/response helpers ───────────────────────────────────────────

class TaskRequest(BaseModel):
    task:       str
    scenario:   str = "normal"
    project_id: str = "default"
    tags:       List[str] = []
    k_trials:   int = Field(default=1, ge=1, le=20)
    # Optionally pre-assign a trace_id (set by the API layer before dispatching)
    trace_id:   Optional[str] = None


class PassKRequest(BaseModel):
    task:       str = "Book the cheapest flight to Delhi tomorrow and send confirmation email."
    k:          int = Field(default=5, ge=2, le=20)
    scenario:   str = "normal"
    project_id: str = "default"


class IngestRequest(BaseModel):
    """Payload for the SDK /api/ingest endpoint (non-OTLP path)."""
    trace_id:     str
    spans:        List[Dict[str, Any]]
    project_id:   str = "default"
    service_name: str = "external-agent"
