"""
core/config.py – Platform-wide configuration and domain definitions.

Domains encode the expected tool sequence and parameter schemas for a given
agent task type.  New domains can be registered here without code changes.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Set

# Import starter domains
from domains.definitions import (
    CODE_REVIEW_DOMAIN,
    CUSTOMER_SUPPORT_DOMAIN,
    DATA_ANALYSIS_DOMAIN,
    OPERATIONS_TRIAGE_DOMAIN,
    PROCUREMENT_DOMAIN,
    WEB_RESEARCH_DOMAIN,
)
from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file) or from the
# backend directory, whichever exists first.
load_dotenv()

# ── Database (PostgreSQL only) ─────────────────────────────────────────────
# Set DATABASE_URL to a valid asyncpg/psycopg2 DSN before starting the server.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/agent_scope",
)

# ── API Authentication ─────────────────────────────────────────────────────
# Set FLIGHT_RECORDER_API_KEY in the environment to enable key-based auth.
# When set, all mutating (POST/DELETE) endpoints require X-API-Key header.
API_KEY = os.environ.get("FLIGHT_RECORDER_API_KEY", "")
ENABLE_AUTH = bool(API_KEY)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
if ENVIRONMENT == "production" and not API_KEY:
    raise RuntimeError("SECURITY ERROR: FLIGHT_RECORDER_API_KEY must be set in production.")

# ── LLM Judge provider configuration ─────────────────────────────────────
# Set one of these keys to enable real-LLM evaluation.
# If neither key is set, the system falls back to the rule-based judge.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model overrides (optional — sensible defaults are used when not set)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

# ── LLM Judge – Ollama configuration ───────────────────────────────────────
LLM_PROVIDER    = os.environ.get("LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "mistral")

# LLM_JUDGE_PROVIDER: auto-detected.  "ollama" | "openai" | "anthropic" | "none"
def get_llm_provider() -> str:
    if LLM_PROVIDER.lower() == "ollama": return "ollama"
    if OPENAI_API_KEY:    return "openai"
    if ANTHROPIC_API_KEY: return "anthropic"
    return "none"


# ── Analysis thresholds ────────────────────────────────────────────────────
MAX_TOOL_CALLS = 15  # exceeded → EXCESSIVE_STEPS anomaly
REASONING_LOOP_THRESHOLD = 3  # same tool failing N times → REASONING_LOOP
MAX_STEP_DURATION_MS = 10_000  # ms → ABNORMAL_LATENCY
Z_SCORE_THRESHOLD = 2.5  # standard deviations → STATISTICAL_OUTLIER

# ── Domain configurations ──────────────────────────────────────────────────
# Key: domain_id, Value: dict with optimal_path, required_params, unauthorized_tools
# The evaluator picks the domain that best matches the trace's scenario.

DOMAINS: Dict[str, Dict[str, Any]] = {
    "flight_booking": {
        "name": "Flight Booking",
        "description": "Book flights with pricing and payment processing",
        "scenarios": {
            "normal",
            "tool_error",
            "param_error",
            "reasoning_loop",
            "hallucination",
            "idpi",
            "schema_poison",
            "schema_poisoning",
            "memory_poison",
            "prompt_injection",
            "partial_completion",
            "goal_hijacking",
            "jailbreak",
            "context_overflow",
        },
        "optimal_path": [
            "flight_search_api",
            "price_comparison_tool",
            "booking_api",
            "payment_api",
            "email_api",
        ],
        "required_params": {
            "flight_search_api": ["origin", "destination", "date", "passengers"],
            "price_comparison_tool": ["flight_ids"],
            "booking_api": [
                "flight_id",
                "passenger_name",
                "passenger_email",
                "payment_token",
            ],
            "payment_api": ["booking_id", "amount", "payment_method"],
            "email_api": ["to", "subject", "body"],
        },
        "authorized_tools": {
            "flight_search_api",
            "price_comparison_tool",
            "booking_api",
            "payment_api",
            "email_api",
        },
        "unauthorized_tools": {"web_search", "document_retriever"},
        "thresholds": {
            "max_tool_calls": 15,
            "max_reasoning_loops": 3,
            "acceptable_error_rate": 0.1,
            "min_tool_selection_accuracy": 0.85,
        },
    },
    "customer_support": CUSTOMER_SUPPORT_DOMAIN,
    "code_review": CODE_REVIEW_DOMAIN,
    "operations_triage": OPERATIONS_TRIAGE_DOMAIN,
    "data_analysis": DATA_ANALYSIS_DOMAIN,
    "web_research": WEB_RESEARCH_DOMAIN,
    "procurement": PROCUREMENT_DOMAIN,
    "generic": {
        "name": "Generic",
        "description": "Generic task with no predefined constraints",
        "scenarios": {
            "normal",
            "tool_error",
            "param_error",
            "reasoning_loop",
            "hallucination",
        },
        "optimal_path": [],
        "required_params": {},
        "authorized_tools": set(),
        "unauthorized_tools": set(),
        "thresholds": {
            "max_tool_calls": 20,
            "max_reasoning_loops": 5,
            "acceptable_error_rate": 0.2,
            "min_tool_selection_accuracy": 0.7,
        },
    },
}

DEFAULT_DOMAIN = "generic"

# ── Email / SMTP ──────────────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASS: str = os.getenv("SMTP_PASS", "")


def get_domain(scenario: str) -> Dict[str, Any]:
    """Return the domain config whose scenarios set contains the given scenario.

    Args:
        scenario: Scenario name (e.g., "hallucination", "prompt_injection")

    Returns:
        Domain configuration dict matching the scenario
    """
    if scenario in DOMAINS:
        return DOMAINS[scenario]
    for d in DOMAINS.values():
        if scenario in d.get("scenarios", set()):
            return d
    return DOMAINS["generic"]


def get_all_domains() -> Dict[str, Dict[str, Any]]:
    """Return all registered domains."""
    return DOMAINS


def get_domain_names() -> List[str]:
    """Return sorted list of all domain names."""
    return sorted(list(DOMAINS.keys()))


def register_domain(domain_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Register or replace a domain definition at runtime."""
    normalized = {
        "name": config.get("name", domain_name.replace("_", " ").title()),
        "scenarios": set(config.get("scenarios") or {domain_name}),
        "optimal_path": list(config.get("optimal_path") or []),
        "required_params": dict(config.get("required_params") or {}),
        "allowed_tools": set(config.get("allowed_tools") or []),
        "unauthorized_tools": set(config.get("unauthorized_tools") or []),
        "thresholds": dict(config.get("thresholds") or {}),
    }
    DOMAINS[domain_name] = normalized
    return normalized


def serialize_domain(domain_name: str, domain: Dict[str, Any]) -> Dict[str, Any]:
    """Convert in-memory domain config to JSON-safe shape for API/storage."""
    return {
        "domain_name": domain_name,
        "name": domain.get("name", domain_name),
        "scenarios": sorted(list(domain.get("scenarios") or [])),
        "optimal_path": list(domain.get("optimal_path") or []),
        "required_params": dict(domain.get("required_params") or {}),
        "allowed_tools": sorted(list(domain.get("allowed_tools") or [])),
        "unauthorized_tools": sorted(list(domain.get("unauthorized_tools") or [])),
        "thresholds": dict(domain.get("thresholds") or {}),
    }
