import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.core.timeutil import utc_now
from app.simulator import catalog

SIGNALS: dict[str, tuple[str, str]] = {
    "cell.mode": ("HMI", "Cell operating mode"),
    "sequence.step": ("DB10.STEP", "Active sequence step"),
    "sequence.step_elapsed_s": ("DB10.T", "Seconds spent in active step"),
    "robot.at_pick": ("I5.2", "Robot at pick position"),
    "robot.at_home": ("I5.0", "Robot at home position"),
    "robot.program_running": ("I5.4", "Robot program running"),
    "conv.infeed.running": ("I3.0", "Infeed conveyor running feedback"),
    "sensor.case_present_pick": ("I3.4", "Case present at pick (photo-eye B12)"),
    "grip.close_cmd": ("Q4.0", "Gripper close command (valve Y4)"),
    "grip.open_fb": ("I2.0", "Gripper open position (sensor B20)"),
    "grip.closed_fb": ("I2.1", "Gripper closed position (sensor B21)"),
    "air.pressure_switch_ok": ("I1.6", "Main air pressure switch > 4.0 bar"),
    "safety.estop_ok": ("F-I0.0", "Emergency stop circuit healthy"),
    "safety.light_curtain_ok": ("F-I0.3", "Light curtain LC2 OSSD healthy"),
    "safety.relay_ok": ("F-I0.4", "Safety relay K20 closed"),
    "pallet.in_position": ("I6.1", "Pallet located at build station"),
    "pallet.layer_count": ("DB20.LAYERS", "Completed layers on current pallet"),
}

SEQUENCE: dict[str, list[tuple[str, Any, str]]] = {
    "10_WAIT_CASE": [
        ("sensor.case_present_pick", True, "Case present at pick position"),
        ("robot.at_home", True, "Robot at home before pick"),
        ("safety.estop_ok", True, "E-stop circuit healthy"),
    ],
    "30_GRIP_CLOSE": [
        ("grip.close_cmd", True, "Close command issued"),
        ("grip.closed_fb", True, "Closed-position feedback within 1.5 s"),
        ("air.pressure_switch_ok", True, "Main air pressure switch OK"),
    ],
    "40_PLACE": [
        ("grip.closed_fb", True, "Case held (closed feedback)"),
        ("pallet.in_position", True, "Pallet located at station"),
        ("safety.light_curtain_ok", True, "Pallet-exit light curtain LC2 clear"),
        ("safety.relay_ok", True, "Safety relay K20 closed"),
    ],
}

MAINTENANCE_MODE_TESTS = {"T_GRIP_MANUAL_CYCLE"}


@dataclass
class TestExecution:
    test_id: str
    outcome: str
    observations: dict[str, Any]
    started_at: str
    finished_at: str


