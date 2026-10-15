import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from app.core.timeutil import utc_now_iso
from app.memory import temporal_agent

logger = logging.getLogger("aria.learning")
_tasks: set[asyncio.Task[None]] = set()


def schedule_fact_update(source_id: str, machine_id: str, episode: str, emit: Callable[[str, dict[str, Any]], None]) -> None:
    """Runs temporal fact extraction for new knowledge in the background so the conversation is not blocked."""
    if not get_settings().has_api_key:
        return

    async def run() -> None:
        invalidated: list[dict[str, Any]] = []

        async def progress(data: dict[str, Any]) -> None:
            if data.get("stage") == "invalidated":
                invalidated.append({"old": data["old"], "new": data["new"]})

        try:
            stored = await temporal_agent.ingest_episode(source_id, machine_id, episode, utc_now_iso(), progress)
            emit(
                "knowledge.updated",
                {"source_id": source_id, "facts_added": [s["statement"] for s in stored], "facts_superseded": invalidated},
            )
        except Exception:
            logger.exception("Temporal fact update failed for %s", source_id)

    task = asyncio.create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
