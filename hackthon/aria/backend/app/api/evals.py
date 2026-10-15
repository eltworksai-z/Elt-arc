import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.streaming import sse_response
from app.core import db
from app.core.config import get_settings
from app.evals import harness
from app.simulator import catalog

router = APIRouter(prefix="/api/evals", tags=["evals"])


class RunIn(BaseModel):
    case_ids: list[str] = Field(min_length=1)
    modes: list[Literal["improved", "baseline"]] = ["baseline", "improved"]
    channel: Literal["text", "voice"] = "text"
    concurrency: int = Field(default=2, ge=1, le=6)


@router.get("/cases")
def cases() -> list[dict[str, Any]]:
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "scenario": catalog.public_scenario(catalog.scenario(c["scenario_id"])),
            "opening": c["caller"]["opening"],
            "persona": c["caller"]["persona"],
        }
        for c in harness.eval_cases()
    ]


@router.post("/runs")
async def start(body: RunIn) -> dict[str, str]:
    if not get_settings().has_api_key:
        raise HTTPException(400, "OPENAI_API_KEY is not set.")
    known = {c["id"] for c in harness.eval_cases()}
    unknown = [c for c in body.case_ids if c not in known]
    if unknown:
        raise HTTPException(404, f"Unknown cases: {unknown}")
    return {"run_id": harness.start_run(body.case_ids, list(body.modes), body.channel, body.concurrency)}


@router.get("/runs")
def runs() -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT 50")
    return [r | {"config": json.loads(r["config"]), "summary": json.loads(r["summary"]) if r["summary"] else None} for r in rows]


@router.get("/runs/{run_id}")
def run(run_id: str) -> dict[str, Any]:
    results = harness.load_results(run_id)
    if results is None:
        row = db.query_one("SELECT * FROM eval_runs WHERE id = ?", (run_id,))
        if row is None:
            raise HTTPException(404, "Unknown run")
        return {"run_id": run_id, "status": row["status"], "config": json.loads(row["config"]), "results": []}
    return results | {"status": "completed"}


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, request: Request, after: int = 0):
    return sse_response(run_id, request, after)


@router.get("/runs/{run_id}/audio/{file_name}")
def audio(run_id: str, file_name: str) -> FileResponse:
    path = (get_settings().eval_runs_dir / run_id / file_name).resolve()
    if path.parent != (get_settings().eval_runs_dir / run_id).resolve() or path.suffix != ".wav" or not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/wav")
