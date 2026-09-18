"""Render every page headlessly with Streamlit's AppTest, in two states:
an empty fleet log (what a fresh cloud instance sees) and a populated one.
Any exception on any page fails the test. This is the "zero errors" gate."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest  # noqa: E402

from core import events  # noqa: E402

PAGES = ["", "fleet", "door", "shm", "rail", "acv", "monitor", "validation", "submission", "method"]


def _run(page: str, tmp_events: Path) -> AppTest:
    os.environ["NEBULA_TEST_PAGE"] = page
    os.environ["NEBULA_EVENTS_PATH"] = str(tmp_events)
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    return at


def _errors(at: AppTest) -> list[str]:
    return [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_empty_log(page, tmp_path):
    at = _run(page, tmp_path / "events.jsonl")
    assert not _errors(at), _errors(at)


@pytest.mark.parametrize("page", ["", "fleet"])
def test_page_renders_with_populated_log(page, tmp_path):
    p = tmp_path / "events.jsonl"
    events.EVENTS_PATH = p
    events.ACTIONS_PATH = tmp_path / "actions.jsonl"
    rows = [{"time": events.now().isoformat(), "analysed_at": events.now().isoformat(), "subsystem": "door",
             "subsystem_name": "Door", "state": "alert", "severity": 0.9, "title": f"Door cycle {i} abnormal",
             "detail": "x", "file_id": "Test.csv", "train": "NSL-01", "line": "NSL", "station": "BISHAN",
             "source": "run", "dataset": "Upload test"} for i in range(3)]
    rows.append({**rows[0], "title": "dup"})            # a repeat identity to exercise de-duplication
    rows.append({**rows[0], "title": "dup"})
    events.append(rows)
    at = _run(page, p)
    assert not _errors(at), _errors(at)


@pytest.mark.skipif(not (ROOT / "predictions" / "analysis_cache.pkl").exists(), reason="no cached run")
@pytest.mark.parametrize("page", ["", "fleet", "door", "shm", "rail", "acv"])
def test_page_renders_with_session_results(page, tmp_path):
    """Every page with real results in session (the cached competition run), so the
    schematics, verdict cards, charts and tables all execute."""
    from core import cache
    os.environ["NEBULA_TEST_PAGE"] = page
    os.environ["NEBULA_EVENTS_PATH"] = str(tmp_path / "events.jsonl")
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
    for k, v in (cache.load() or {}).items():
        at.session_state[f"{k}_result"] = v
    at.run()
    assert not _errors(at), _errors(at)
