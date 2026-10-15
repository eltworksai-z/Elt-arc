import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="aria-test-"))
os.environ["DB_PATH"] = str(_tmp / "test.db")
os.environ["REPORTS_DIR"] = str(_tmp / "reports")
os.environ["EVAL_RUNS_DIR"] = str(_tmp / "eval_runs")
os.environ["OPENAI_API_KEY"] = ""
