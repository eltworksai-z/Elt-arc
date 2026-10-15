from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    openai_api_key: str = ""

    live_model: str = "gpt-live-1"
    live_voice: str = "marin"
    agent_model: str = "gpt-5.6-terra"
    fast_model: str = "gpt-5.6-luna"
    judge_model: str = "gpt-5.6-terra"
    embedding_model: str = "text-embedding-3-large"

    agent_reasoning_effort: str = "medium"
    max_diagnostic_tests: int = 6
    investigation_timeout_s: int = 240
    max_agent_turns: int = 30

    cors_origins: str = "http://localhost:3000"
    plant_scenario: str = "gripper_feedback_missing"

    data_dir: Path = DATA_DIR
    db_path: Path = DATA_DIR / "aria.db"
    manuals_dir: Path = DATA_DIR / "manuals"
    reports_dir: Path = DATA_DIR / "reports"
    incidents_dir: Path = DATA_DIR / "incidents"
    eval_runs_dir: Path = DATA_DIR / "eval_runs"

    @property
    def has_api_key(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for path in (settings.manuals_dir, settings.reports_dir, settings.incidents_dir, settings.eval_runs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return settings
