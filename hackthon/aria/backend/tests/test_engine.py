import pytest

from app.agents.engine import DiagnosticEngine, EngineError
from app.simulator import catalog
from app.simulator.palletizer import PalletizerSimulator


def _uniform_engine(scenario_id: str) -> tuple[DiagnosticEngine, PalletizerSimulator, str]:
    sim = PalletizerSimulator(scenario_id)
    alarm = next(a for a in sim.alarm_history() if a["active"])["code"]
    engine = DiagnosticEngine(max_tests=6, timeout_s=999)
    model = engine.fault_model_for(alarm)
    engine.register(alarm, [{"hypothesis_id": h["id"], "prior": 1.0, "rationale": "uniform"} for h in model["candidate_hypotheses"]])
    return engine, sim, alarm


@pytest.mark.parametrize("scenario", [s["id"] for s in catalog.scenarios() if s["kind"] == "fault"])
def test_greedy_policy_reaches_ground_truth(scenario: str) -> None:
    engine, sim, _ = _uniform_engine(scenario)
    while (decision := engine.decide(sim))["decision"] == "continue":
        result = sim.run_test(decision["next_test"])
        engine.observe(result.test_id, result.outcome, f"E{len(engine.tests)}")
    truth = catalog.scenario(scenario)["ground_truth"]["hypothesis_id"]
    assert decision["stop_reason"] == "sufficient_evidence"
    assert decision["leading_hypothesis"] == truth
    assert len(engine.tests) <= catalog.scenario(scenario)["expected"]["max_reasonable_tests"]


def test_equipment_moving_test_blocked_when_robot_not_home() -> None:
    engine, sim, _ = _uniform_engine("gripper_feedback_missing")
    permitted, reason = sim.test_permission("T_GRIP_MANUAL_CYCLE")
    assert not permitted and "home" in reason
    ranked = {r["test_id"]: r for r in engine.rank_tests(sim)}
    assert ranked["T_GRIP_MANUAL_CYCLE"]["permitted"] is False


def test_adjustment_is_bounded_and_cannot_beat_contradicting_test() -> None:
    engine, sim, _ = _uniform_engine("gripper_low_air")
    for _ in range(3):
        engine.adjust("H_GRIP_SENSOR_MISALIGNED", "raise", "moderate", "operator blames sensor")
    result = sim.run_test("T_AIR_PRESSURE")
    engine.observe(result.test_id, result.outcome, "E1")
    result = sim.run_test("T_GRIP_SENSOR_DIAG")
    engine.observe(result.test_id, result.outcome, "E2")
    assert engine.leading().id == "H_AIR_PRESSURE_LOW"


def test_register_rejects_unknown_hypothesis_and_repeat_test() -> None:
    engine, sim, alarm = _uniform_engine("case_missing_photoeye")
    with pytest.raises(EngineError):
        DiagnosticEngine(6, 999).register(alarm, [{"hypothesis_id": "H_MADE_UP", "prior": 1, "rationale": "x"}])
    result = sim.run_test("T_PICK_EYE_DIAG")
    engine.observe(result.test_id, result.outcome, "E1")
    with pytest.raises(EngineError):
        engine.observe(result.test_id, result.outcome, "E2")


def test_snapshot_never_exposes_hidden_state() -> None:
    sim = PalletizerSimulator("gripper_feedback_missing")
    names = {s["name"] for s in sim.snapshot()["signals"]}
    hidden = set(catalog.scenario("gripper_feedback_missing")["hidden"])
    assert not names & hidden
    assert "ground_truth" not in str(sim.snapshot())
