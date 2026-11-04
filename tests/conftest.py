import datetime as dt
import itertools
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Make sure the pinned ontology is present (CI also fetches it explicitly).
if not (ROOT / "vendor" / "rfq-ontology" / "ontology").exists():
    import os
    if not os.environ.get("RFQ_ONTOLOGY_DIR"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_ontology.py")], check=True)

from rfq_agents.pla import PLA  # noqa: E402
from rfq_agents.retry import FailureInjector, RetryPolicy  # noqa: E402
from rfq_agents.store import RunStore  # noqa: E402

QUOTE_DATE = "2026-10-27"


class Clock:
    def __init__(self):
        self.t = itertools.count()

    def __call__(self):
        return dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=next(self.t))


@pytest.fixture
def db(tmp_path):
    return tmp_path / "pla.sqlite"


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def make_pla(db, tmp_path, sleeps):
    """Factory: a fresh PLA (new store connection, like a new process) over the same database."""
    def _make(injector=None, max_attempts=3, llm=None, planner=None):
        import random
        policy = RetryPolicy(max_attempts=max_attempts, base_delay=0.5, max_delay=8, sleep=sleeps.append,
                             rng=random.Random(7))
        return PLA(RunStore(db), llm=llm, planner=planner, retry=policy, injector=injector or FailureInjector(),
                   clock=Clock(), out_dir=tmp_path / "out")
    return _make


def runs_of(state, tool):
    return [r for r in state["runs"] if r["tool"] == tool]


def open_issues(state, severity=None):
    return [i for i in state["issues"].values() if i["status"] == "open" and (severity is None or i["severity"] == severity)]
