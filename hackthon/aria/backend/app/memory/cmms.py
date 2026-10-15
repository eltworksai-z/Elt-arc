import json
import random
from datetime import timedelta
from functools import lru_cache
from typing import Any

from app.core import db
from app.core.config import get_settings
from app.core.timeutil import utc_now, utc_now_iso


@lru_cache
def _plan() -> dict[str, Any]:
    path = get_settings().data_dir / "maintenance_plan.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def maintenance_status(component: str | None = None) -> dict[str, Any]:
    now = utc_now()
    tasks = []
    for task in _plan()["tasks"]:
        if component and component.lower() not in task["component"].lower() and task["component"].lower() not in component.lower():
            continue
        due_in = task["next_due_offset_days"]
        tasks.append(
            {
                "pm_id": task["id"],
                "component": task["component"],
                "task": task["task"],
                "interval": task["interval"],
                "last_done": (now + timedelta(days=task["last_done_offset_days"])).date().isoformat(),
                "next_due": (now + timedelta(days=due_in)).date().isoformat(),
                "status": "overdue" if due_in < 0 else "due_this_week" if due_in <= 7 else "scheduled",
                "counter": task["counter"],
            }
        )
    tasks.sort(key=lambda t: t["next_due"])
    return {"machine_id": "PAL-01", "source": "SIMULATED CMMS", "tasks": tasks}


def create_work_order(
    *,
    session_id: str,
    incident_id: str | None,
    title: str,
    priority: str,
    component: str,
    description: str,
    evidence: list[str],
) -> dict[str, Any]:
    work_order_id = f"WO-{random.randint(50000, 59999)}"
    record = {
        "id": work_order_id,
        "session_id": session_id,
        "incident_id": incident_id,
        "title": title,
        "priority": priority,
        "component": component,
        "description": description,
        "evidence": json.dumps(evidence),
        "status": "open",
        "created_at": utc_now_iso(),
    }
    db.execute(
        f"INSERT INTO work_orders ({', '.join(record)}) VALUES ({', '.join('?' for _ in record)})",
        tuple(record.values()),
    )
    return record | {"evidence": evidence, "system": "SIMULATED CMMS"}


def list_work_orders(session_id: str | None = None) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM work_orders WHERE (? IS NULL OR session_id = ?) ORDER BY created_at DESC",
        (session_id, session_id),
    )
    return [row | {"evidence": json.loads(row["evidence"])} for row in rows]
