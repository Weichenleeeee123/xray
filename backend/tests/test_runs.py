"""A refreshed browser can recover a live case build without submitting again."""
import time
import threading

import pytest

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


def test_failed_run_retains_complete_input_without_repeating_it_in_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    def broken(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(main, "new_case", broken)
    body = {"company_name": DEMO_COMPANY, "need": SAVINGS_NEED,
            "material_title": "合同全文", "material_text": "付款主体待核对\n原始合同第2段"}
    created = client.post("/api/runs", json=body).json()
    settled = _settled(created["run_id"])
    for key, value in body.items():
        assert settled["input"]["body"][key] == value
    assert settled["input"]["kind"] == "create"
    assert all("input" not in event for event in settled["events"])
    assert client.get(f"/api/runs/{created['run_id']}?after=1").json()["input"] is None


def test_legacy_journal_without_saved_input_remains_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    run_id = "b" * 24
    main.runs.append(tmp_path, run_id, {"type": "begin", "company": DEMO_COMPANY, "steps": []})
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["status"] == "interrupted"
    assert result["input"] is None


def test_supplement_keeps_case_identity_and_full_original_material(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    original = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED}).json()
    body = {"kind": "material", "title": "补充合同", "text": "第一段：保本保息\n第二段：年化收益 9%"}
    created = client.post(f"/api/cases/{original['id']}/runs", json=body,
                          headers={"Idempotency-Key": "supplement-original-input"}).json()
    settled = _settled(created["run_id"])
    assert settled["input"]["kind"] == "supplement"
    assert settled["input"]["case_id"] == original["id"]
    assert settled["version"] == 2
    for key, value in body.items():
        assert settled["input"]["body"][key] == value
    duplicate = client.post(f"/api/cases/{original['id']}/runs", json=body,
                            headers={"Idempotency-Key": "supplement-original-input"}).json()
    assert duplicate["run_id"] == created["run_id"]


def test_failed_original_input_write_releases_run_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(main, "_run_slots", slots)
    def broken(*_args, **_kwargs):
        raise OSError("simulated storage failure")
    monkeypatch.setattr(main.runs, "save_input", broken)
    run_id = "c" * 24
    with pytest.raises(OSError):
        main._start_run({"type": "begin"}, lambda: None, run_id,
                        original_input={"kind": "create", "body": {}})
    assert run_id not in main._active_runs
    assert slots.acquire(blocking=False)
    slots.release()
