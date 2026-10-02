"""Exercise existing A routes with B services; fixtures are explicitly synthetic."""
import json

from fastapi.testclient import TestClient

from app import main
from tests.test_llm_assistant import FakeLLM


def test_http_chat_rejects_fabrication_without_changing_report(tmp_path, monkeypatch):
    client = TestClient(main.app)
    demo = client.get("/api/demo", params={"case": "C"}).json()
    case = client.post("/api/cases", json=demo["input"]).json()
    monkeypatch.setattr(main, "llm", FakeLLM([json.dumps({
        "segments": [{"text": "老板已经逃走", "citations": ["R999"]}]
    })], tmp_path))
    result = client.post(f'/api/cases/{case["id"]}/chat', json={"text": "老板去哪里了"})
    assert result.status_code == 200
    assert result.json()["not_found"] and "老板已经逃走" not in result.json()["text"]
    after = client.get(f'/api/cases/{case["id"]}').json()
    assert after["versions"] == case["versions"] and after["raw"] == case["raw"]
    assert len(after["chat"]) == 2


def test_http_old_version_reference_after_supplement(tmp_path, monkeypatch):
    client = TestClient(main.app)
    demo = client.get("/api/demo", params={"case": "C"}).json()
    case = client.post("/api/cases", json=demo["input"]).json()
    cid = case["id"]
    updated = client.post(f"/api/cases/{cid}/supplements", json=demo["supplements"][0]).json()
    assert updated["current"] == 2
    monkeypatch.setattr(main, "llm", FakeLLM([], tmp_path))
    reply = client.post(f"/api/cases/{cid}/chat", json={
        "text": "这一条什么意思", "refs": ["v:1:assertion:A2"]}).json()
    assert reply["version"] == 1 and "A2" in reply["citations"]
    assert client.get(f"/api/cases/{cid}").json()["current"] == 2
