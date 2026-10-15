import asyncio
import json
from collections import defaultdict
from typing import Any

from app.core import db
from app.core.timeutil import utc_now_iso


class EventHub:
    """Fan-out of typed session events to SSE subscribers, persisted for replay."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._seq: dict[str, int] = {}

    def _next_seq(self, session_id: str) -> int:
        if session_id not in self._seq:
            row = db.query_one("SELECT MAX(seq) AS seq FROM session_events WHERE session_id = ?", (session_id,))
            self._seq[session_id] = (row or {}).get("seq") or 0
        self._seq[session_id] += 1
        return self._seq[session_id]

    def publish(self, session_id: str, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "seq": self._next_seq(session_id),
            "ts": utc_now_iso(),
            "type": event_type,
            "data": data or {},
        }
        db.execute(
            "INSERT INTO session_events (session_id, seq, ts, type, payload) VALUES (?, ?, ?, ?, ?)",
            (session_id, event["seq"], event["ts"], event_type, db.dumps(event["data"])),
        )
        for queue in list(self._subscribers[session_id]):
            queue.put_nowait(event)
        return event

    def history(self, session_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        rows = db.query(
            "SELECT seq, ts, type, payload FROM session_events WHERE session_id = ? AND seq > ? ORDER BY seq",
            (session_id, after_seq),
        )
        return [{"seq": r["seq"], "ts": r["ts"], "type": r["type"], "data": json.loads(r["payload"])} for r in rows]

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers[session_id].discard(queue)


hub = EventHub()
