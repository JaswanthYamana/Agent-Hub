from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.config import DOMAINS, register_domain, serialize_domain
from storage import repository
from api.deps import require_api_key

router = APIRouter()

class DomainConfigRequest(BaseModel):
    domain_name: str
    optimal_path: List[str] = Field(default_factory=list)
    required_params: Dict[str, List[str]] = Field(default_factory=dict)
    allowed_tools: List[str] = Field(default_factory=list)
    thresholds: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/domains", summary="Create or update a runtime domain configuration")
async def upsert_domain(
    request: DomainConfigRequest,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    config = {
        "name": request.domain_name.replace("_", " ").title(),
        "scenarios": [request.domain_name],
        "optimal_path": request.optimal_path,
        "required_params": request.required_params,
        "allowed_tools": request.allowed_tools,
        "thresholds": request.thresholds,
    }
    normalized = register_domain(request.domain_name, config)
    await repository.save_domain(request.domain_name, serialize_domain(request.domain_name, normalized))
    return {"status": "ok", "domain": serialize_domain(request.domain_name, normalized)}


@router.get("/api/domains", summary="List available domain configurations")
async def list_domains() -> Dict[str, Any]:
    return {
        "domains": [serialize_domain(name, cfg) for name, cfg in DOMAINS.items()]
    }
