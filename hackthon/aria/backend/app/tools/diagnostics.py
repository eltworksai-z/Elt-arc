import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from agents import FunctionTool, RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from app.agents import reporting
from app.agents.context import AgentContext
from app.agents.engine import EngineError
from app.core.llm import MissingApiKeyError
from app.core.timeutil import new_id
from app.memory import cmms, learning, temporal_store
from app.rag import orchestrator, retriever
from app.simulator import catalog

Ctx = RunContextWrapper[AgentContext]
ControlAction = Literal[
    "restart_cell", "reset_alarm", "reset_safety_circuit", "bypass_interlock", "force_output", "move_robot", "change_parameter"
]
EXPECTED_ERRORS = (EngineError, KeyError, ValueError, MissingApiKeyError)


class HypothesisPrior(BaseModel):
    hypothesis_id: str = Field(description="Hypothesis id from get_fault_model")
    prior: float = Field(description="Prior probability 0-1 before testing")
    rationale: str = Field(description="Why this prior: snapshot, history, operator input")


def _ui_result(result: Any) -> Any:
    text = json.dumps(result, default=str)
    return result if len(text) < 12000 else {"truncated": True, "preview": text[:12000]}


async def _invoke(ctx: Ctx, name: str, args: dict[str, Any], body: Callable[[], Awaitable[Any]]) -> str:
    context = ctx.context
    call_id = new_id("call")
    context.emit("tool.started", {"call_id": call_id, "name": name, "args": args})
    started = time.perf_counter()
    status = "ok"
    try:
        result = await body()
    except EXPECTED_ERRORS as exc:
        status = "error"
        result = {"error": {"type": type(exc).__name__, "message": str(exc).strip("'\"")}}
    duration_ms = round((time.perf_counter() - started) * 1000)
    if isinstance(result, dict) and result.get("status") == "blocked":
        status = "blocked"
    entry = {"call_id": call_id, "name": name, "args": args, "status": status, "duration_ms": duration_ms}
    context.tool_log.append(entry | {"result": result})
    context.emit("tool.completed", entry | {"result": _ui_result(result)})
    updates = context.drain_operator_inbox()
    if updates and isinstance(result, dict):
        result["operator_updates"] = updates
    return json.dumps(result, default=str)


def _require_alarm_context(context: AgentContext) -> None:
    if context.incident_id is None:
        raise EngineError("No open investigation. Call start_investigation first.")


@function_tool
async def start_investigation(ctx: Ctx, operator_request: str) -> str:
    """Open an issue record when the worker reports a stop, fault or abnormal behaviour. Not for questions or how-to requests.

    Args:
        operator_request: The worker's description of the issue in their own words.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        if context.incident_id and not context.incident_closed:
            return {"incident_id": context.incident_id, "status": "already_open"}
        if context.incident_closed:
            context.reset_investigation()
        context.incident_id = new_id("INC").upper().replace("INC_", "INC-")
        if context.record_history:
            temporal_store.open_incident(context.incident_id, context.sim.machine_id, operator_request[:120], None, operator_request)
        context.emit("investigation.started", {"incident_id": context.incident_id, "request": operator_request})
        context.timeline("milestone", "Investigation opened", context.incident_id)
        return {"incident_id": context.incident_id, "machine_id": context.sim.machine_id, "status": "opened", "data_source": "SIMULATED palletizer"}

    return await _invoke(ctx, "start_investigation", {"operator_request": operator_request}, body)


@function_tool
async def get_machine_snapshot(ctx: Ctx) -> str:
    """Read current PLC signals, sequence step, mode and active alarms from the (simulated) cell."""

    async def body() -> dict[str, Any]:
        context = ctx.context
        snapshot = context.sim.snapshot()
        alarms = ", ".join(f"{a['code']} {a['message']}" for a in snapshot["active_alarms"]) or "none"
        snapshot["evidence_id"] = context.add_evidence(
            "machine_snapshot",
            f"Mode {snapshot['mode']}, step {snapshot['sequence_step']}, active alarms: {alarms}",
            {s["name"]: s["value"] for s in snapshot["signals"]},
        )
        context.emit("machine.snapshot", snapshot)
        context.timeline("observation", "Machine snapshot read", f"{snapshot['mode']} at {snapshot['sequence_step']}")
        return snapshot

    return await _invoke(ctx, "get_machine_snapshot", {}, body)


@function_tool
async def get_alarm_history(ctx: Ctx, include_signal_history: bool) -> str:
    """Read active and recent alarms with timestamps, optionally with recent signal transitions.

    Args:
        include_signal_history: Also return timestamped signal transitions around the stop.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        alarms = context.sim.alarm_history()
        result: dict[str, Any] = {"machine_id": context.sim.machine_id, "simulated": True, "alarms": alarms}
        if include_signal_history:
            result["signal_history"] = context.sim.signal_history()
        active = [a for a in alarms if a["active"]]
        result["evidence_id"] = context.add_evidence(
            "alarm_history",
            "Active alarms: " + "; ".join(f"{a['code']} at {a['timestamp']}" for a in active),
            result,
        )
        if context.record_history and context.incident_id:
            for alarm in active:
                temporal_store.add_event(context.incident_id, context.sim.machine_id, "alarm", signal=alarm["code"], value=alarm["message"], ts=alarm["timestamp"])
        return result

    return await _invoke(ctx, "get_alarm_history", {"include_signal_history": include_signal_history}, body)


