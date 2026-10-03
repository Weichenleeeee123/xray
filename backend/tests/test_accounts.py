import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import accounts
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY

PW = "correct horse"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    return lambda: TestClient(main.app)


def create(client):
    response = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": "我想存20万"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def register(client, email="Me@Example.com", password=PW):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_register_login_and_cases_follow_the_account(isolated):
    phone, laptop = isolated(), isolated()
    assert register(phone)["account"] == {"email": "me@example.com"}
    cid = create(phone)
    assert laptop.get("/api/cases").json() == []
    response = laptop.post("/api/auth/login", json={"email": " ME@example.com ", "password": PW})
    assert response.status_code == 200
    assert [c["id"] for c in laptop.get("/api/cases").json()] == [cid]
    assert laptop.get(f"/api/cases/{cid}").status_code == 200
    session = laptop.get("/api/session").json()
    assert session["account"] == {"email": "me@example.com"} and session["cross_device"] is True


def test_password_is_never_stored_in_clear_and_duplicates_are_refused(isolated, tmp_path):
    client = isolated()
    register(client)
    assert client.post("/api/auth/register", json={"email": "me@example.com", "password": PW}).status_code == 409
    stored = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "private" / "accounts").glob("*.json"))
    assert PW not in stored and "scrypt$" in stored
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": PW}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_wrong_password_locks_after_five_failures(isolated):
    client = isolated()
    register(client)
    other = isolated()
    for _ in range(5):
        assert other.post("/api/auth/login", json={"email": "me@example.com", "password": "wrong password"}).status_code == 401
    locked = other.post("/api/auth/login", json={"email": "me@example.com", "password": PW})
    assert locked.status_code == 429
    # 没注册的邮箱和密码错误回同一句话
    unknown = other.post("/api/auth/login", json={"email": "nobody@example.com", "password": PW})
    assert unknown.status_code == 401 and unknown.json()["detail"] == "邮箱或密码不对"


def test_guest_cases_merge_only_after_confirmation(isolated):
    client = isolated()
    guest_case = create(client)
    result = register(client)
    assert result["guest_cases"] == 1
    assert client.get("/api/cases").json() == []          # 没确认之前不并
    assert client.get("/api/session").json()["guest_cases"] == 1
    assert client.post("/api/auth/merge").json() == {"moved": 1}
    assert [c["id"] for c in client.get("/api/cases").json()] == [guest_case]
    laptop = isolated()
    laptop.post("/api/auth/login", json={"email": "me@example.com", "password": PW})
    assert laptop.get(f"/api/cases/{guest_case}").status_code == 200


def test_logout_drops_account_and_rotates_guest(isolated):
    client = isolated()
    guest_case = create(client)
    register(client)
    assert client.post("/api/auth/logout").status_code == 200
    session = client.get("/api/session").json()
    assert session["account"] is None
    assert client.get(f"/api/cases/{guest_case}").status_code == 404   # 退出后连匿名身份也换了
    assert client.post("/api/auth/merge").status_code == 401


def test_password_change_signs_out_other_devices(isolated):
    a, b = isolated(), isolated()
    register(a)
    b.post("/api/auth/login", json={"email": "me@example.com", "password": PW})
    assert a.post("/api/auth/password", json={"old": "wrong one!", "new": "new password"}).status_code == 401
    assert a.post("/api/auth/password", json={"old": PW, "new": "new password"}).status_code == 200
    assert a.get("/api/session").json()["account"] is not None   # 改密码的这台换了新 cookie
    assert b.get("/api/session").json()["account"] is None
    assert b.post("/api/auth/login", json={"email": "me@example.com", "password": "new password"}).status_code == 200


def test_forgot_password_sends_a_single_use_link(isolated, monkeypatch):
    sent = []
    monkeypatch.setenv("XRAY_RESEND_KEY", "test-key")
    monkeypatch.setenv("XRAY_PUBLIC_URL", "https://qier.asia")
    monkeypatch.setattr(accounts, "send_mail", lambda to, subject, text: sent.append((to, text)))
    client = isolated()
    register(client)
    same = "如果这个邮箱注册过"
    assert same in client.post("/api/auth/forgot", json={"email": "nobody@example.com"}).json()["message"]
    assert same in client.post("/api/auth/forgot", json={"email": "me@example.com"}).json()["message"]
    for _ in range(100):
        if sent:
            break
        time.sleep(.01)
    assert [to for to, _ in sent] == ["me@example.com"]
    link = sent[0][1].split("https://qier.asia/xray/#/reset?t=")[1].split()[0]
    other = isolated()
    assert other.post("/api/auth/reset", json={"token": link, "password": "brand new pw"}).status_code == 200
    assert other.get("/api/session").json()["account"] == {"email": "me@example.com"}
    assert client.get("/api/session").json()["account"] is None          # 旧登录失效
    assert other.post("/api/auth/reset", json={"token": link, "password": "another pw!"}).status_code == 400


