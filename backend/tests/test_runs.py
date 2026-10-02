"""A refreshed browser can recover a live case build without submitting again."""
import time

from fastapi.testclient import TestClient

import app.main as main
from tests.helpers import DEMO_COMPANY, SAVINGS_NEED

client = TestClient(main.app)


def _settled(run_id):
    for _ in range(200):
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        state = response.json()
        if state["status"] != "running":
            return state
        time.sleep(.01)
    raise AssertionError("run never settled")


def test_create_run_recovers_persisted_case(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    r = client.post("/api/runs", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    first = client.get(f"/api/runs/{run_id}").json()
    assert first["events"][0]["type"] == "begin"
    settled = _settled(run_id)
    assert settled["status"] == "complete"
    assert settled["case_id"]
    assert client.get(f"/api/cases/{settled['case_id']}").status_code == 200
    assert settled["events"][-1]["type"] == "complete"
    assert settled["events"][-1]["case_id"] == settled["case_id"]
    assert client.get(f"/api/runs/{run_id}?after={len(settled['events'])}").json()["events"] == []


def test_supplement_run_recovers_new_version(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    original = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED}).json()
    r = client.post(f"/api/cases/{original['id']}/runs", json={"kind": "material", "text": "保本保息，年化收益 9%"})
    assert r.status_code == 202
    settled = _settled(r.json()["run_id"])
    assert settled["status"] == "complete"
    assert settled["case_id"] == original["id"]
    assert client.get(f"/api/cases/{original['id']}").json()["current"] == 2


def test_failed_run_has_recoverable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    def broken(*_args, **_kwargs):
        raise RuntimeError("private-provider-detail")
    monkeypatch.setattr(main, "new_case", broken)
    r = client.post("/api/runs", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED})
    settled = _settled(r.json()["run_id"])
    assert settled["status"] == "error"
    assert "private-provider-detail" not in settled["events"][-1]["message"]
    assert settled["case_id"] is None


def test_unknown_run_is_404(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    assert client.get("/api/runs/does-not-exist").status_code == 404