@function_tool
async def trace_sequence_conditions(ctx: Ctx) -> str:
    """List the conditions of the active sequence step with expected vs observed values and which are blocking."""

    async def body() -> dict[str, Any]:
        context = ctx.context
        trace = context.sim.trace_sequence()
        trace["evidence_id"] = context.add_evidence(
            "sequence_trace",
            f"Step {trace['step']} blocking: {', '.join(trace['blocking']) or 'none'}",
            trace,
        )
        context.timeline("observation", "Sequence conditions traced", ", ".join(trace["blocking"]) or "no blocking condition")
        return trace

    return await _invoke(ctx, "trace_sequence_conditions", {}, body)


@function_tool
async def search_past_incidents(ctx: Ctx, query: str, alarm_code: str | None, component: str | None) -> str:
    """Search the temporal incident knowledge base for similar past incidents, their event timelines, outcomes and time-valid facts.

    Args:
        query: Symptom-oriented search text.
        alarm_code: Alarm code to match, or null.
        component: Component tag to match (e.g. gripper.closed_sensor), or null.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        result = await temporal_store.search_incidents(
            query,
            component=component,
            alarm_code=alarm_code,
            exclude_incident=context.incident_id,
            history_only=not context.record_history,
        )
        if result["incidents"]:
            summary = "; ".join(f"{i['incident_id']} ({i['age_days']} d ago): {i['root_cause']}" for i in result["incidents"])
            result["evidence_id"] = context.add_evidence("incident_history", f"Similar past incidents: {summary}", {"incidents": [i["incident_id"] for i in result["incidents"]]})
        context.emit("knowledge.incidents", {"query": query, **result})
        return result

    return await _invoke(ctx, "search_past_incidents", {"query": query, "alarm_code": alarm_code, "component": component}, body)


@function_tool
async def search_manuals(ctx: Ctx, query: str) -> str:
    """Retrieve relevant sections from indexed equipment manuals and procedures (hybrid search with reranking).

    Args:
        query: What to look up, e.g. an alarm code meaning or a procedure name.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        result = await retriever.search(query, top_k=4)
        if result["hits"]:
            result["evidence_id"] = context.add_evidence(
                "manual",
                "Manual sections: " + "; ".join(h["citation"] for h in result["hits"]),
                {"citations": [h["citation"] for h in result["hits"]]},
            )
        context.emit("knowledge.manuals", {"query": query, **result})
        return result

    return await _invoke(ctx, "search_manuals", {"query": query}, body)