@dataclass
class PalletizerSimulator:
    scenario_id: str
    anchor: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        definition = catalog.scenario(self.scenario_id)
        self._definition = definition
        self.signals: dict[str, Any] = copy.deepcopy(definition["signals"])
        self._hidden: dict[str, Any] = copy.deepcopy(definition["hidden"])
        self._clock = self.anchor

    @property
    def machine_id(self) -> str:
        return catalog.machine_info()["id"]

    def _at(self, offset_s: float) -> str:
        return (self.anchor + timedelta(seconds=offset_s)).isoformat(timespec="milliseconds")

    def now(self) -> str:
        return self._clock.isoformat(timespec="milliseconds")

    def _advance(self, seconds: float) -> None:
        self._clock += timedelta(seconds=seconds)

    def snapshot(self) -> dict[str, Any]:
        signals = [
            {"name": name, "address": SIGNALS[name][0], "description": SIGNALS[name][1], "value": value}
            for name, value in self.signals.items()
            if name in SIGNALS
        ]
        return {
            "machine_id": self.machine_id,
            "simulated": True,
            "read_at": self.now(),
            "mode": self.signals["cell.mode"],
            "sequence_step": self.signals["sequence.step"],
            "signals": signals,
            "active_alarms": [a for a in self.alarm_history() if a["active"]],
        }

    def alarm_history(self) -> list[dict[str, Any]]:
        return [
            {
                "code": alarm["code"],
                "message": alarm["message"],
                "severity": alarm["severity"],
                "active": alarm["active"],
                "timestamp": self._at(alarm["offset_s"]),
            }
            for alarm in sorted(self._definition["alarm_log"], key=lambda a: a["offset_s"])
        ]

    def signal_history(self) -> list[dict[str, Any]]:
        return [
            {"timestamp": self._at(item["offset_s"]), "signal": item["signal"], "value": item["value"]}
            for item in sorted(self._definition["signal_history"], key=lambda s: s["offset_s"])
        ]

    def trace_sequence(self) -> dict[str, Any]:
        step = self.signals["sequence.step"]
        conditions = [
            {
                "condition": label,
                "signal": signal,
                "expected": expected,
                "observed": self.signals.get(signal),
                "satisfied": self.signals.get(signal) == expected,
            }
            for signal, expected, label in SEQUENCE.get(step, [])
        ]
        return {
            "machine_id": self.machine_id,
            "simulated": True,
            "step": step,
            "step_elapsed_s": self.signals.get("sequence.step_elapsed_s"),
            "conditions": conditions,
            "blocking": [c["condition"] for c in conditions if not c["satisfied"]],
            "read_at": self.now(),
        }

    def test_permission(self, test_id: str) -> tuple[bool, str]:
        override = self._definition.get("test_permissions", {}).get(test_id)
        if override is not None and not override["permitted"]:
            return False, override["reason"]
        if test_id in MAINTENANCE_MODE_TESTS:
            if self.signals.get("cell.mode") == "AUTO" or self.signals.get("robot.program_running"):
                return False, "Equipment-moving tests require the cell out of AUTO and the robot program stopped."
            if not self.signals.get("robot.at_home"):
                return False, "Equipment-moving tests require the robot at its home position."
        return True, "Permitted read-only diagnostic." if test_id not in MAINTENANCE_MODE_TESTS else "Permitted in maintenance mode."

    def run_test(self, test_id: str) -> TestExecution:
        handler = getattr(self, f"_test_{test_id[2:].lower()}", None)
        if handler is None:
            raise KeyError(f"No simulator handler for {test_id}")
        started = self.now()
        outcome, observations = handler()
        self._advance(catalog.fault_model()["tests"][test_id]["duration_s"])
        return TestExecution(test_id, outcome, observations, started, self.now())

    def _test_grip_io_check(self) -> tuple[str, dict[str, Any]]:
        current = self._hidden["grip.valve_coil_current_ma"]
        energized = current > 100 and self.signals["grip.close_cmd"]
        return ("coil_energized" if energized else "coil_not_energized"), {
            "close_cmd_Q4.0": self.signals["grip.close_cmd"],
            "valve_Y4_coil_current_mA": current,
            "open_fb_I2.0": self.signals["grip.open_fb"],
            "closed_fb_I2.1": self.signals["grip.closed_fb"],
        }

    def _test_air_pressure(self) -> tuple[str, dict[str, Any]]:
        pressure = self._hidden["air.manifold_pressure_bar"]
        return ("pressure_normal" if pressure >= 5.5 else "pressure_low"), {
            "manifold_pressure_bar": pressure,
            "minimum_required_bar": 5.5,
            "main_pressure_switch_ok_4bar": self.signals["air.pressure_switch_ok"],
        }

    def _test_grip_sensor_diag(self) -> tuple[str, dict[str, Any]]:
        comm = self._hidden["grip.closed_sensor_comm"]
        distance = self._hidden["grip.closed_sensor_distance_mm"]
        if comm != "ok":
            return "no_communication", {"io_link_status": comm, "device": "B21"}
        if distance <= 2.0:
            outcome = "target_in_range"
        elif distance <= 5.0:
            outcome = "target_beyond_switch_point"
        else:
            outcome = "target_absent"
        return outcome, {
            "device": "B21 inductive, IO-Link",
            "io_link_status": comm,
            "measured_target_distance_mm": distance,
            "switching_distance_mm": 2.0,
            "switch_output": distance <= 2.0,
        }

    def _test_grip_manual_cycle(self) -> tuple[str, dict[str, Any]]:
        motion = self._hidden["grip.jaw_motion"]
        timings = {
            "full_stroke_no_closed_fb": ("no_closed_feedback", 0.3, None),
            "slow_close": ("closes_slow", 0.6, 2.4),
            "normal": ("normal", 0.3, 0.7),
            "no_motion": ("no_motion", None, None),
        }
        outcome, open_off_s, closed_on_s = timings[motion]
        return outcome, {
            "open_fb_off_after_s": open_off_s,
            "closed_fb_on_after_s": closed_on_s,
            "confirm_window_s": 1.5,
        }

    def _test_conveyor_drive(self) -> tuple[str, dict[str, Any]]:
        running = self.signals["conv.infeed.running"]
        load = self._hidden["conv.motor_load_pct"]
        if not running:
            outcome = "not_running"
        elif load > 80:
            outcome = "running_high_load"
        else:
            outcome = "running_normal_load"
        return outcome, {
            "vfd_run_status": running,
            "speed_mps": 0.4 if running else 0.0,
            "motor_load_pct": load,
        }

    def _test_upstream_flow(self) -> tuple[str, dict[str, Any]]:
        count = self._hidden["upstream.cases_last_5min"]
        return ("cases_arriving" if count > 0 else "no_cases"), {
            "entry_sensor": "B10",
            "cases_last_5_min": count,
        }

    def _test_case_tracking(self) -> tuple[str, dict[str, Any]]:
        state = self._hidden["tracking.case_state"]
        if state == "overdue_at_pick":
            return "case_overdue_at_pick", {
                "last_case_entry_s_ago": 38,
                "expected_transit_s": 9,
                "case_detected_at_pick": False,
            }
        return "no_case_in_transit", {"tracking_state": state, "cases_in_transit": 0}

    def _test_pick_eye_diag(self) -> tuple[str, dict[str, Any]]:
        margin = self._hidden["pick_eye.margin_pct"]
        return ("signal_ok" if margin >= 60 else "signal_low"), {
            "device": "B12 photo-eye, IO-Link",
            "received_light_margin_pct": margin,
            "switching_threshold_pct": 100,
            "contamination_warning": margin < 60,
        }

    def _test_safety_circuit(self) -> tuple[str, dict[str, Any]]:
        ossd = self._hidden["lc2.ossd"]
        latched = self._hidden["safety.relay_latched"]
        if ossd == "off":
            outcome = "ossd_off"
        elif latched:
            outcome = "ossd_on_relay_latched"
        else:
            outcome = "circuit_ok"
        return outcome, {
            "lc2_ossd1": ossd,
            "lc2_ossd2": ossd,
            "relay_k20_closed": self.signals["safety.relay_ok"],
            "relay_k20_reset_required": latched,
        }

    def _test_lc_beam_diag(self) -> tuple[str, dict[str, Any]]:
        beams = self._hidden["lc2.beams"]
        if beams.startswith("partial"):
            first, last = beams.split("_")[1:]
            return "partial_beams_blocked", {
                "beams_total": 24,
                "beams_interrupted": list(range(int(first), int(last) + 1)),
                "approx_height_m": "0.85-1.05",
                "other_beams_signal": "strong",
                "device_fault_code": None,
            }
        mapping = {"clear": "beams_clear", "weak": "all_beams_weak", "fault": "device_fault"}
        return mapping[beams], {"beams_total": 24, "state": beams}
