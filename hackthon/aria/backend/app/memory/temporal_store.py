import json
import math
from datetime import timedelta
from typing import Any

from app.core import db
from app.core.config import get_settings
from app.core.llm import embed
from app.core.timeutil import parse_iso, utc_now, utc_now_iso
from app.rag.lexical import BM25, reciprocal_rank_fusion
from app.rag.vectors import cosine_scores, from_blob

HISTORY_SOURCE = "history_simulated"


def seed_history_if_empty() -> int:
    if db.query_one("SELECT COUNT(*) AS n FROM incidents WHERE source = ?", (HISTORY_SOURCE,))["n"]:
        return 0
    path = get_settings().data_dir / "incident_history.json"
    history = json.loads(path.read_text(encoding="utf-8-sig"))
    now = utc_now()
    with db.transaction() as conn:
        for incident in history["incidents"]:
            opened = now + timedelta(days=incident["offset_days"])
            events = sorted(incident["events"], key=lambda e: e["t_min"])
            closed = opened + timedelta(minutes=events[-1]["t_min"])
            conn.execute(
                """INSERT INTO incidents (id, machine_id, title, summary, root_cause, component, alarm_code,
                   status, opened_at, closed_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'resolved', ?, ?, ?)""",
                (
                    incident["id"],
                    incident["machine_id"],
                    incident["title"],
                    incident["narrative"],
                    incident["root_cause"],
                    incident["component"],
                    incident["alarm_code"],
                    opened.isoformat(),
                    closed.isoformat(),
                    HISTORY_SOURCE,
                ),
            )
            for event in events:
                conn.execute(
                    """INSERT INTO events (incident_id, machine_id, ts, event_type, component, signal, value,
                       technician_action, outcome, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        incident["id"],
                        incident["machine_id"],
                        (opened + timedelta(minutes=event["t_min"])).isoformat(),
                        event["event_type"],
                        event.get("component"),
                        event.get("signal"),
                        event.get("value"),
                        event.get("technician_action"),
                        event.get("outcome"),
                        HISTORY_SOURCE,
                    ),
                )
    return len(history["incidents"])


def open_incident(incident_id: str, machine_id: str, title: str, alarm_code: str | None, summary: str) -> None:
    db.execute(
        """INSERT OR IGNORE INTO incidents (id, machine_id, title, summary, alarm_code, status, opened_at, source)
           VALUES (?, ?, ?, ?, ?, 'investigating', ?, 'aria')""",
        (incident_id, machine_id, title, summary, alarm_code, utc_now_iso()),
    )


def add_event(
    incident_id: str,
    machine_id: str,
    event_type: str,
    *,
    component: str | None = None,
    signal: str | None = None,
    value: str | None = None,
    technician_action: str | None = None,
    outcome: str | None = None,
    ts: str | None = None,
) -> None:
    db.execute(
        """INSERT INTO events (incident_id, machine_id, ts, event_type, component, signal, value,
           technician_action, outcome, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aria')""",
        (incident_id, machine_id, ts or utc_now_iso(), event_type, component, signal, value, technician_action, outcome),
    )


def close_incident(incident_id: str, *, status: str, root_cause: str | None, component: str | None, alarm_code: str | None) -> None:
    db.execute(
        """UPDATE incidents SET status = ?, root_cause = ?, component = COALESCE(?, component),
           alarm_code = COALESCE(?, alarm_code), closed_at = ? WHERE id = ?""",
        (status, root_cause, component, alarm_code, utc_now_iso(), incident_id),
    )


def incident_timeline(incident_id: str) -> list[dict[str, Any]]:
    return db.query(
        """SELECT ts, event_type, component, signal, value, technician_action, outcome
           FROM events WHERE incident_id = ? ORDER BY ts""",
        (incident_id,),
    )


def _incident_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title", "summary", "root_cause", "component", "alarm_code"))


async def search_incidents(
    query: str,
    *,
    component: str | None = None,
    alarm_code: str | None = None,
    exclude_incident: str | None = None,
    limit: int = 4,
    history_only: bool = False,
) -> dict[str, Any]:
    rows = db.query(
        "SELECT * FROM incidents WHERE status != 'investigating' AND id != ? AND (? = 0 OR source = ?) ORDER BY opened_at DESC",
        (exclude_incident or "", int(history_only), HISTORY_SOURCE),
    )
    if not rows:
        return {"incidents": [], "facts": [], "retrieval": {"mode": "empty"}}
    texts = [_incident_text(r) for r in rows]
    lexical = BM25(texts).scores(f"{query} {component or ''} {alarm_code or ''}")
    rankings = [sorted(range(len(rows)), key=lambda i: -lexical[i])]
    mode = "lexical"
    vectors = [from_blob(r["embedding"]) for r in rows]
    if get_settings().has_api_key and all(v is not None for v in vectors):
        query_vec = (await embed([query]))[0]
        dense = cosine_scores(query_vec, vectors)
        rankings.append(sorted(range(len(rows)), key=lambda i: -dense[i]))
        mode = "hybrid"
    fused = reciprocal_rank_fusion(rankings)
    now = utc_now()
    scored = []
    for index, base in fused.items():
        row = rows[index]
        reasons = []
        score = base
        if alarm_code and row["alarm_code"] == alarm_code:
            score += 0.02
            reasons.append(f"same alarm {alarm_code}")
        if component and row["component"] and (component in row["component"] or row["component"] in component):
            score += 0.015
            reasons.append(f"same component {row['component']}")
        age_days = (now - parse_iso(row["opened_at"])).days
        score += 0.01 * math.exp(-age_days / 180)
        if lexical[index] > 0:
            reasons.append("text match on symptoms/root cause")
        scored.append((score, index, reasons, age_days))
    scored.sort(reverse=True)
    incidents = []
    for score, index, reasons, age_days in scored[:limit]:
        row = rows[index]
        incidents.append(
            {
                "incident_id": row["id"],
                "machine_id": row["machine_id"],
                "title": row["title"],
                "opened_at": row["opened_at"],
                "age_days": age_days,
                "alarm_code": row["alarm_code"],
                "component": row["component"],
                "root_cause": row["root_cause"],
                "relevance": round(score, 4),
                "similarity_reasons": reasons or ["semantic similarity"],
                "timeline": incident_timeline(row["id"]),
                "simulated_history": row["source"] == HISTORY_SOURCE,
            }
        )
    facts = related_facts(query, [i["incident_id"] for i in incidents])
    return {
        "incidents": incidents,
        "facts": facts,
        "retrieval": {"mode": mode, "candidates": len(rows)},
        "caveat": "Historical similarity is supporting context only; current machine evidence must confirm the cause.",
    }


def related_facts(query: str, incident_ids: list[str], limit: int = 8) -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM statements")
    if not rows:
        return []
    lexical = BM25([r["statement"] for r in rows]).scores(query)
    ranked = sorted(
        range(len(rows)),
        key=lambda i: (rows[i]["source_id"] in incident_ids, lexical[i]),
        reverse=True,
    )
    return [_fact_view(rows[i]) for i in ranked[:limit] if lexical[i] > 0 or rows[i]["source_id"] in incident_ids]


def _fact_view(row: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()
    invalid = row["t_invalid"]
    return {
        "fact_id": row["id"],
        "statement": row["statement"],
        "temporal_type": row["temporal_type"],
        "valid_from": row["t_valid"],
        "valid_until": invalid,
        "currently_valid": invalid is None or invalid > now,
        "invalidated_by": row["invalidated_by"],
        "source": row["source_id"],
    }


def knowledge_overview() -> dict[str, Any]:
    incidents = db.query(
        "SELECT id, machine_id, title, alarm_code, component, status, opened_at, source FROM incidents ORDER BY opened_at DESC"
    )
    statements = db.query("SELECT * FROM statements ORDER BY t_valid DESC")
    return {
        "incidents": incidents,
        "statements": [_fact_view(s) | {"subject": s["subject"], "predicate": s["predicate"], "object": s["object"]} for s in statements],
        "counts": {
            "incidents": len(incidents),
            "events": db.query_one("SELECT COUNT(*) AS n FROM events")["n"],
            "statements": len(statements),
            "invalidated": sum(1 for s in statements if s["t_invalid"]),
            "embedded_incidents": db.query_one("SELECT COUNT(*) AS n FROM incidents WHERE embedding IS NOT NULL")["n"],
        },
    }
