import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.llm import LLMError, REQUEST_DEADLINE, remaining_timeout
from app.models import ChatMessage
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY


def test_duplicate_chat_and_recovery_never_call_model_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    client = TestClient(main.app)
    other = TestClient(main.app)
    cid = client.post("/api/cases", json={"company_name": DEMO_COMPANY}).json()["id"]
    entered, release = threading.Event(), threading.Event()
    calls = []
    def response(*args, **kwargs):
        calls.append(True); entered.set(); release.wait(3)
        return ChatMessage(role="assistant", text="可以一起核对。", version=1, created_at="2026-10-03T00:00:00", dropped=3)
    monkeypatch.setattr(main, "answer", response)
    url = f"/api/cases/{cid}/chat"
    body, headers = {"text": "我很担心"}, {"Idempotency-Key": "synthetic-qa-key"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(client.post, url, json=body, headers=headers)
        assert entered.wait(2)
        try:
            assert client.post(url, json=body, headers=headers).status_code == 409
            status_url = f"{url}/requests/synthetic-qa-key"
            assert client.get(status_url).json()["status"] == "running"
            assert other.get(status_url).status_code == 404
        finally:
            release.set()
        result = pending.result().json()
    assert client.post(url, json=body, headers=headers).json() == result
    assert client.post(url, json={"text": "不同问题"}, headers=headers).status_code == 409
    recovered = client.get(status_url).json()
    assert recovered["status"] == "complete" and recovered["reply"] == result
    assert "dropped" not in result and len(calls) == 1
    assert len(main.store.get(cid).chat) == 2


def test_llm_repair_deadline_clamps_timeout_and_stops_new_calls():
    token = REQUEST_DEADLINE.set(time.monotonic() + 2)
    try:
        assert 0 < remaining_timeout(45) <= 2
        REQUEST_DEADLINE.set(time.monotonic() - 1)
        with pytest.raises(LLMError) as err:
            remaining_timeout(45)
        assert err.value.code == "deadline"
    finally:
        REQUEST_DEADLINE.reset(token)
