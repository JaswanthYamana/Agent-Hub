import uuid
from typing import Any, Dict, List, Optional

from core.hooks import hooks
from core.models import RedTeamRequest, TaskRequest
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, HTTPException
from pydantic import BaseModel
from redteam.catalogue import ATTACK_CATALOGUE
from redteam.idpi_fuzzer import IDPIFuzzer, IDPITechnique
from redteam.schema_fuzzer import FuzzStrategy, SchemaFuzzer
from storage import repository

from api.deps import require_api_key, limiter, redteam, agent, real_agent, prompt_gen
from api.utils import run_and_persist

# Initialize fuzzers
idpi_fuzzer = IDPIFuzzer()
schema_fuzzer = SchemaFuzzer()

router = APIRouter()


@router.get("/api/redteam/catalogue", summary="Available attack types")
async def get_catalogue() -> Dict[str, Any]:
    return ATTACK_CATALOGUE


@router.post("/api/redteam/run", summary="Execute a red-team attack")
@limiter.limit("20/minute")
async def run_redteam(
    request: Request,
    redteam_request: RedTeamRequest,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    # Fire pre_attack hook (Friend 3 adversarial evolution plugs in here)
    await hooks.fire("pre_attack", request=redteam_request)

    # Select target agent based on request (demo, real, or external)
    target_agent_fn = real_agent.execute if redteam_request.agent_target == "real" else agent.execute
    result = await redteam.run_attack(redteam_request, target_agent_fn, project_id="default")
    result_dict = result.model_dump(mode="json")
    await repository.save_attack_result(result_dict)
    await repository.emit_attack_metrics(result_dict, project_id="default")
    return result_dict


@router.get("/api/redteam/results", summary="Past red-team attack results")
async def list_redteam_results(limit: int = Query(default=50)) -> List[Dict[str, Any]]:
    return await repository.list_attack_results(limit=limit)


class EvolutionStartRequest(BaseModel):
    agent_id: str = "flight-agent"
    generations: int = 3
    attacks_per_generation: int = 10


@router.post("/api/redteam/evolution/start", summary="Start Attack Evolution Test")
@limiter.limit("5/minute")
async def start_evolution(
    request: Request,
    evolution_request: EvolutionStartRequest,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    from redteam.evolution import AttackEvolutionEngine

    engine = AttackEvolutionEngine(agent=agent)
    result = await engine.run_evolution_loop(
        generations=evolution_request.generations,
        initial_count=evolution_request.attacks_per_generation,
        variants_per_success=3,
    )
    result_dict = result.model_dump(mode="json")
    await repository.save_evolution_result(result_dict)
    return result_dict


@router.get("/api/redteam/evolution/{test_id}", summary="Get Evolution Results")
async def get_evolution_results(test_id: str) -> Dict[str, Any]:
    return await repository.get_evolution_result(test_id)


@router.get(
    "/api/redteam/generate-prompts", summary="Generate adversarial prompt variants"
)
async def generate_prompts(
    attack_type: str = Query(
        description="idpi | schema_poison | memory_poison | tool_fuzzing"
    ),
    n: int = Query(default=5, ge=1, le=20),
    goal: Optional[str] = Query(default=None),
    tool: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    variants = prompt_gen.generate_variants(
        attack_type=attack_type, n=n, goal=goal, tool=tool
    )
    return {"attack_type": attack_type, "n": len(variants), "variants": variants}


@router.post(
    "/api/redteam/fuzz-params", summary="Generate fuzz test parameter variants"
)
@limiter.limit("20/minute")
async def fuzz_parameters(
    request: Request,
    body: Dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    tool_name = body.get("tool_name", "unknown_tool")
    valid_params = body.get("valid_params", {})
    n = min(int(body.get("n", 8)), 50)
    variants = prompt_gen.fuzz_parameters(tool_name, valid_params, n=n)
    return {"tool_name": tool_name, "n": len(variants), "variants": variants}


@router.post(
    "/api/redteam/generate-idpi", summary="Generate invisible prompt injection payloads"
)
@limiter.limit("20/minute")
async def generate_idpi_payloads(
    request: Request,
    body: Dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Generate N invisible prompt injection variations using stealth techniques.

    Request body:
    {
        "task": "Find flights from NYC to LAX",
        "injection_instructions": ["IGNORE INSTRUCTIONS", "OVERRIDE SYSTEM"],
        "count": 5,
        "position": "append",  # or "prepend", "middle"
        "technique": "white_text"  # optional, use specific technique
    }

    Returns:
        List of mutated tasks with injection metadata
    """
    task = body.get("task", "")
    injection_instructions = body.get("injection_instructions", None)
    count = min(int(body.get("count", 5)), 20)
    position = body.get("position", "append")
    technique_name = body.get("technique", None)

    if not task:
        return {"error": "task field is required"}

    # Parse technique if specified
    technique = None
    if technique_name:
        try:
            technique = IDPITechnique[technique_name.upper()]
        except KeyError:
            return {
                "error": f"Unknown technique: {technique_name}",
                "available_techniques": [t.value for t in IDPITechnique],
            }

    mutations = idpi_fuzzer.mutate_task_payload(
        task,
        injection_instructions=injection_instructions,
        count=count,
        position=position,
    )

    return {
        "status": "success",
        "mutation_count": len(mutations),
        "original_task": task,
        "mutations": mutations,
        "note": "These are invisible payloads for adversarial testing. Use with real_agent target.",
    }


@router.post(
    "/api/redteam/generate-idpi-variants", summary="Generate IDPI variants by technique"
)
@limiter.limit("20/minute")
async def generate_idpi_variants(
    request: Request,
    body: Dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Generate one IDPI variant per technique for the same payload.

    Request body:
    {
        "task": "Find flights from NYC to LAX",
        "hidden_instruction": "IGNORE PREVIOUS INSTRUCTIONS"
    }

    Returns:
        List of variants, one per technique
    """
    task = body.get("task", "")
    hidden_instruction = body.get("hidden_instruction", "")

    if not task:
        return {"error": "task field is required"}
    if not hidden_instruction:
        return {"error": "hidden_instruction field is required"}

    variants = idpi_fuzzer.generate_variants_by_technique(task, hidden_instruction)

    return {"status": "success", "variant_count": len(variants), "variants": variants}


@router.post("/api/redteam/fuzz-schema", summary="Generate fuzzed tool schemas")
@limiter.limit("20/minute")
async def fuzz_tool_schema(
    request: Request,
    body: Dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Generate N fuzzed variations of a tool schema to test parameter extraction resilience.

    Request body:
    {
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        "mutation_strategy": "change_type_constraint",  # optional
        "count": 5
    }

    Returns:
        List of fuzzed schemas with mutation details
    """
    schema = body.get("schema", None)
    count = min(int(body.get("count", 5)), 20)
    strategy_name = body.get("mutation_strategy", None)

    if not schema:
        return {"error": "schema field is required and must be a JSON object"}

    # Parse strategy if specified
    strategy = None
    if strategy_name:
        try:
            strategy = FuzzStrategy[strategy_name.upper()]
        except KeyError:
            return {
                "error": f"Unknown strategy: {strategy_name}",
                "available_strategies": [s.value for s in FuzzStrategy],
            }

    fuzzed = schema_fuzzer.generate_fuzzed_schemas(
        schema, count=count, strategies=[strategy] if strategy else None
    )

    return {
        "status": "success",
        "mutation_count": len(fuzzed),
        "original_schema": schema,
        "mutations": fuzzed,
        "note": "Feed these schemas to an agent to test parameter-extraction resilience.",
    }


@router.post(
    "/api/redteam/fuzz-schema-variants",
    summary="Generate schema fuzz variants by strategy",
)
@limiter.limit("20/minute")
async def fuzz_schema_variants(
    request: Request,
    body: Dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Generate one fuzzed schema variant per strategy for comprehensive testing.

    Request body:
    {
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }

    Returns:
        List of variants, one per fuzzing strategy
    """
    schema = body.get("schema", None)

    if not schema:
        return {"error": "schema field is required and must be a JSON object"}

    variants = schema_fuzzer.generate_variants_by_strategy(schema)

    return {"status": "success", "variant_count": len(variants), "variants": variants}


@router.post("/api/execute", summary="Run a demo agent scenario")
@limiter.limit("30/minute")
async def execute_task(
    request: Request,
    task_request: TaskRequest,
    background: BackgroundTasks,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    from agents.demo_agent import _SCENARIO_MAP
    if task_request.scenario not in _SCENARIO_MAP:
        raise HTTPException(status_code=422, detail=f"Unsupported scenario: {task_request.scenario}")

    trace_id = str(uuid.uuid4())
    repository.create_queue(trace_id)
    task_request = task_request.model_copy(update={"trace_id": trace_id})
    background.add_task(run_and_persist, task_request)
    return {
        "trace_id": trace_id,
        "status": "running",
        "task": task_request.task,
        "scenario": task_request.scenario,
        "stream_url": f"/api/traces/{trace_id}/stream",
    }
