import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.api.streaming import sse_response
from app.core import db
from app.core.config import get_settings
from app.core.events import hub
from app.core.llm import MissingApiKeyError
from app.memory import temporal_agent, temporal_store
from app.rag import index, orchestrator, retriever
from app.rag.loader import SUPPORTED_SUFFIXES

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
CHANNEL = "knowledge"
_jobs: set[asyncio.Task[Any]] = set()


class SearchIn(BaseModel):
    query: str
    multi_step: bool = False


def _background(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


@router.get("/documents")
def documents() -> list[dict[str, Any]]:
    return index.list_documents()


@router.post("/documents")
async def upload(file: UploadFile) -> dict[str, Any]:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or "document.pdf")
    path = get_settings().manuals_dir / name
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(400, "Upload a PDF, Markdown or text file.")
    path.write_bytes(await file.read())

    async def ingest() -> None:
        hub.publish(CHANNEL, "document.indexing", {"file": name})
        try:
            result = await index.ingest_document(path)
            hub.publish(CHANNEL, "document.indexed", result)
        except (ValueError, MissingApiKeyError) as exc:
            hub.publish(CHANNEL, "document.failed", {"file": name, "error": str(exc)})

    _background(ingest())
    return {"file": name, "status": "indexing"}


@router.delete("/documents/{doc_id}")
def remove(doc_id: str) -> dict[str, str]:
    try:
        index.delete_document(doc_id)
    except KeyError as exc:
        raise HTTPException(404, "Unknown document") from exc
    return {"status": "deleted"}


@router.post("/search")
async def search(body: SearchIn) -> dict[str, Any]:
    try:
        if body.multi_step:
            return await orchestrator.research(body.query)
        return await retriever.search(body.query)
    except MissingApiKeyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/temporal")
def temporal_overview() -> dict[str, Any]:
    return temporal_store.knowledge_overview()


@router.get("/incidents/{incident_id}")
def incident(incident_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT id, machine_id, title, summary, root_cause, component, alarm_code, status, opened_at, closed_at, source FROM incidents WHERE id = ?", (incident_id,))
    if row is None:
        raise HTTPException(404, "Unknown incident")
    facts = db.query("SELECT statement, temporal_type, t_valid, t_invalid, invalidated_by FROM statements WHERE source_id = ?", (incident_id,))
    return row | {"timeline": temporal_store.incident_timeline(incident_id), "facts": facts}


@router.post("/temporal/build")
async def build_temporal() -> dict[str, str]:
    if not get_settings().has_api_key:
        raise HTTPException(400, str(MissingApiKeyError()))

    async def run() -> None:
        async def progress(data: dict[str, Any]) -> None:
            hub.publish(CHANNEL, f"temporal.{data['stage']}", data)

        try:
            result = await temporal_agent.build_from_history(progress)
            hub.publish(CHANNEL, "temporal.completed", result)
        except Exception as exc:
            hub.publish(CHANNEL, "temporal.failed", {"error": str(exc)})

    _background(run())
    return {"status": "started"}


@router.post("/sync")
async def sync() -> dict[str, Any]:
    try:
        return {"indexed": await index.sync_manuals_folder()}
    except MissingApiKeyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/events")
def events(request: Request, after: int = 0):
    return sse_response(CHANNEL, request, after)
