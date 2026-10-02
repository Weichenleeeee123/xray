"""预制示例：输入一字不差就交出预制案卷、回放研究过程；按顺序补充交出预制的下一版；改过输入就照常现查。"""
import json

import pytest
from fastapi.testclient import TestClient

from app import demo_prebuilt, progress
from app.main import app
from app.models import CaseIn, SupplementIn
from tests.helpers import DEMO_COMPANY, SAVINGS_NEED, add, make_case

REPLY = "我们是正规公司，请放心，不会有问题的。"


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_prebuilt, "DIR", tmp_path)
    case = make_case(DEMO_COMPANY)
    first = case.model_copy(deep=True)
    add(case, "reply", REPLY)
    events = [{"type": "step", "id": "lists", "label": "持牌名单", "phase": "start", "t": 0.0},
              {"type": "step", "id": "lists", "label": "持牌名单", "phase": "done", "t": 0.05}]
    data = {"demo_id": "T", "stages": [
        {"supplement": None, "events": events, "case": first.model_dump(mode="json")},
        {"supplement": {"kind": "reply", "text": REPLY, "title": None}, "events": events,
         "case": case.model_dump(mode="json")}]}
    (tmp_path / "T.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def test_same_input_gets_the_prebuilt_case_and_replays_progress(bundle):
    hit = demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED))
    assert hit is not None
    seen = []
    with progress.reporting(seen.append):
        case = demo_prebuilt.start_case(hit, "browser-1")
    assert [e["phase"] for e in seen] == ["start", "done"] and all("t" not in e for e in seen)
    assert case.owner_id == "browser-1" and case.id != bundle["stages"][0]["case"]["id"] and len(case.versions) == 1
    assert case.versions[0].created_at == bundle["stages"][0]["case"]["versions"][0]["created_at"]


def test_changed_input_is_researched_live(bundle):
    assert demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED + "，三个月内要用")) is None
    assert demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED, refresh_sources=True)) is None
    assert demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED, scenario="job")) is None


def test_the_next_prepared_supplement_gets_the_prebuilt_version(bundle):
    case = demo_prebuilt.start_case(bundle, "browser-1")
    assert demo_prebuilt.for_supplement(case, SupplementIn(kind="reply", text="另一段回复，内容不同")) is None
    hit = demo_prebuilt.for_supplement(case, SupplementIn(kind="reply", text=REPLY))
    assert hit is not None and hit[1] == 1
    nxt = demo_prebuilt.next_case(case, *hit)
    assert nxt.id == case.id and nxt.owner_id == "browser-1" and len(nxt.versions) == 2


def test_api_hands_out_the_prebuilt_case(bundle):
    client = TestClient(app)   # 不用 with：那会触发应用关闭，影响后面的测试
    lines = client.post("/api/cases/stream", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED}).text.splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["type"] for e in events][:3] == ["begin", "step", "step"] and events[-1]["type"] == "case"
    built = events[-1]["case"]
    assert built["versions"][0]["created_at"] == bundle["stages"][0]["case"]["versions"][0]["created_at"]


def test_turned_off_means_live(bundle, monkeypatch):
    monkeypatch.setenv("XRAY_DEMO_PREBUILT", "0")
    assert demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED)) is None
