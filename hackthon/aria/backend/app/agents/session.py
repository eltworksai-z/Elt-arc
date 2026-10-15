import asyncio
import logging
import re
import time
from functools import lru_cache
from typing import Any, Literal

import openai
from agents import Agent, ModelSettings, Runner, set_default_openai_key
from openai.types.shared import Reasoning

from app.agents.context import AgentContext, AgentMode
from app.agents.prompts import BASELINE_INSTRUCTIONS, IMPROVED_INSTRUCTIONS
from app.core import db
from app.core.config import get_settings
from app.core.events import hub
from app.core.llm import MissingApiKeyError
from app.core.timeutil import new_id, utc_now_iso
from app.memory import cmms
from app.simulator import catalog
from app.simulator.palletizer import PalletizerSimulator
from app.tools.diagnostics import BASELINE_TOOLS, IMPROVED_TOOLS

logger = logging.getLogger("aria.session")
InputSource = Literal["text", "voice", "simulated_caller"]
INPUT_TAG = re.compile(r"\[\w+ input\] ")
_reasoning_summaries = {"enabled": True}


@lru_cache
def build_agent(mode: AgentMode, summaries: bool) -> Agent[AgentContext]:
    settings = get_settings()
    reasoning = Reasoning(effort=settings.agent_reasoning_effort, summary="auto" if summaries else None)
    return Agent[AgentContext](
        name="ARIA Investigator" if mode == "improved" else "Baseline Assistant",
        instructions=IMPROVED_INSTRUCTIONS if mode == "improved" else BASELINE_INSTRUCTIONS,
        tools=IMPROVED_TOOLS if mode == "improved" else BASELINE_TOOLS,
        model=settings.agent_model,
        model_settings=ModelSettings(reasoning=reasoning, parallel_tool_calls=True),
    )