@function_tool
async def research_knowledge(ctx: Ctx, question: str) -> str:
    """Multi-step retrieval for knowledge questions: plans sub-queries over manuals and incident history, runs them in parallel, and retries empty branches.

    Args:
        question: The operator's knowledge question.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context

        async def progress(stage: str, data: dict[str, Any]) -> None:
            context.emit(f"retrieval.{stage}", data)

        result = await orchestrator.research(question, progress, history_only=not context.record_history)
        if result["evidence"]:
            result["evidence_id"] = context.add_evidence(
                "knowledge_research",
                f"Research for '{question}': {len(result['evidence'])} sources",
                {"steps": result["steps"]},
            )
        return result

    return await _invoke(ctx, "research_knowledge", {"question": question}, body)


@function_tool
async def get_fault_model(ctx: Ctx, alarm_code: str) -> str:
    """Return the machine fault model for an alarm: candidate fault hypotheses and the allowlisted diagnostic tests.

    Args:
        alarm_code: Active alarm code, e.g. A-301.
    """

    async def body() -> dict[str, Any]:
        return ctx.context.engine.fault_model_for(alarm_code)

    return await _invoke(ctx, "get_fault_model", {"alarm_code": alarm_code}, body)


@function_tool
async def register_hypotheses(ctx: Ctx, alarm_code: str, hypotheses: list[HypothesisPrior]) -> str:
    """Register candidate fault hypotheses with priors. The deterministic engine normalizes them and applies machine rules.

    Args:
        alarm_code: Alarm the hypotheses explain.
        hypotheses: Hypotheses from the fault model with priors and rationale.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        _require_alarm_context(context)
        context.engine.register(alarm_code, [h.model_dump() for h in hypotheses])
        state = context.engine.state()
        context.emit("hypotheses.updated", state | {"trigger": "registered"})
        context.timeline("reasoning", "Hypotheses registered", ", ".join(h["id"] for h in state["hypotheses"][:3]))
        return {"hypotheses": state["hypotheses"], "decision": context.engine.decide(context.sim)}

    args = {"alarm_code": alarm_code, "hypotheses": [h.model_dump() for h in hypotheses]}
    return await _invoke(ctx, "register_hypotheses", args, body)


@function_tool
async def adjust_hypothesis(
    ctx: Ctx,
    hypothesis_id: str,
    direction: Literal["raise", "lower"],
    strength: Literal["weak", "moderate"],
    reason: str,
    evidence_id: str,
) -> str:
    """Apply bounded soft evidence (operator statement, history, manual) to one hypothesis. Cannot override test results.

    Args:
        hypothesis_id: Hypothesis to adjust.
        direction: raise or lower.
        strength: weak or moderate.
        reason: Why the evidence shifts belief.
        evidence_id: Evidence id that justifies the adjustment.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        if evidence_id not in context.evidence_ids():
            raise EngineError(f"Unknown evidence id {evidence_id}")
        result = context.engine.adjust(hypothesis_id, direction, strength, reason)
        state = context.engine.state()
        context.emit("hypotheses.updated", state | {"trigger": f"adjusted {hypothesis_id}"})
        context.timeline("reasoning", f"Belief {direction}d for {hypothesis_id}", reason)
        return {"adjustment": result, "hypotheses": state["hypotheses"], "decision": context.engine.decide(context.sim)}

    args = {"hypothesis_id": hypothesis_id, "direction": direction, "strength": strength, "reason": reason, "evidence_id": evidence_id}
    return await _invoke(ctx, "adjust_hypothesis", args, body)


@function_tool
async def select_next_test(ctx: Ctx) -> str:
    """Rank permitted diagnostic tests by expected information gain over the current hypotheses and return the stop/continue decision."""

    async def body() -> dict[str, Any]:
        context = ctx.context
        ranking = context.engine.rank_tests(context.sim)
        decision = context.engine.decide(context.sim)
        context.emit("decision", decision | {"ranking": ranking})
        return {"ranking": ranking, "decision": decision}

    return await _invoke(ctx, "select_next_test", {}, body)


def _execute_test(context: AgentContext, test_id: str, rationale: str) -> dict[str, Any]:
    tests = catalog.fault_model()["tests"]
    if test_id not in tests:
        raise KeyError(f"Unknown test '{test_id}'. Allowlisted tests: {list(tests)}")
    permitted, reason = context.sim.test_permission(test_id)
    if not permitted:
        attempt = {"test_id": test_id, "reason": reason}
        context.blocked_attempts.append(attempt)
        context.emit("safety.blocked", {"kind": "test", "target": test_id, "reason": reason})
        context.timeline("safety", f"{test_id} blocked by permission rules", reason)
        return {"test_id": test_id, "status": "blocked", "reason": reason}
    execution = context.sim.run_test(test_id)
    evidence_id = context.add_evidence(
        "diagnostic_test",
        f"{test_id} ({tests[test_id]['name']}) -> {execution.outcome}",
        {"outcome": execution.outcome, "observations": execution.observations},
    )
    context.executed_tests.append({"test_id": test_id, "outcome": execution.outcome, "evidence_id": evidence_id, "rationale": rationale})
    context.timeline("test", f"{tests[test_id]['name']}: {execution.outcome}", json.dumps(execution.observations, default=str))
    if context.record_history and context.incident_id:
        temporal_store.add_event(
            context.incident_id, context.sim.machine_id, "diagnostic_test", component=tests[test_id]["family"], signal=test_id, value=execution.outcome
        )
    return {
        "test_id": test_id,
        "status": "completed",
        "outcome": execution.outcome,
        "observations": execution.observations,
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
        "evidence_id": evidence_id,
        "simulated": True,
    }


@function_tool
async def run_diagnostic_test(ctx: Ctx, test_id: str, rationale: str) -> str:
    """Execute one allowlisted diagnostic test on the simulated cell, then update hypotheses and the stop decision.

    Args:
        test_id: Test id from the fault model.
        rationale: Why this test now (which hypotheses it separates).
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        _require_alarm_context(context)
        if not context.engine.hypotheses:
            raise EngineError("Register hypotheses before running tests so results can update them.")
        result = _execute_test(context, test_id, rationale)
        if result["status"] != "completed":
            return result | {"decision": context.engine.decide(context.sim)}
        record = context.engine.observe(test_id, result["outcome"], result["evidence_id"])
        state = context.engine.state()
        decision = context.engine.decide(context.sim)
        context.emit("hypotheses.updated", state | {"trigger": f"{test_id} -> {result['outcome']}"})
        context.emit("decision", decision)
        context.emit("agent.context", {"text": f"Test {test_id} returned {result['outcome']}: {json.dumps(result['observations'])}. Leading hypothesis {decision['leading_hypothesis']} at {decision['leading_confidence']:.0%}. Decision: {decision['decision']}."})
        return result | {
            "expected_gain_bits": record.expected_gain_bits,
            "hypotheses": state["hypotheses"],
            "decision": decision,
        }

    return await _invoke(ctx, "run_diagnostic_test", {"test_id": test_id, "rationale": rationale}, body)


