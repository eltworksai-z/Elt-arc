import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core import db
from app.core.config import get_settings
from app.core.llm import embed, structured
from app.core.timeutil import new_id, utc_now_iso
from app.rag.vectors import to_blob

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]]

EXTRACTION_PROMPT = """You extract temporally-aware facts from industrial maintenance records.

For the episode you receive, return atomic statements about equipment, components, configuration, procedures and outcomes.

Temporal classification:
- atemporal: always true regardless of time (physics, fixed specifications such as "B21 switching distance is 2.0 mm").
- static: became true at a point in time and does not change afterwards (an event: "valve Y4 was replaced").
- dynamic: a state that is true for a period and can later change ("B21 is mounted on the slotted bracket", "B12 is a WL12G-IOL").

Temporal event extraction:
- valid_at: ISO-8601 timestamp when the statement became true. Resolve relative references ("this morning", "after the work") against the episode base date. Use null for atemporal statements.
- invalid_at: ISO-8601 timestamp when it stopped being true if the episode says so, else null.

Use canonical subjects (e.g. "PAL-01 sensor B21", "PAL-01 photo-eye B12", "PAL-01 light curtain LC2", "plant air header") so facts about the same thing can be compared. Predicates are short snake_case verbs (mounted_on, model_is, failed_due_to, recommended_action, threshold_is). Do not invent facts that are not in the text."""

CONTRADICTION_PROMPT = """You check temporal validity in a maintenance knowledge graph.
Decide whether the NEW statement means the EXISTING statement is no longer true from the new statement's valid time onward.
Only answer true when both describe the same subject and property and cannot both hold at the same time."""


class ExtractedStatement(BaseModel):
    statement: str
    subject: str
    predicate: str
    object: str
    temporal_type: Literal["atemporal", "static", "dynamic"]
    statement_type: Literal["fact", "opinion", "prediction"]
    valid_at: str | None
    invalid_at: str | None


class Extraction(BaseModel):
    statements: list[ExtractedStatement] = Field(description="Atomic statements found in the episode")


class ContradictionVerdict(BaseModel):
    invalidates_existing: bool
    reason: str


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").split())


async def extract_statements(episode: str, base_date: str) -> list[ExtractedStatement]:
    settings = get_settings()
    result, _ = await structured(
        model=settings.fast_model,
        instructions=EXTRACTION_PROMPT,
        input_text=f"Episode base date: {base_date}\n\nEpisode:\n{episode}",
        schema=Extraction,
    )
    return result.statements


async def _check_invalidation(new: dict[str, Any], existing: dict[str, Any]) -> ContradictionVerdict:
    settings = get_settings()
    verdict, _ = await structured(
        model=settings.fast_model,
        instructions=CONTRADICTION_PROMPT,
        input_text=(
            f"EXISTING (valid from {existing['t_valid']}): {existing['statement']}\n"
            f"NEW (valid from {new['t_valid']}): {new['statement']}"
        ),
        schema=ContradictionVerdict,
    )
    return verdict


async def _apply_validity(new: dict[str, Any], progress: ProgressFn | None) -> None:
    if new["temporal_type"] != "dynamic":
        return
    candidates = [
        row
        for row in db.query(
            "SELECT * FROM statements WHERE temporal_type = 'dynamic' AND t_invalid IS NULL AND id != ?", (new["id"],)
        )
        if _normalize(row["subject"]) == _normalize(new["subject"])
        and _normalize(row["predicate"]) == _normalize(new["predicate"])
        and (row["t_valid"] or "") <= (new["t_valid"] or "")
    ]
    for existing in candidates:
        verdict = await _check_invalidation(new, existing)
        if verdict.invalidates_existing:
            db.execute(
                "UPDATE statements SET t_invalid = ?, t_expired = ?, invalidated_by = ? WHERE id = ?",
                (new["t_valid"], utc_now_iso(), new["id"], existing["id"]),
            )
            if progress:
                await progress(
                    {
                        "stage": "invalidated",
                        "old": existing["statement"],
                        "new": new["statement"],
                        "reason": verdict.reason,
                    }
                )


async def ingest_episode(
    source_id: str,
    machine_id: str | None,
    episode: str,
    base_date: str,
    progress: ProgressFn | None = None,
    extracted: list[ExtractedStatement] | None = None,
) -> list[dict[str, Any]]:
    statements = extracted if extracted is not None else await extract_statements(episode, base_date)
    vectors = await embed([s.statement for s in statements]) if statements else []
    stored = []
    for item, vector in zip(statements, vectors, strict=True):
        record = {
            "id": new_id("fact"),
            "source_id": source_id,
            "machine_id": machine_id,
            "subject": item.subject,
            "predicate": item.predicate,
            "object": item.object,
            "statement": item.statement,
            "temporal_type": item.temporal_type,
            "statement_type": item.statement_type,
            "t_created": utc_now_iso(),
            "t_valid": item.valid_at or (base_date if item.temporal_type != "atemporal" else None),
            "t_invalid": item.invalid_at,
        }
        db.execute(
            """INSERT INTO statements (id, source_id, machine_id, subject, predicate, object, statement, temporal_type,
               statement_type, t_created, t_valid, t_invalid, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*record.values(), to_blob(vector)),
        )
        await _apply_validity(record, progress)
        stored.append(record)
    if progress:
        await progress({"stage": "episode_done", "source_id": source_id, "statements": len(stored)})
    return stored


async def build_from_history(progress: ProgressFn | None = None) -> dict[str, Any]:
    """Runs the temporal pipeline over every simulated history incident not yet ingested, oldest first."""
    pending = db.query(
        """SELECT * FROM incidents WHERE source = 'history_simulated'
           AND id NOT IN (SELECT DISTINCT source_id FROM statements) ORDER BY opened_at"""
    )
    if progress:
        await progress({"stage": "started", "episodes": len(pending)})
    semaphore = asyncio.Semaphore(4)

    async def extract(row: dict[str, Any]) -> list[ExtractedStatement]:
        async with semaphore:
            result = await extract_statements(row["summary"], row["opened_at"])
            if progress:
                await progress({"stage": "extracted", "source_id": row["id"], "statements": len(result)})
            return result

    extracted = await asyncio.gather(*(extract(row) for row in pending))
    total = 0
    for row, statements in zip(pending, extracted, strict=True):
        stored = await ingest_episode(row["id"], row["machine_id"], row["summary"], row["opened_at"], progress, statements)
        total += len(stored)
    await embed_incidents()
    return {"episodes": len(pending), "statements": total}


async def embed_incidents() -> int:
    rows = db.query("SELECT id, title, summary, root_cause, component, alarm_code FROM incidents WHERE embedding IS NULL AND status != 'investigating'")
    if not rows:
        return 0
    texts = [" ".join(str(r.get(k) or "") for k in ("title", "summary", "root_cause", "component", "alarm_code")) for r in rows]
    vectors = await embed(texts)
    with db.transaction() as conn:
        for row, vector in zip(rows, vectors, strict=True):
            conn.execute("UPDATE incidents SET embedding = ? WHERE id = ?", (to_blob(vector), row["id"]))
    return len(rows)
