import json
from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def _load(name: str) -> dict[str, Any]:
    path = get_settings().data_dir / name
    return json.loads(path.read_text(encoding="utf-8-sig"))


def machine_info() -> dict[str, Any]:
    return _load("scenarios.json")["machine"]


def scenarios() -> list[dict[str, Any]]:
    return _load("scenarios.json")["scenarios"]


def default_scenario_id() -> str:
    from app.core.config import get_settings

    return get_settings().plant_scenario


def scenario(scenario_id: str) -> dict[str, Any]:
    for item in scenarios():
        if item["id"] == scenario_id:
            return item
    raise KeyError(f"Unknown scenario '{scenario_id}'")


def fault_model() -> dict[str, Any]:
    return _load("fault_model.json")


def family_for_alarm(alarm_code: str) -> str | None:
    for family_id, family in fault_model()["families"].items():
        if alarm_code in family["alarm_codes"]:
            return family_id
    return None


def public_scenario(item: dict[str, Any]) -> dict[str, Any]:
    """Scenario view safe to show the operator and agent: no hidden truth or hidden state."""
    return {
        "id": item["id"],
        "title": item["title"],
        "summary": item["summary"],
        "operator_symptom": item["operator_symptom"],
        "kind": item.get("kind", "fault"),
        "simulated": True,
    }