@function_tool
async def list_diagnostic_tests(ctx: Ctx) -> str:
    """List every allowlisted diagnostic test with its description."""

    async def body() -> dict[str, Any]:
        tests = catalog.fault_model()["tests"]
        return {"tests": [{"test_id": tid, "name": t["name"], "description": t["description"]} for tid, t in tests.items()]}

    return await _invoke(ctx, "list_diagnostic_tests", {}, body)


@function_tool(name_override="run_diagnostic_test")
async def run_diagnostic_test_basic(ctx: Ctx, test_id: str, rationale: str) -> str:
    """Execute one allowlisted diagnostic test on the simulated cell and return its observations.

    Args:
        test_id: Test id from list_diagnostic_tests.
        rationale: Why this test now.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        _require_alarm_context(context)
        return _execute_test(context, test_id, rationale)

    return await _invoke(ctx, "run_diagnostic_test", {"test_id": test_id, "rationale": rationale}, body)


@function_tool
async def request_control_action(ctx: Ctx, action: ControlAction, operator_request: str) -> str:
    """Route any operator request to restart, reset, bypass, force or move equipment through the safety policy.

    Args:
        action: The control action requested.
        operator_request: The operator's words.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        reason = catalog.fault_model()["prohibited_actions"][action]
        record = {"action": action, "operator_request": operator_request, "decision": "denied", "policy": reason}
        context.declined_requests.append(record)
        context.add_evidence("safety_policy", f"Declined {action}: {reason}")
        context.emit("safety.blocked", {"kind": "control_action", "target": action, "reason": reason})
        context.timeline("safety", f"Declined {action.replace('_', ' ')}", reason)
        return record | {"status": "blocked"}

    return await _invoke(ctx, "request_control_action", {"action": action, "operator_request": operator_request}, body)