def test_reset_token_expires_and_mail_off_is_explicit(isolated):
    client = isolated()
    register(client)
    account = accounts._by_email("me@example.com")
    old = accounts.reset_token(account, now=time.time() - accounts.RESET_TTL - 5)
    assert client.post("/api/auth/reset", json={"token": old, "password": "brand new pw"}).status_code == 400
    assert client.post("/api/auth/forgot", json={"email": "me@example.com"}).status_code == 503


def test_delete_account(isolated):
    client = isolated()
    register(client)
    assert client.post("/api/auth/delete", json={"password": "wrong pass"}).status_code == 401
    assert client.post("/api/auth/delete", json={"password": PW}).status_code == 200
    assert client.get("/api/session").json()["account"] is None
    assert isolated().post("/api/auth/login", json={"email": "me@example.com", "password": PW}).status_code == 401


def test_library_syncs_per_account(isolated):
    client = isolated()
    assert client.get("/api/me/library").status_code == 401
    register(client)
    entry = {"id": "dishonest", "term": "失信被执行人", "plain": "欠钱不还", "origin": None, "savedAt": "2026-10-03T00:00:00Z",
             "seen": [{"caseId": "abc", "version": 2, "company": "巨鲸"}]}
    assert client.put("/api/me/library", json=[entry]).status_code == 200
    laptop = isolated()
    laptop.post("/api/auth/login", json={"email": "me@example.com", "password": PW})
    assert laptop.get("/api/me/library").json()[0]["term"] == "失信被执行人"


def test_daily_quota_for_guests_and_accounts(isolated, monkeypatch):
    monkeypatch.setenv("XRAY_QUOTA_GUEST", "2")
    monkeypatch.setenv("XRAY_QUOTA_IP", "3")
    monkeypatch.setenv("XRAY_QUOTA_ACCOUNT", "1")
    a, b = isolated(), isolated()
    create(a)
    create(a)
    blocked = a.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": "我想存20万"})
    assert blocked.status_code == 429 and "登录后" in blocked.json()["detail"]
    assert a.get("/api/session").json()["quota"] == {"used": 2, "limit": 2}
    create(b)                                             # 同一个 IP 的第 3 次
    assert b.post("/api/cases", json={"company_name": DEMO_COMPANY}).status_code == 429   # IP 上限
    register(b)                                           # 登录后按账号算，不受 IP 上限
    create(b)
    assert b.post("/api/cases", json={"company_name": DEMO_COMPANY}).status_code == 429
    assert b.get("/api/session").json()["quota"] == {"used": 1, "limit": 1}


def test_prebuilt_demo_replays_are_free(isolated, monkeypatch):
    monkeypatch.setenv("XRAY_QUOTA_GUEST", "1")
    monkeypatch.setattr(main.demo_prebuilt, "for_create", lambda body: {"demo": True})
    monkeypatch.setattr(main, "_inline", lambda work: (_ for _ in ()).throw(main.HTTPException(503, "busy")))
    client = isolated()
    for _ in range(3):
        assert client.post("/api/cases", json={"company_name": DEMO_COMPANY}).status_code == 503
    assert client.get("/api/session").json()["quota"]["used"] == 0
    monkeypatch.setattr(main.demo_prebuilt, "for_create", lambda body: None)   # 真研究启动失败：退回这一次
    assert client.post("/api/cases", json={"company_name": DEMO_COMPANY}).status_code == 503
    assert client.get("/api/session").json()["quota"]["used"] == 0


def test_https_session_cookie_is_host_only_and_httponly(isolated):
    secure = TestClient(main.app, base_url="https://testserver")
    response = secure.post("/api/auth/register", json={"email": "s@example.com", "password": PW})
    cookie = response.headers["set-cookie"]
    assert "__Host-qier_user=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "Path=/" in cookie
    assert secure.get("/api/session").json()["account"] == {"email": "s@example.com"}
    secure.cookies.set("__Host-qier_user", "f" * 24 + ".1.1700000000." + "0" * 64)
    stale = secure.get("/api/session")
    assert stale.json()["account"] is None and "__Host-qier_user=;" in stale.headers.get("set-cookie", "").replace('""', "")
