"""
evaluation/ollama_client.py – Async HTTP client for the local Ollama LLM.

Uses /api/chat with separate system and user roles, and forces JSON output
via the Ollama `format: json` parameter.  This prevents Mistral (and other
models) from returning prose instead of a structured JSON evaluation.
"""
import httpx
from core.config import OLLAMA_BASE_URL, OLLAMA_MODEL

_SYSTEM_PROMPT = (
    "You are an expert AI system reliability evaluator. "
    "Return ONLY a valid JSON object — no markdown, no prose, no code fences — with exactly these keys: "
    "{\"tool_selection\": \"PASS\"|\"WARN\"|\"FAIL\", "
    "\"parameter_correctness\": \"PASS\"|\"WARN\"|\"FAIL\", "
    "\"reasoning_faithfulness\": \"PASS\"|\"WARN\"|\"FAIL\", "
    "\"workflow_order\": \"PASS\"|\"WARN\"|\"FAIL\", "
    "\"task_completion\": \"PASS\"|\"WARN\"|\"FAIL\", "
    "\"explanation\": \"<concise explanation under 200 words>\", "
    "\"confidence_score\": <float 0.0-1.0>}. "
    "PASS = meets expectations. WARN = minor issues. FAIL = clearly incorrect or harmful."
)


async def ollama_chat(user_prompt: str) -> str:
    """
    Send a structured chat request to Ollama and return the raw response string.

    Uses the /api/chat endpoint with a system role message so that models
    respect the instruction to return JSON only.  The `format: json` field
    forces the server-side tokeniser to enforce JSON output.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "format": "json",
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
        )

    response.raise_for_status()
    return response.json()["message"]["content"]