@function_tool
async def notify_operator(ctx: Ctx, message: str) -> str:
    """Speak a short progress update to the operator while work continues (one sentence, no results you have not observed).

    Args:
        message: One short spoken sentence.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        context.spoken.append(message)
        context.emit("agent.say", {"text": message})
        return {"delivered": True}

    return await _invoke(ctx, "notify_operator", {"message": message}, body)


@function_tool
async def write_diagnostic_report(ctx: Ctx, report: reporting.ReportDraft) -> str:
    """Write the structured diagnostic report to disk. Cite evidence ids exactly as returned by tools.

    Args:
        report: The report content.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        _require_alarm_context(context)
        result = reporting.write_report(context, report)
        context.emit("report.written", result | {"report": report.model_dump()})
        context.timeline("report", "Report written", result["path"])
        return result

    return await _invoke(ctx, "write_diagnostic_report", {"title": report.title, "status": report.status}, body)


@function_tool
async def verify_diagnostic_report(ctx: Ctx, report_id: str) -> str:
    """Re-read a written report from disk and verify it against the evidence log, executed tests and engine state.

    Args:
        report_id: Report id returned by write_diagnostic_report.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        result = await reporting.verify_report(context, report_id)
        context.emit("report.verified", result)
        context.timeline("report", "Report verified" if result["verified"] else "Report verification failed", "; ".join(result["mismatches"]))
        if result["verified"]:
            context.incident_closed = True
        if result["verified"] and context.record_history and context.incident_id:
            draft = context.reports[report_id]["draft"]
            leader = context.engine.leading()
            temporal_store.add_event(context.incident_id, context.sim.machine_id, "result", value=draft["diagnosis_summary"], outcome=draft["status"])
            temporal_store.close_incident(
                context.incident_id,
                status="diagnosed" if draft["status"] == "diagnosed" else "escalated",
                root_cause=draft["diagnosis_summary"],
                component=leader.component if leader else None,
                alarm_code=next((a["code"] for a in context.sim.alarm_history() if a["active"]), None),
            )
            learning.schedule_fact_update(
                context.incident_id,
                context.sim.machine_id,
                f"ARIA diagnosed incident {context.incident_id} on {context.sim.machine_id}: {draft['diagnosis_summary']}. "
                f"Tests: {', '.join(draft['tests_performed'])}. Recommended: {draft['recommended_next_safe_action']}",
                context.emit,
            )
        return result

    return await _invoke(ctx, "verify_diagnostic_report", {"report_id": report_id}, body)


@function_tool
async def get_maintenance_status(ctx: Ctx, component: str | None) -> str:
    """Read preventive-maintenance tasks, due dates, last-done dates and usage counters from the CMMS.

    Args:
        component: Component tag or keyword to filter by (e.g. gripper, photo_eye), or null for all tasks.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        result = cmms.maintenance_status(component)
        due = [t for t in result["tasks"] if t["status"] != "scheduled"]
        result["evidence_id"] = context.add_evidence(
            "cmms",
            f"Maintenance plan{f' for {component}' if component else ''}: "
            + "; ".join(f"{t['pm_id']} {t['task'][:60]} last {t['last_done']} ({t['status']})" for t in result["tasks"][:6]),
            {"due_or_overdue": [t["pm_id"] for t in due]},
        )
        return result

    return await _invoke(ctx, "get_maintenance_status", {"component": component}, body)


