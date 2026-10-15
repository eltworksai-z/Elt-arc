import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.agents.context import AgentMode
from app.agents.session import AgentSession, sessions
from app.core import db
from app.core.config import get_settings
from app.core.events import hub
from app.core.timeutil import new_id, utc_now_iso
from app.evals import grader
from app.evals.participants import CompletionObserver, SimulatedCaller
from app.evals.voice_relay import run_voice_conversation

logger = logging.getLogger("aria.eval")
Channel = Literal["text", "voice"]
MAX_OPERATOR_TURNS = 7


@lru_cache
def eval_cases() -> list[dict[str, Any]]:
    path = get_settings().data_dir / "eval_cases.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))["cases"]


def _case(case_id: str) -> dict[str, Any]:
    return next(c for c in eval_cases() if c["id"] == case_id)


async def _watch_interjections(session: AgentSession, case: dict[str, Any]) -> None:
    pending = list(case["caller"].get("interjections", []))
    if not pending:
        return
    queue = hub.subscribe(session.id)
    try:
        while pending:
            event = await queue.get()
            if event["type"] == "tool.completed" and event["data"]["name"] == pending[0]["after_tool"]:
                session.submit(pending.pop(0)["text"], "simulated_caller")
    finally:
        hub.unsubscribe(session.id, queue)


def _transcript_from_events(session_id: str) -> list[dict[str, Any]]:
    transcript = []
    for event in hub.history(session_id):
        data = event["data"]
        if event["type"] == "operator.message":
            transcript.append({"speaker": "operator", "text": data["text"], "ts": event["ts"]})
        elif event["type"] in {"agent.say", "agent.message"} and data.get("text"):
            transcript.append({"speaker": "assistant", "text": data["text"], "ts": event["ts"]})
    return transcript


async def run_text_conversation(case: dict[str, Any], session: AgentSession) -> dict[str, Any]:
    caller = SimulatedCaller(case)
    observer = CompletionObserver(case)
    watcher = asyncio.create_task(_watch_interjections(session, case))
    utterance = case["caller"]["opening"]
    try:
        for _ in range(MAX_OPERATOR_TURNS):
            await session.ask(utterance)
            transcript = _transcript_from_events(session.id)
            if (await observer.check(transcript)).resolved:
                break
            turn = await caller.next_turn(transcript)
            if turn.end_call:
                hub.publish(session.id, "operator.message", {"text": turn.utterance, "source": "simulated_caller", "closing": True})
                break
            utterance = turn.utterance
    finally:
        watcher.cancel()
    return {"transcript": _transcript_from_events(session.id), "caller_usage": caller.usage}


async def run_case(run_id: str, case_id: str, mode: AgentMode, channel: Channel, out_dir: Path) -> dict[str, Any]:
    case = _case(case_id)
    session = sessions.create(case["scenario_id"], mode, kind="eval", title=f"Eval {case_id} · {mode} · {channel}", record_history=False)
    hub.publish(run_id, "eval.case.started", {"case_id": case_id, "mode": mode, "channel": channel, "session_id": session.id})
    try:
        if channel == "voice":
            conversation = await run_voice_conversation(case, session, out_dir)
        else:
            conversation = await run_text_conversation(case, session)
        extra = {"channel": channel, "session_id": session.id, "caller_usage": conversation["caller_usage"]}
        if "voice" in conversation:
            extra["voice"] = conversation["voice"]
            extra["delegations"] = conversation["voice"]["delegations"]
            extra["expected_delegations"] = case["expected"].get("expected_delegations")
        result = await grader.grade(case, session, conversation["transcript"], extra)
        result["transcript"] = conversation["transcript"]
        result["tool_log"] = [{k: v for k, v in t.items() if k != "result"} for t in session.ctx.tool_log]
    except Exception as exc:
        logger.exception("Eval case %s failed", case_id)
        result = {"case_id": case_id, "mode": mode, "channel": channel, "session_id": session.id, "error": f"{type(exc).__name__}: {exc}"}
    hub.publish(run_id, "eval.case.completed", {k: v for k, v in result.items() if k not in {"transcript", "tool_log", "voice"}})
    return result


async def run_eval(run_id: str, case_ids: list[str], modes: list[AgentMode], channel: Channel, concurrency: int) -> None:
    out_dir = get_settings().eval_runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(case_id: str, mode: AgentMode) -> dict[str, Any]:
        async with semaphore:
            return await run_case(run_id, case_id, mode, channel, out_dir)

    results = await asyncio.gather(*(guarded(c, m) for c in case_ids for m in modes))
    summary = grader.summarize(list(results))
    payload = {"run_id": run_id, "channel": channel, "created_at": utc_now_iso(), "summary": summary, "results": list(results)}
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    db.execute("UPDATE eval_runs SET status = 'completed', summary = ? WHERE id = ?", (db.dumps(summary), run_id))
    hub.publish(run_id, "eval.run.completed", {"summary": summary})


def start_run(case_ids: list[str], modes: list[AgentMode], channel: Channel, concurrency: int = 2) -> str:
    run_id = new_id("run")
    config = {"cases": case_ids, "modes": modes, "channel": channel, "concurrency": concurrency}
    db.execute("INSERT INTO eval_runs (id, created_at, status, config) VALUES (?, ?, 'running', ?)", (run_id, utc_now_iso(), db.dumps(config)))
    hub.publish(run_id, "eval.run.started", config)
    task = asyncio.create_task(run_eval(run_id, case_ids, modes, channel, concurrency))
    task.add_done_callback(lambda t: _mark_failed(run_id, t))
    return run_id


def _mark_failed(run_id: str, task: asyncio.Task[None]) -> None:
    if task.cancelled() or task.exception() is None:
        return
    db.execute("UPDATE eval_runs SET status = 'failed', summary = ? WHERE id = ?", (db.dumps({"error": str(task.exception())}), run_id))
    hub.publish(run_id, "eval.run.failed", {"error": str(task.exception())})


def load_results(run_id: str) -> dict[str, Any] | None:
    path = get_settings().eval_runs_dir / run_id / "results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
