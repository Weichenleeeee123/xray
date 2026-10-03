"""Public omission notice without exposing internal rejected content or counters."""
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.models import ChatMessage, PublicChatMessage
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY


@pytest.mark.parametrize("mode", ["model", "replay", "template", "guard", None])
@pytest.mark.parametrize("not_found", [False, True])
@pytest.mark.parametrize("dropped", [0, 3])
def test_public_omission_flag_is_computed_without_exposing_audit_fields(mode, not_found, dropped):
    original = ChatMessage(role="assistant", text="保留下来的说明。", version=1,
                           created_at="2026-10-03T00:00:00", mode=mode, not_found=not_found,
                           dropped=dropped, rewrites=2, blocked=["被拒绝的内部文本"])
    before = original.model_dump()
    expected = mode in ("model", "replay") and not not_found and dropped > 0
    public = PublicChatMessage.model_validate({**before, "has_omitted_claims": not expected})
    body = public.model_dump(mode="json")
    assert body["has_omitted_claims"] is expected
    assert not {"dropped", "rewrites", "blocked"} & body.keys()
    assert "被拒绝的内部文本" not in public.model_dump_json()
    assert original.model_dump() == before
    assert "has_omitted_claims" not in original.model_dump()


def test_omission_flag_is_a_public_read_only_output_property():
    schema = PublicChatMessage.model_json_schema(mode="serialization")
    assert schema["properties"]["has_omitted_claims"]["type"] == "boolean"
    assert schema["properties"]["has_omitted_claims"]["readOnly"] is True
    assert "has_omitted_claims" not in PublicChatMessage.model_fields
    assert "has_omitted_claims" not in ChatMessage.model_fields
    assert "has_omitted_claims" not in ChatMessage.model_json_schema(mode="serialization")["properties"]


@pytest.mark.parametrize("mode,not_found,dropped,expected", [
    ("model", False, 3, True),
    ("replay", False, 3, True),
    ("model", False, 0, False),
    ("model", True, 3, False),
    ("template", False, 3, False),
    ("guard", False, 3, False),
    (None, False, 3, False),
])
def test_chat_post_case_read_and_request_recovery_expose_only_omission_boolean(
        tmp_path, monkeypatch, mode, not_found, dropped, expected):
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    client = TestClient(main.app)
    created = client.post("/api/cases", json={"company_name": DEMO_COMPANY})
    assert created.status_code == 200
    case_id = created.json()["id"]
    calls = []

    def answer(*args, **kwargs):
        calls.append(True)
        return ChatMessage(role="assistant", text="保留且可以展示的说明。", version=1,
                           created_at="2026-10-03T00:00:00", mode=mode, not_found=not_found,
                           dropped=dropped, rewrites=2, blocked=["不应公开的被拒内容"])

    monkeypatch.setattr(main, "answer", answer)
    url = f"/api/cases/{case_id}/chat"
    payload = {"text": "请说明这一条", "has_omitted_claims": not expected}
    headers = {"Idempotency-Key": "public-omission-check"}
    posted = client.post(url, json=payload, headers=headers)
    assert posted.status_code == 200
    stored_before_reads = main.store._path(case_id).read_bytes()
    case_response = client.get(f"/api/cases/{case_id}")
    recovered = client.get(f"{url}/requests/public-omission-check")
    assert case_response.status_code == recovered.status_code == 200
    assert recovered.json()["status"] == "complete"
    replies = [posted.json(), case_response.json()["chat"][-1], recovered.json()["reply"]]
    assert all(reply == replies[0] for reply in replies)
    for reply in replies:
        assert reply["has_omitted_claims"] is expected
        assert not {"dropped", "rewrites", "blocked"} & reply.keys()
        assert "不应公开的被拒内容" not in json.dumps(reply, ensure_ascii=False)
    assert case_response.json()["chat"][0]["has_omitted_claims"] is False
    assert client.post(url, json=payload, headers=headers).json() == replies[0]
    assert len(calls) == 1
    assert main.store._path(case_id).read_bytes() == stored_before_reads
    stored = json.loads(stored_before_reads)
    assert stored["chat"][-1]["dropped"] == dropped
    assert stored["chat"][-1]["rewrites"] == 2
    assert stored["chat"][-1]["blocked"] == ["不应公开的被拒内容"]
    assert all("has_omitted_claims" not in message for message in stored["chat"])
