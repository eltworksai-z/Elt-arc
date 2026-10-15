import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.simulator import catalog
from app.simulator.palletizer import PalletizerSimulator

DEFAULT_RELIABILITY = 0.85
RULE_OUT_THRESHOLD = 0.02
SUFFICIENCY_THRESHOLD = 0.9
MIN_USEFUL_GAIN_BITS = 0.05
ADJUSTMENT_FACTORS = {("raise", "weak"): 1.3, ("raise", "moderate"): 1.8, ("lower", "weak"): 0.75, ("lower", "moderate"): 0.5}

StopReason = Literal["sufficient_evidence", "budget_exhausted", "no_useful_test", "timeout", "tool_failure"]


@dataclass
class Hypothesis:
    id: str
    label: str
    component: str
    prior: float
    posterior: float
    rationale: str
    predictions: dict[str, str]
    status: str = "active"
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "component": self.component,
            "prior": round(self.prior, 4),
            "posterior": round(self.posterior, 4),
            "status": self.status,
            "rationale": self.rationale,
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
        }


@dataclass
class TestRecord:
    test_id: str
    outcome: str
    evidence_id: str
    expected_gain_bits: float
    posterior_before: dict[str, float]
    posterior_after: dict[str, float]


class EngineError(ValueError):
    pass


