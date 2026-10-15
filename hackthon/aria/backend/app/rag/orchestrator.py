import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import structured
from app.memory import temporal_store
from app.rag import retriever

ProgressFn = Callable[[str, dict[str, Any]], Awaitable[None]]

PLAN_PROMPT = """You plan retrieval for an industrial maintenance assistant.
Split the question into 1-4 focused sub-queries. Each targets one source:
- manuals: equipment manuals and procedures (specifications, alarm meanings, step-by-step procedures, safety rules)
- incident_history: past incidents with timelines, root causes and repairs
Write each query as a short keyword-rich search string. Do not answer the question."""

RETRY_PROMPT = """A retrieval sub-query returned nothing useful. Rewrite it once with different terminology, synonyms,
component tags or a broader scope so the same information can be found. Return only the new query."""


class SubQuery(BaseModel):
    target: Literal["manuals", "incident_history"]
    query: str
    purpose: str


class RetrievalPlan(BaseModel):
    sub_queries: list[SubQuery] = Field(max_length=4)


class RewrittenQuery(BaseModel):
    query: str


async def _run(target: str, query: str, history_only: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if target == "manuals":
        result = await retriever.search(query, top_k=3)
        return result["hits"], result["retrieval"]
    result = await temporal_store.search_incidents(query, limit=3, history_only=history_only)
    hits = [
        {k: v for k, v in incident.items() if k != "timeline"} | {"timeline_events": len(incident["timeline"])}
        for incident in result["incidents"]
        if incident["relevance"] > 0.025
    ]
    return hits, result["retrieval"] | {"facts": result["facts"]}


async def research(question: str, progress: ProgressFn | None = None, history_only: bool = False) -> dict[str, Any]:
    settings = get_settings()

    async def emit(stage: str, data: dict[str, Any]) -> None:
        if progress:
            await progress(stage, data)

    plan, _ = await structured(
        model=settings.fast_model,
        instructions=PLAN_PROMPT,
        input_text=question,
        schema=RetrievalPlan,
    )
    steps = [
        {"step": i + 1, "target": sq.target, "query": sq.query, "purpose": sq.purpose, "status": "running"}
        for i, sq in enumerate(plan.sub_queries)
    ]
    await emit("plan", {"question": question, "steps": steps})

    async def execute(step: dict[str, Any]) -> dict[str, Any]:
        hits, meta = await _run(step["target"], step["query"], history_only)
        step.update(hits=hits, retrieval=meta, status="success" if hits else "empty")
        await emit("step", step)
        return step

    await asyncio.gather(*(execute(step) for step in steps))

    for step in [s for s in steps if s["status"] == "empty"]:
        rewritten, _ = await structured(
            model=settings.fast_model,
            instructions=RETRY_PROMPT,
            input_text=f"Original question: {question}\nTarget: {step['target']}\nFailed query: {step['query']}",
            schema=RewrittenQuery,
        )
        retry = {
            "step": len(steps) + 1,
            "target": step["target"],
            "query": rewritten.query,
            "purpose": f"Orchestrator retry of step {step['step']}",
            "retry_of": step["step"],
            "status": "running",
        }
        await emit("retry", retry)
        steps.append(await execute(retry))

    evidence = [
        {"step": s["step"], "target": s["target"], **hit} for s in steps if s["status"] == "success" for hit in s["hits"]
    ]
    facts = [f for s in steps if s["target"] == "incident_history" for f in s.get("retrieval", {}).get("facts", [])]
    return {
        "question": question,
        "steps": [{k: v for k, v in s.items() if k not in {"hits"}} | {"hit_count": len(s.get("hits", []))} for s in steps],
        "evidence": evidence,
        "facts": facts,
    }