class AgentSession:
    def __init__(self, session_id: str, scenario_id: str, mode: AgentMode, record_history: bool) -> None:
        self.id = session_id
        self.scenario_id = scenario_id
        self.mode = mode
        self.ctx = AgentContext(
            session_id=session_id,
            mode=mode,
            sim=PalletizerSimulator(scenario_id),
            emit=self._emit,
            record_history=record_history,
        )
        self.history: list[Any] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "requests": 0, "turns": 0}
        self.turns: list[dict[str, Any]] = []
        self.current_delegation: str | None = None
        self.titled = False
        self._queued_delegations: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._idle = asyncio.Event()
        self._idle.set()

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type in {"agent.say", "agent.context"}:
            data = data | {"delegation_id": self.current_delegation}
        hub.publish(self.id, event_type, data)

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def submit(self, text: str, source: InputSource, delegation_id: str | None = None) -> dict[str, Any]:
        self._emit("operator.message", {"text": text, "source": source, "delegation_id": delegation_id})
        if not self.titled:
            self.titled = True
            title = text if len(text) <= 60 else text[:57].rsplit(" ", 1)[0] + "…"
            db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, self.id))
            self._emit("session.titled", {"title": title})
        if self.busy:
            self.ctx.operator_inbox.append(text)
            self._emit("operator.queued", {"text": text, "delegation_id": delegation_id})
            if delegation_id:
                self._queued_delegations.append(delegation_id)
                self._emit(
                    "delegation.ack",
                    {"delegation_id": delegation_id, "text": "Got it — that was passed to the work already running and will be used in the next step."},
                )
            return {"status": "queued"}
        self._idle.clear()
        self._task = asyncio.create_task(self._run_loop(text, source, delegation_id))
        return {"status": "started"}

    async def wait_idle(self) -> None:
        await self._idle.wait()

    async def ask(self, text: str, source: InputSource = "simulated_caller") -> str:
        before = len(self.turns)
        self.submit(text, source)
        await self.wait_idle()
        replies = [t["reply"] for t in self.turns[before:] if t.get("reply")]
        return " ".join(replies)

    async def _run_loop(self, text: str, source: InputSource, delegation_id: str | None) -> None:
        try:
            pending = f"[{source} input] {text}"
            while pending:
                self.current_delegation = delegation_id
                await self._run_turn(pending)
                leftover = [self.ctx.operator_inbox.pop(0) for _ in range(len(self.ctx.operator_inbox))]
                pending = " ".join(f"[{source} input] {t}" for t in leftover) if leftover else ""
                delegation_id = self._queued_delegations[-1] if self._queued_delegations else None
                self._queued_delegations.clear()
        finally:
            self.current_delegation = None
            self._idle.set()

    async def _run_turn(self, user_text: str) -> None:
        settings = get_settings()
        started = time.perf_counter()
        self._emit("agent.turn.started", {"mode": self.mode})
        reply = ""
        try:
            if not settings.has_api_key:
                raise MissingApiKeyError()
            reply = await self._stream(user_text, settings)
        except openai.BadRequestError as exc:
            if _reasoning_summaries["enabled"] and "summary" in str(exc).lower():
                _reasoning_summaries["enabled"] = False
                reply = await self._stream(user_text, settings)
            else:
                self._fail(exc)
        except (MissingApiKeyError, openai.OpenAIError) as exc:
            self._fail(exc)
        except Exception as exc:
            logger.exception("Agent turn failed")
            self._fail(exc)
        duration = round(time.perf_counter() - started, 2)
        turn = {"user": user_text, "reply": reply, "duration_s": duration}
        self.turns.append(turn)
        self.usage["turns"] += 1
        self._emit("agent.turn.completed", {"duration_s": duration, "usage": self.usage, "delegation_id": self.current_delegation})
        db.execute("UPDATE sessions SET updated_at = ?, summary = ? WHERE id = ?", (utc_now_iso(), (reply or INPUT_TAG.sub("", user_text))[:160], self.id))

    def _fail(self, exc: Exception) -> None:
        message = str(exc)
        self._emit("error", {"message": message, "type": type(exc).__name__})
        self._emit("agent.message", {"text": f"I couldn't complete that: {message}", "delegation_id": self.current_delegation, "error": True})

    async def _stream(self, user_text: str, settings: Any) -> str:
        agent = build_agent(self.mode, _reasoning_summaries["enabled"])
        result = Runner.run_streamed(
            agent,
            input=self.history + [{"role": "user", "content": user_text}],
            context=self.ctx,
            max_turns=settings.max_agent_turns,
        )
        async for event in result.stream_events():
            if event.type != "raw_response_event":
                continue
            data = event.data
            if data.type == "response.output_text.delta":
                self._emit("agent.delta", {"text": data.delta})
            elif data.type == "response.reasoning_summary_text.delta":
                self._emit("agent.thinking.delta", {"text": data.delta})
            elif data.type == "response.reasoning_summary_part.done":
                self._emit("agent.thinking", {"text": data.part.text})
        usage = result.context_wrapper.usage
        self.usage["input_tokens"] += usage.input_tokens
        self.usage["output_tokens"] += usage.output_tokens
        self.usage["requests"] += usage.requests
        details = getattr(usage, "output_tokens_details", None)
        self.usage["reasoning_tokens"] += getattr(details, "reasoning_tokens", 0) or 0
        self.history = result.to_input_list()
        reply = str(result.final_output or "").strip()
        self._emit("agent.message", {"text": reply, "delegation_id": self.current_delegation})
        return reply

    def state(self) -> dict[str, Any]:
        ctx = self.ctx
        return {
            "session_id": self.id,
            "scenario": catalog.public_scenario(catalog.scenario(self.scenario_id)),
            "mode": self.mode,
            "busy": self.busy,
            "incident_id": ctx.incident_id,
            "engine": ctx.engine.state() if ctx.engine.hypotheses else None,
            "evidence": ctx.evidence,
            "executed_tests": ctx.executed_tests,
            "blocked_attempts": ctx.blocked_attempts,
            "declined_requests": ctx.declined_requests,
            "reports": ctx.reports,
            "work_orders": cmms.list_work_orders(self.id),
            "usage": self.usage,
        }


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def create(
        self,
        scenario_id: str | None = None,
        mode: AgentMode = "improved",
        kind: str = "live",
        title: str | None = None,
        record_history: bool = True,
    ) -> AgentSession:
        scenario_id = scenario_id or catalog.default_scenario_id()
        scenario = catalog.scenario(scenario_id)
        session_id = new_id("ses")
        now = utc_now_iso()
        db.execute(
            "INSERT INTO sessions (id, title, kind, scenario_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (session_id, title or "New conversation", kind, scenario_id, now, now),
        )
        session = AgentSession(session_id, scenario_id, mode, record_history)
        session.titled = title is not None
        self._sessions[session_id] = session
        hub.publish(
            session_id,
            "session.created",
            {"scenario": catalog.public_scenario(scenario), "machine": catalog.machine_info(), "mode": mode, "kind": kind},
        )
        return session

    def get(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)

    def discard(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def configure_sdk() -> None:
    settings = get_settings()
    if settings.has_api_key:
        set_default_openai_key(settings.openai_api_key)


sessions = SessionManager()