@function_tool
async def create_work_order(
    ctx: Ctx,
    title: str,
    priority: Literal["low", "medium", "high", "urgent"],
    component: str,
    description: str,
    evidence_ids: list[str],
) -> str:
    """Create a maintenance work order in the CMMS so an authorized technician is assigned. Use only after the worker agrees.

    Args:
        title: Short work order title.
        priority: Priority based on production and safety impact.
        component: Component tag the work applies to.
        description: What to inspect or repair, including the manual procedure reference.
        evidence_ids: Evidence ids that justify the work order.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        unknown = [e for e in evidence_ids if e not in context.evidence_ids()]
        if unknown:
            raise EngineError(f"Unknown evidence ids {unknown}")
        record = cmms.create_work_order(
            session_id=context.session_id,
            incident_id=context.incident_id,
            title=title,
            priority=priority,
            component=component,
            description=description,
            evidence=evidence_ids,
        )
        context.add_evidence("work_order", f"Work order {record['id']} created: {title} ({priority})")
        context.emit("work_order.created", record)
        context.timeline("action", f"Work order {record['id']} created", title)
        return record

    args = {"title": title, "priority": priority, "component": component, "description": description, "evidence_ids": evidence_ids}
    return await _invoke(ctx, "create_work_order", args, body)


@function_tool
async def record_technician_action(ctx: Ctx, component: str, action: str, outcome: str) -> str:
    """Record maintenance work the worker reports having done, so the temporal knowledge base stays current.

    Args:
        component: Component tag the work applied to.
        action: What the worker did, in their words (e.g. realigned B21 to 1.0 mm).
        outcome: Result the worker observed (e.g. 20 test cycles OK), or "unknown".
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        evidence_id = context.add_evidence("technician", f"Worker reported: {action} on {component}; outcome: {outcome}")
        context.timeline("action", f"Technician action recorded on {component}", f"{action} → {outcome}")
        stored_in = None
        if context.record_history:
            record_id = context.incident_id or f"MNT-{new_id('m')[2:10].upper()}"
            if context.incident_id is None:
                temporal_store.open_incident(record_id, context.sim.machine_id, f"Maintenance: {action[:80]}", None, action)
                temporal_store.close_incident(record_id, status="maintenance_logged", root_cause=None, component=component, alarm_code=None)
            temporal_store.add_event(record_id, context.sim.machine_id, "repair", component=component, value=action, technician_action=action, outcome=outcome)
            stored_in = record_id
            learning.schedule_fact_update(record_id, context.sim.machine_id, f"On {context.sim.machine_id}, a technician performed: {action} on {component}. Outcome: {outcome}.", context.emit)
        return {"recorded": True, "evidence_id": evidence_id, "record_id": stored_in, "knowledge_update": "temporal facts refreshing in background" if stored_in else "not persisted (evaluation run)"}

    return await _invoke(ctx, "record_technician_action", {"component": component, "action": action, "outcome": outcome}, body)


VisualKind = Literal["line_status", "alarm_history", "maintenance_plan", "incident_history", "investigation"]


@function_tool
async def show_visual(ctx: Ctx, kind: VisualKind, focus: str | None) -> str:
    """Render a visual card on the worker's screen. Use only when the worker asks to see or show something, or when a picture clearly helps them follow an investigation.

    Args:
        kind: What to show: line_status (live signals, alarms, sequence), alarm_history, maintenance_plan, incident_history, investigation (hypotheses and decision).
        focus: Optional component, alarm code or search text to focus the visual, or null.
    """

    async def body() -> dict[str, Any]:
        context = ctx.context
        sim = context.sim
        if kind == "line_status":
            data: dict[str, Any] = {"snapshot": sim.snapshot(), "trace": sim.trace_sequence()}
        elif kind == "alarm_history":
            data = {"alarms": sim.alarm_history(), "signal_history": sim.signal_history()}
        elif kind == "maintenance_plan":
            data = cmms.maintenance_status(focus)
        elif kind == "incident_history":
            result = await temporal_store.search_incidents(focus or "recent incidents", limit=5, history_only=not context.record_history)
            data = {"incidents": result["incidents"], "facts": result["facts"]}
        else:
            if not context.engine.hypotheses:
                raise EngineError("No investigation is running, so there is nothing to show yet.")
            data = {"engine": context.engine.state(), "decision": context.engine.decide(sim)}
        context.emit("visual.render", {"kind": kind, "focus": focus, "data": data})
        return {"rendered": kind, "on_screen": True}

    return await _invoke(ctx, "show_visual", {"kind": kind, "focus": focus}, body)


IMPROVED_TOOLS: list[FunctionTool] = [
    show_visual,
    start_investigation,
    get_machine_snapshot,
    get_alarm_history,
    trace_sequence_conditions,
    search_past_incidents,
    search_manuals,
    research_knowledge,
    get_fault_model,
    register_hypotheses,
    adjust_hypothesis,
    select_next_test,
    run_diagnostic_test,
    request_control_action,
    notify_operator,
    write_diagnostic_report,
    verify_diagnostic_report,
    get_maintenance_status,
    create_work_order,
    record_technician_action,
]

BASELINE_TOOLS: list[FunctionTool] = [
    start_investigation,
    get_machine_snapshot,
    get_alarm_history,
    trace_sequence_conditions,
    search_past_incidents,
    search_manuals,
    list_diagnostic_tests,
    run_diagnostic_test_basic,
    request_control_action,
    notify_operator,
    write_diagnostic_report,
    get_maintenance_status,
    create_work_order,
    record_technician_action,
]
