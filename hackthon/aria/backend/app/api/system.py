from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.core import db
from app.core.config import get_settings
from app.simulator import catalog

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "openai_configured": settings.has_api_key,
        "models": {
            "live": settings.live_model,
            "agent": settings.agent_model,
            "fast": settings.fast_model,
            "judge": settings.judge_model,
            "embedding": settings.embedding_model,
        },
        "machine": catalog.machine_info(),
    }


@router.get("/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return [catalog.public_scenario(s) for s in catalog.scenarios()]


@router.get("/reports/{report_id}", response_class=PlainTextResponse)
def report(report_id: str) -> str:
    row = db.query_one("SELECT path FROM reports WHERE id = ?", (report_id,))
    if row is None:
        raise HTTPException(404, "Unknown report")
    with open(row["path"], encoding="utf-8") as handle:
        return handle.read().split("<!-- aria-report")[0]
