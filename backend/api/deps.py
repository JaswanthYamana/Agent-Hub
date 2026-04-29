from typing import Optional
from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from agents.demo_agent import DemoAgent
from agents.real_agent import RealAgent
from anomaly.detector import AnomalyDetector
from evaluation.metrics import MetricsEngine
from redteam.engine import RedTeamEngine
from graph.builder import GraphBuilder
from redteam.prompt_generator import AdversarialPromptGenerator
from core.config import ENABLE_AUTH, API_KEY

limiter = Limiter(key_func=get_remote_address)

agent = DemoAgent()
real_agent = RealAgent()
metrics = MetricsEngine()
detector = AnomalyDetector()
redteam = RedTeamEngine()
graph = GraphBuilder()
prompt_gen = AdversarialPromptGenerator(seed=42)

async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    Optional API key guard — only active when FLIGHT_RECORDER_API_KEY env var is set.
    Applied to all mutating endpoints (POST/DELETE).  GET endpoints are always public.
    """
    import core.config
    if core.config.ENABLE_AUTH and x_api_key != core.config.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-API-Key header.",
        )
