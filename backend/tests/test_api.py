from fastapi.testclient import TestClient

from app.main import DEMO_COMPANY, app

client = TestClient(app)


def test_health_reports_real_license_list():
    body = client.get("/api/health").json()
    assert body["licensed_count"] == 4070
    assert body["licensed_as_of"] == "2025-06-30"


def test_license_check():
    assert client.get("/api/licenses/check", params={"name": "杭州银行股份有限公司"}).json()["found"]
    assert client.get("/api/licenses/check", params={"name": "x"}).status_code == 422


def test_demo_case_roundtrip():
    demo = client.get("/api/demo").json()
    created = client.post("/api/cases", json=demo)
    assert created.status_code == 200
    body = created.json()
    assert len(body["assertions"]) == 6
    assert client.get(f"/api/cases/{body['id']}").json()["id"] == body["id"]


def test_demo_company_without_text_uses_demo_flyer():
    body = client.post("/api/cases", json={"company_name": DEMO_COMPANY}).json()
    assert len(body["assertions"]) == 6


def test_company_profile_coverage():
    assert client.get("/api/companies/profile", params={"name": DEMO_COMPANY}).json()["covered"]
    assert not client.get("/api/companies/profile", params={"name": "某某科技有限公司"}).json()["covered"]


def test_errors():
    assert client.get("/api/cases/nope").status_code == 404
    assert client.post("/api/cases", json={"company_name": ""}).status_code == 422
