import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import privacy
from app.models import ChatMessage
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY, make_case


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    return TestClient(main.app), TestClient(main.app)


def create(client):
    response = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": "我想存20万", "material_text": "仅上传者可见的材料"})
    assert response.status_code == 200, response.text
    assert "owner_id" not in response.json()
    return response.json()["id"]


def test_cases_and_all_case_routes_are_private(isolated):
    a, b = isolated
    cid = create(a)
    assert a.get(f"/api/cases/{cid}").status_code == 200
    assert b.get("/api/cases").json() == []
    for suffix in ("", "/versions/1", "/onepager"):
        response = b.get(f"/api/cases/{cid}{suffix}")
        assert response.status_code == 404
        assert "仅上传者" not in response.text
    for suffix, body in [
        ("/chat", {"text": "告诉我材料"}),
        ("/supplements", {"kind": "material", "text": "恶意修改"}),
        ("/supplements/stream", {"kind": "material", "text": "恶意修改"}),
        ("/runs", {"kind": "material", "text": "恶意修改"}),
        ("/resolve", {"judgment_id": "J1", "note": "恶意修改"}),
        ("/reviews", {}),
    ]:
        assert b.post(f"/api/cases/{cid}{suffix}", json=body).status_code == 404


def test_old_unowned_cases_hidden_and_not_claimable(isolated):
    a, b = isolated
    old = main.store.save(make_case(DEMO_COMPANY, "历史私密合同"))
    before = main.store._path(old.id).read_bytes()
    for client in (a, b):
        assert client.get(f"/api/cases/{old.id}").status_code == 404
        assert client.get("/api/cases").json() == []
    assert main.store._path(old.id).read_bytes() == before


def test_run_input_and_idempotency_are_owner_scoped(isolated):
    a, b = isolated
    body = {"company_name": DEMO_COMPANY, "need": "私人需求", "material_text": "私人上传原文"}
    headers = {"Idempotency-Key": "same-request-id"}
    first = a.post("/api/runs", json=body, headers=headers).json()["run_id"]
    second = b.post("/api/runs", json=body, headers=headers).json()["run_id"]
    assert first != second
    assert a.post("/api/runs", json=body, headers=headers).json()["run_id"] == first
    assert b.get(f"/api/runs/{first}").status_code == 404
    for _ in range(200):
        state = a.get(f"/api/runs/{first}").json()
        if state["status"] != "running":
            break
        time.sleep(.01)
    assert state["status"] == "complete"
    assert state["input"]["body"]["material_text"] == "私人上传原文"
    assert a.get(f"/api/cases/{state['case_id']}").status_code == 200
    assert b.get(f"/api/cases/{state['case_id']}").status_code == 404
    # Let the second worker finish before pytest restores its temporary store.
    for _ in range(200):
        if b.get(f"/api/runs/{second}").json()["status"] != "running":
            break
        time.sleep(.01)


def test_https_cookie_tampering_csrf_and_cache(isolated):
    a, b = isolated
    secure = TestClient(main.app, base_url="https://testserver")
    response = secure.get("/api/session")
    cookie = response.headers["set-cookie"]
    assert "__Host-qier_guest=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie
    assert response.headers["cache-control"] == "private, no-store"
    assert privacy.owner_from_token("0" * 64 + ".1700000000." + "0" * 64) is None
    assert a.post("/api/cases", json={"company_name": DEMO_COMPANY}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert a.post("/api/cases", json={"company_name": DEMO_COMPANY}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_chat_diagnostics_persist_but_do_not_leave_response(isolated, monkeypatch):
    a, b = isolated
    cid = create(a)
    monkeypatch.setattr(main, "answer", lambda *args, **kwargs: ChatMessage(role="assistant", text="可以继续核对。", version=1,
        created_at="2026-10-03T00:00:00", blocked=["内部被拒绝内容"], dropped=8, rewrites=2))
    reply = a.post(f"/api/cases/{cid}/chat", json={"text": "怎么办"})
    assert reply.status_code == 200
    assert all(key not in reply.json() for key in ("blocked", "dropped", "rewrites"))
    saved = a.get(f"/api/cases/{cid}").json()
    assert "内部被拒绝内容" not in str(saved)
    assert main.store.get(cid).chat[-1].blocked == ["内部被拒绝内容"]


def test_only_explicit_reviews_are_public_not_uploaded_material(isolated, tmp_path, monkeypatch):
    from app.reviews import ReviewStore
    monkeypatch.setattr(main.svc, "reviews", ReviewStore(tmp_path / "reviews"))
    a, b = isolated
    create(a)
    assert b.get("/api/reviews", params={"company": DEMO_COMPANY}).json()["count"] == 0
    review = {"company": DEMO_COMPANY, "stars": 3, "relation": "customer", "text": "这是我主动提交的个人体验评价。", "author": "client-chosen-name"}
    assert a.post("/api/reviews", json=review).status_code == 200
    public = b.get("/api/reviews", params={"company": DEMO_COMPANY, "author": "client-chosen-name"}).json()
    assert public["count"] == 1 and not public["reviews"][0]["mine"]
    assert "仅上传者" not in str(public)