class DiagnosticEngine:
    """Explicit machine knowledge: hypothesis state, rule-based elimination, test selection and stop rules.

    The model proposes and explains; this engine decides what is consistent, what is permitted and when to stop.
    """

    def __init__(self, max_tests: int, timeout_s: float) -> None:
        self.family: str | None = None
        self.hypotheses: dict[str, Hypothesis] = {}
        self.tests: list[TestRecord] = []
        self.adjustments: list[dict[str, Any]] = []
        self.max_tests = max_tests
        self.timeout_s = timeout_s
        self.started = time.monotonic()

    @property
    def model(self) -> dict[str, Any]:
        return catalog.fault_model()

    def fault_model_for(self, alarm_code: str) -> dict[str, Any]:
        family_id = catalog.family_for_alarm(alarm_code)
        if family_id is None:
            known = sorted({c for f in self.model["families"].values() for c in f["alarm_codes"]})
            raise EngineError(f"No fault model for alarm '{alarm_code}'. Known alarm codes: {', '.join(known)}")
        family = self.model["families"][family_id]
        tests = {tid: t for tid, t in self.model["tests"].items() if t["family"] == family_id}
        return {
            "fault_family": family_id,
            "description": family["description"],
            "candidate_hypotheses": [
                {"id": hid, "label": h["label"], "component": h["component"]} for hid, h in family["hypotheses"].items()
            ],
            "diagnostic_tests": [
                {
                    "test_id": tid,
                    "name": t["name"],
                    "description": t["description"],
                    "possible_outcomes": t["outcomes"],
                    "moves_equipment": not t["read_only"],
                }
                for tid, t in tests.items()
            ],
        }

    def register(self, alarm_code: str, priors: list[dict[str, Any]]) -> None:
        family_id = catalog.family_for_alarm(alarm_code)
        if family_id is None:
            raise EngineError(f"No fault model for alarm '{alarm_code}'")
        if self.tests:
            raise EngineError("Hypotheses are already being tested; use adjust_hypothesis to revise beliefs.")
        catalog_hyps = self.model["families"][family_id]["hypotheses"]
        unknown = [p["hypothesis_id"] for p in priors if p["hypothesis_id"] not in catalog_hyps]
        if unknown:
            raise EngineError(f"Unknown hypothesis ids {unknown}. Valid ids: {list(catalog_hyps)}")
        given = {p["hypothesis_id"]: p for p in priors}
        floor = 0.02
        raw = {hid: max(floor, float(given[hid]["prior"])) if hid in given else floor for hid in catalog_hyps}
        total = sum(raw.values())
        self.family = family_id
        self.hypotheses = {
            hid: Hypothesis(
                id=hid,
                label=h["label"],
                component=h["component"],
                prior=raw[hid] / total,
                posterior=raw[hid] / total,
                rationale=given.get(hid, {}).get("rationale", "Catalog hypothesis not proposed by the agent; kept at floor prior."),
                predictions=h["predictions"],
            )
            for hid, h in catalog_hyps.items()
        }
        self._refresh_status()

    def adjust(self, hypothesis_id: str, direction: str, strength: str, reason: str) -> dict[str, Any]:
        hyp = self._require(hypothesis_id)
        factor = ADJUSTMENT_FACTORS[(direction, strength)]
        before = self._posteriors()
        hyp.posterior *= factor
        self._normalize()
        self._refresh_status()
        record = {"hypothesis_id": hypothesis_id, "direction": direction, "strength": strength, "factor": factor, "reason": reason}
        self.adjustments.append(record)
        return {**record, "posterior_before": before[hypothesis_id], "posterior_after": round(hyp.posterior, 4)}

    def _require(self, hypothesis_id: str) -> Hypothesis:
        if not self.hypotheses:
            raise EngineError("No hypotheses registered. Call register_hypotheses first.")
        if hypothesis_id not in self.hypotheses:
            raise EngineError(f"Unknown hypothesis '{hypothesis_id}'. Registered: {list(self.hypotheses)}")
        return self.hypotheses[hypothesis_id]

    def _posteriors(self) -> dict[str, float]:
        return {hid: round(h.posterior, 4) for hid, h in self.hypotheses.items()}

    def _normalize(self) -> None:
        total = sum(h.posterior for h in self.hypotheses.values()) or 1.0
        for h in self.hypotheses.values():
            h.posterior /= total

    def _likelihood(self, hyp: Hypothesis, test_id: str, outcome: str) -> float:
        test = self.model["tests"][test_id]
        outcomes = test["outcomes"]
        reliability = test.get("reliability", DEFAULT_RELIABILITY)
        predicted = hyp.predictions.get(test_id)
        if predicted is None:
            return 1.0 / len(outcomes)
        if outcome == predicted:
            return reliability
        return (1 - reliability) / (len(outcomes) - 1)

    @staticmethod
    def _entropy(probs: list[float]) -> float:
        return -sum(p * math.log2(p) for p in probs if p > 0)

    def expected_gain(self, test_id: str) -> float:
        hyps = list(self.hypotheses.values())
        prior = [h.posterior for h in hyps]
        base = self._entropy(prior)
        expected = 0.0
        for outcome in self.model["tests"][test_id]["outcomes"]:
            joint = [h.posterior * self._likelihood(h, test_id, outcome) for h in hyps]
            p_outcome = sum(joint)
            if p_outcome > 0:
                expected += p_outcome * self._entropy([j / p_outcome for j in joint])
        return max(0.0, base - expected)

    def rank_tests(self, sim: PalletizerSimulator) -> list[dict[str, Any]]:
        if not self.hypotheses:
            raise EngineError("No hypotheses registered. Call register_hypotheses first.")
        done = {t.test_id for t in self.tests}
        ranked = []
        for test_id, test in self.model["tests"].items():
            if test["family"] != self.family:
                continue
            permitted, reason = sim.test_permission(test_id)
            gain = self.expected_gain(test_id) if test_id not in done else 0.0
            ranked.append(
                {
                    "test_id": test_id,
                    "name": test["name"],
                    "already_run": test_id in done,
                    "permitted": permitted,
                    "permission_reason": reason,
                    "expected_gain_bits": round(gain, 3),
                    "useful": gain >= MIN_USEFUL_GAIN_BITS and test_id not in done,
                }
            )
        ranked.sort(key=lambda r: (r["permitted"] and r["useful"], r["expected_gain_bits"]), reverse=True)
        return ranked

    def observe(self, test_id: str, outcome: str, evidence_id: str) -> TestRecord:
        if test_id in {t.test_id for t in self.tests}:
            raise EngineError(f"{test_id} already executed in this investigation.")
        gain = self.expected_gain(test_id)
        before = self._posteriors()
        for hyp in self.hypotheses.values():
            hyp.posterior *= self._likelihood(hyp, test_id, outcome)
            predicted = hyp.predictions.get(test_id)
            if predicted is None:
                continue
            (hyp.evidence_for if predicted == outcome else hyp.evidence_against).append(evidence_id)
        self._normalize()
        self._refresh_status()
        record = TestRecord(test_id, outcome, evidence_id, round(gain, 3), before, self._posteriors())
        self.tests.append(record)
        return record

    def _refresh_status(self) -> None:
        leader = self.leading()
        for hyp in self.hypotheses.values():
            if hyp.posterior < RULE_OUT_THRESHOLD:
                hyp.status = "ruled_out"
            elif hyp is leader and hyp.posterior >= SUFFICIENCY_THRESHOLD and hyp.evidence_for and not hyp.evidence_against:
                hyp.status = "supported"
            elif hyp is leader:
                hyp.status = "leading"
            else:
                hyp.status = "active"

    def leading(self) -> Hypothesis | None:
        if not self.hypotheses:
            return None
        return max(self.hypotheses.values(), key=lambda h: h.posterior)

    def is_sufficient(self) -> bool:
        leader = self.leading()
        return bool(
            leader
            and leader.posterior >= SUFFICIENCY_THRESHOLD
            and leader.evidence_for
            and not leader.evidence_against
        )

    def decide(self, sim: PalletizerSimulator) -> dict[str, Any]:
        leader = self.leading()
        ranked = self.rank_tests(sim)
        next_test = next((r for r in ranked if r["permitted"] and r["useful"]), None)
        blocked = [r for r in ranked if r["useful"] and not r["permitted"]]
        elapsed = time.monotonic() - self.started
        stop_reason: StopReason | None = None
        if self.is_sufficient():
            stop_reason = "sufficient_evidence"
        elif len(self.tests) >= self.max_tests:
            stop_reason = "budget_exhausted"
        elif elapsed > self.timeout_s:
            stop_reason = "timeout"
        elif next_test is None:
            stop_reason = "no_useful_test"
        if stop_reason == "sufficient_evidence":
            rationale = f"{leader.label} reached {leader.posterior:.0%} with supporting test evidence and no contradiction."
        elif stop_reason:
            rationale = {
                "budget_exhausted": f"Test budget of {self.max_tests} reached before sufficient evidence.",
                "timeout": f"Investigation time budget of {self.timeout_s:.0f} s exceeded.",
                "no_useful_test": "No remaining permitted test can discriminate between the remaining hypotheses.",
            }[stop_reason]
        else:
            rationale = f"Leading hypothesis at {leader.posterior:.0%} is below the {SUFFICIENCY_THRESHOLD:.0%} threshold; {next_test['test_id']} has the highest expected information gain ({next_test['expected_gain_bits']} bits)."
        return {
            "decision": "stop" if stop_reason else "continue",
            "stop_reason": stop_reason,
            "leading_hypothesis": leader.id if leader else None,
            "leading_confidence": round(leader.posterior, 4) if leader else 0.0,
            "sufficiency_threshold": SUFFICIENCY_THRESHOLD,
            "next_test": next_test["test_id"] if next_test and not stop_reason else None,
            "tests_used": len(self.tests),
            "test_budget": self.max_tests,
            "blocked_useful_tests": [{"test_id": b["test_id"], "reason": b["permission_reason"]} for b in blocked],
            "human_needed": stop_reason != "sufficient_evidence" if stop_reason else False,
            "rationale": rationale,
        }

    def state(self) -> dict[str, Any]:
        return {
            "fault_family": self.family,
            "hypotheses": sorted((h.as_dict() for h in self.hypotheses.values()), key=lambda h: -h["posterior"]),
            "tests": [t.__dict__ for t in self.tests],
            "adjustments": self.adjustments,
            "sufficient": self.is_sufficient(),
        }
