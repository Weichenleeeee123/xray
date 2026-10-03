from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import accounts, quota
from app.store import CaseStore

PW = "three computer demo password"


@pytest.fixture
def isolated_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.setenv("XRAY_QUOTA_ACCOUNT", "1")
    monkeypatch.setenv("XRAY_QUOTA_GUEST", "1")
    monkeypatch.setenv("XRAY_QUOTA_IP", "1")
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path / "runs")


def test_admin_three_devices_stay_signed_in_and_have_no_daily_quota(isolated_admin):
    created = accounts.register("admin@example.com", PW)
    accounts.grant_admin(created["email"])
    clients = [TestClient(main.app) for _ in range(3)]
    for client in clients:
        response = client.post("/api/auth/login", json={"email": created["email"], "password": PW})
        assert response.status_code == 200
        assert response.json()["account"]["role"] == "admin"
    admin = accounts.load(created["id"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        charges = list(pool.map(lambda _: quota.charge(accounts.owner(admin), admin, "shared-ip"), range(12)))
    assert charges == [[]] * 12
    for client in clients:
        session = client.get("/api/session").json()
        assert session["account"] == {"email": created["email"], "role": "admin"}
        assert session["quota"]["limit"] is None
    clients[0].post("/api/auth/logout")
    assert clients[0].get("/api/session").json()["account"] is None
    for client in clients[1:]:
        assert client.get("/api/session").json()["account"]["role"] == "admin"


def test_public_registration_cannot_self_assign_admin_and_regular_limits_remain(isolated_admin):
    client = TestClient(main.app)
    response = client.post("/api/auth/register", json={"email": "ordinary@example.com", "password": PW,
                                                        "role": "admin", "is_admin": True})
    assert response.status_code == 200
    account = accounts._by_email("ordinary@example.com")
    assert not accounts.is_admin(account)
    owner = accounts.owner(account)
    quota.charge(owner, account, "shared-ip")
    with pytest.raises(accounts.AccountError) as error:
        quota.charge(owner, account, "shared-ip")
    assert error.value.status == 429
    quota.charge("guest-one", None, "shared-ip")
    with pytest.raises(accounts.AccountError):
        quota.charge("guest-two", None, "shared-ip")


def test_grant_preserves_password_sessions_and_cannot_create_unknown_account(isolated_admin):
    account = accounts.register("admin@example.com", PW)
    token = accounts.issue_session(account)
    accounts.grant_admin(" ADMIN@EXAMPLE.COM ")
    accounts.grant_admin(account["email"])
    assert accounts.from_session(token)["role"] == "admin"
    assert accounts.login(account["email"], PW, "test-ip")["pw"] == account["pw"]
    with pytest.raises(accounts.AccountError) as error:
        accounts.grant_admin("missing@example.com")
    assert error.value.status == 404
