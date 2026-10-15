import json
from typing import Any

import pytest
from agents.tool_context import ToolContext

from app.agents.context import AgentContext
from app.agents.reporting import EvidenceCitation, ReportDraft, write_report
from app.core.db import init_db
from app.memory.temporal_store import seed_history_if_empty
from app.simulator.palletizer import PalletizerSimulator
from app.tools import diagnostics as tools


@pytest.fixture
def ctx() -> AgentContext:
    init_db()
    seed_history_if_empty()
    events: list[tuple[str, dict[str, Any]]] = []
    context = AgentContext(
        session_id="ses_test",
        mode="improved",
        sim=PalletizerSimulator("gripper_feedback_missing"),
        emit=lambda t, d: events.append((t, d)),
        record_history=False,
    )
    context.events = events
    return context


async def call(ctx: AgentContext, tool: Any, **args: Any) -> dict[str, Any]:
    raw = json.dumps(args)
    tool_ctx = ToolContext(ctx, tool_name=tool.name, tool_call_id="call_test", tool_arguments=raw)
    return json.loads(await tool.on_invoke_tool(tool_ctx, raw))


@pytest.mark.asyncio
async def test_investigation_tool_flow(ctx: AgentContext) -> None:
    opened = await call(ctx, tools.start_investigation, operator_request="The palletizer stopped")
    assert opened["status"] == "opened"
    snapshot = await call(ctx, tools.get_machine_snapshot)
    assert snapshot["active_alarms"][0]["code"] == "A-301"
    history = await call(ctx, tools.search_past_incidents, query="gripper close timeout after finger replacement", alarm_code="A-301", component="gripper.closed_sensor")
    assert history["incidents"][0]["alarm_code"] == "A-301"
    assert history["retrieval"]["mode"] == "lexical"

    ctx.operator_inbox.append("The gripper was serviced this morning.")
    model = await call(ctx, tools.get_fault_model, alarm_code="A-301")
    assert model["operator_updates"][0]["text"].startswith("The gripper")
    operator_evidence = model["operator_updates"][0]["evidence_id"]

    registered = await call(
        ctx,
        tools.register_hypotheses,
        alarm_code="A-301",
        hypotheses=[{"hypothesis_id": h["id"], "prior": 0.2, "rationale": "even"} for h in model["candidate_hypotheses"]],
    )
    assert registered["decision"]["decision"] == "continue"
    adjusted = await call(ctx, tools.adjust_hypothesis, hypothesis_id="H_GRIP_SENSOR_MISALIGNED", direction="raise", strength="moderate", reason="serviced this morning", evidence_id=operator_evidence)
    assert adjusted["adjustment"]["posterior_after"] > adjusted["adjustment"]["posterior_before"]

    blocked = await call(ctx, tools.run_diagnostic_test, test_id="T_GRIP_MANUAL_CYCLE", rationale="confirm")
    assert blocked["status"] == "blocked"

    while True:
        plan = await call(ctx, tools.select_next_test)
        if plan["decision"]["decision"] == "stop":
            break
        result = await call(ctx, tools.run_diagnostic_test, test_id=plan["decision"]["next_test"], rationale="highest gain")
        assert result["status"] == "completed"
    assert plan["decision"]["leading_hypothesis"] == "H_GRIP_SENSOR_MISALIGNED"
    assert plan["decision"]["stop_reason"] == "sufficient_evidence"

    declined = await call(ctx, tools.request_control_action, action="restart_cell", operator_request="Can you restart it?")
    assert declined["decision"] == "denied"
    assert any(t == "safety.blocked" for t, _ in ctx.events)


@pytest.mark.asyncio
async def test_unknown_test_returns_structured_error(ctx: AgentContext) -> None:
    await call(ctx, tools.start_investigation, operator_request="stop")
    await call(ctx, tools.register_hypotheses, alarm_code="A-301", hypotheses=[{"hypothesis_id": "H_AIR_PRESSURE_LOW", "prior": 0.5, "rationale": "x"}])
    result = await call(ctx, tools.run_diagnostic_test, test_id="T_RM_RF", rationale="x")
    assert result["error"]["type"] == "KeyError"
    assert ctx.tool_log[-1]["status"] == "error"


@pytest.mark.asyncio
async def test_copilot_tools_in_normal_operation(ctx: AgentContext) -> None:
    ctx.sim = PalletizerSimulator("normal_operation")
    snapshot = await call(ctx, tools.get_machine_snapshot)
    assert snapshot["mode"] == "AUTO" and snapshot["active_alarms"] == []

    status = await call(ctx, tools.get_maintenance_status, component=None)
    overdue = {t["pm_id"] for t in status["tasks"] if t["status"] == "overdue"}
    assert {"PM-PAL01-021", "PM-PAL01-060"} <= overdue

    logged = await call(ctx, tools.record_technician_action, component="sensor.pick_photo_eye_b12", action="Cleaned lens", outcome="margin 150 %")
    assert logged["recorded"] and logged["record_id"] is None

    order = await call(
        ctx, tools.create_work_order, title="Inspect infeed belt", priority="medium", component="conveyor.infeed_drive", description="PM-PAL01-060 overdue", evidence_ids=[status["evidence_id"]]
    )
    assert order["id"].startswith("WO-") and order["status"] == "open"


@pytest.mark.asyncio
async def test_new_issue_after_closed_investigation_resets_engine(ctx: AgentContext) -> None:
    first = await call(ctx, tools.start_investigation, operator_request="stopped")
    await call(ctx, tools.register_hypotheses, alarm_code="A-301", hypotheses=[{"hypothesis_id": "H_AIR_PRESSURE_LOW", "prior": 0.5, "rationale": "x"}])
    ctx.incident_closed = True
    second = await call(ctx, tools.start_investigation, operator_request="stopped again")
    assert second["incident_id"] != first["incident_id"]
    assert not ctx.engine.hypotheses


def test_report_written_with_embedded_structure(ctx: AgentContext) -> None:
    ctx.incident_id = "INC-TEST"
    evidence = ctx.add_evidence("diagnostic_test", "T_GRIP_SENSOR_DIAG -> target_beyond_switch_point")
    draft = ReportDraft(
        title="Gripper close timeout",
        status="diagnosed",
        diagnosis_hypothesis_id="H_GRIP_SENSOR_MISALIGNED",
        diagnosis_summary="B21 out of range",
        confidence=0.92,
        supporting_evidence=[EvidenceCitation(evidence_id=evidence, statement="B21 reads 2.9 mm")],
        contradicting_evidence=[],
        tests_performed=["T_GRIP_SENSOR_DIAG"],
        uncertainty="Manual cycle not run",
        recommended_next_safe_action="Authorized technician realigns B21 per procedure 4.1",
        requires_authorized_technician=True,
        operator_requests_declined=["restart_cell"],
        references=["INC-2026-112"],
    )
    result = write_report(ctx, draft)
    with open(result["path"], encoding="utf-8") as handle:
        content = handle.read()
    assert "<!-- aria-report" in content and "SIMULATED" in content
    assert result["write_status"] == "written"
