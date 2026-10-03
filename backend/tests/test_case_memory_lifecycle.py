import json

from fastapi.testclient import TestClient

from app import config
import app.main as main
from app.case_memory.store import MemoryStore
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CASE_MEMORY_ENABLED", True)
    monkeypatch.setattr(config, "CASE_MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "identity"))
    monkeypatch.setattr(main, "_launch", lambda work: work())
    return TestClient(main.app)


def test_every_persisted_version_builds_its_own_memory(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    response = client.post("/api/cases", json={"company_name":DEMO_COMPANY,
        "material_text":"合同主体为甲公司，收款对象为甲公司", "need":"我要签合同"})
    assert response.status_code == 200
    cid = response.json()["id"]
    first_path = next((tmp_path / "memory").glob("*.json"))
    before = first_path.read_bytes()
    response = client.post(f"/api/cases/{cid}/supplements", json={"kind":"material",
        "text":"新的付款信息收款对象为乙公司。"})
    assert response.status_code == 200
    versions = sorted(json.loads(p.read_text(encoding="utf-8"))["version_no"] for p in (tmp_path/"memory").glob("*.json"))
    assert versions == [1, 2] and first_path.read_bytes() == before
    assert main.store.get(cid).owner_id
    assert not main._memory_pending


def test_failed_memory_does_not_fail_report_or_change_progress(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    def broken(*args):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(MemoryStore, "get_or_build", broken)
    response = client.post("/api/cases", json={"company_name":DEMO_COMPANY})
    assert response.status_code == 200
    assert client.get(f"/api/cases/{response.json()['id']}").status_code == 200
    assert not main._memory_pending


def test_all_version_saves_use_single_hook():
    from pathlib import Path
    text = Path(main.__file__).read_text(encoding="utf-8")
    assert text.count("store.save(") == 1
    assert text.count("return _persist_case(") == 6


def test_guest_memory_stays_private_and_restore_keeps_one_answer(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "ASSISTANT_CONTEXT_MODE", "selective")
    other = TestClient(main.app)
    created = client.post("/api/cases", json={"company_name": DEMO_COMPANY}).json()
    cid = created["id"]
    assert other.get(f"/api/cases/{cid}").status_code == 404
    assert other.post(f"/api/cases/{cid}/chat", json={"text":"我害怕怎么办"}).status_code == 404
    header = {"Idempotency-Key":"memory-private-request"}
    answer = client.post(f"/api/cases/{cid}/chat", json={"text":"我想存20w但害怕"}, headers=header)
    assert answer.status_code == 200
    assert answer.json()["context_mode"] == "selective"
    assert not any(key in answer.json() for key in ("owner_key","blocked","dropped","rewrites"))
    restored = client.get(f"/api/cases/{cid}/chat/requests/memory-private-request")
    assert restored.status_code == 200 and "selective" in restored.text
    assert other.get(f"/api/cases/{cid}/chat/requests/memory-private-request").status_code == 404
    again = client.post(f"/api/cases/{cid}/chat", json={"text":"我想存20w但害怕"}, headers=header)
    assert again.json() == answer.json()
    assert len(client.get(f"/api/cases/{cid}").json()["chat"]) == 2
    assert len(list((tmp_path/"memory").glob("*.json"))) == 1


def test_manual_resolution_need_change_and_reviews_each_rebuild(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    created = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need":"我要存钱"}).json()
    cid = created["id"]
    target = created["versions"][-1]["judgments"][0]["id"]
    response = client.post(f"/api/cases/{cid}/resolve", json={"judgment_id":target,"action":"clarified","note":"仅测试人工核对入口"})
    assert response.status_code == 200
    assert client.post(f"/api/cases/{cid}/supplements", json={"kind":"need","text":"我现在想去这里工作"}).status_code == 200
    assert client.post("/api/reviews", json={"company":DEMO_COMPANY,"stars":3,"relation":"customer",
        "text":"仅用于独立测试的一条主动公开评价。","author":"synthetic-author"}).status_code == 200
    assert client.post(f"/api/cases/{cid}/reviews").status_code == 200
    memories = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path/"memory").glob("*.json")]
    assert sorted(m["version_no"] for m in memories) == [1,2,3,4]
    second = next(m for m in memories if m["version_no"] == 2)
    assert any(c["payload"].get("judgment",{}).get("state") == "clarified" for c in second["cards"])


def test_prebuilt_start_and_next_bind_memory_to_each_guest(tmp_path, monkeypatch):
    from app import demo_prebuilt
    from tests.helpers import make_case, SAVINGS_NEED, add
    first = make_case(DEMO_COMPANY)
    second = add(first.model_copy(deep=True), "reply", "测试补充回复，关系仍需核对。")
    bundle = {"demo_id":"memory-test","stages":[
        {"events":[],"case":first.model_dump(mode="json"),"supplement":None},
        {"events":[],"case":second.model_dump(mode="json"),"supplement":{"kind":"reply","text":"测试补充回复，关系仍需核对。"}}]}
    client = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(demo_prebuilt, "_bundles", lambda: [bundle])
    a = client.post("/api/cases", json={"company_name":DEMO_COMPANY,"need":SAVINGS_NEED}).json()
    other = TestClient(main.app)
    b = other.post("/api/cases", json={"company_name":DEMO_COMPANY,"need":SAVINGS_NEED}).json()
    assert a["id"] != b["id"]
    assert client.post(f"/api/cases/{a['id']}/supplements", json={"kind":"reply","text":"测试补充回复，关系仍需核对。"}).status_code == 200
    memories = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path/"memory").glob("*.json")]
    assert len(memories) == 3 and len({m["owner_key"] for m in memories}) == 2
    assert {m["overview"]["report_date"] for m in memories if m["version_no"] == 1} == {first.versions[0].created_at}
