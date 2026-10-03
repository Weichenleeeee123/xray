"""预制示例：输入一字不差就交出预制案卷、回放研究过程；按顺序补充交出预制的下一版；改过输入就照常现查。"""
import json
from copy import deepcopy
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import demo_prebuilt, progress
import app.main as main
from app.analysis.pipeline import refresh_reviews, resolve
from app.main import app
from app.models import Case, CaseIn, Glance, ResolveIn, ReviewIn, SupplementIn
from app.reviews import ReviewStore
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY, SAVINGS_NEED, add, make_case, svc

REPLY = "我们是正规公司，请放心，不会有问题的。"
BUILT_AT = "2026-09-30 10:20"
LEGACY_NOTE = f"预制示例：这份报告在 {BUILT_AT} 生成，现场演示直接展示，不重新联网查询；记录截至当时。"


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_prebuilt, "DIR", tmp_path)
    case = make_case(DEMO_COMPANY)
    case.versions[0].notes.insert(0, LEGACY_NOTE)
    case.versions[0].glance = Glance(mode="model", short={"credit.status": "原快照短句"})
    first = case.model_copy(deep=True)
    add(case, "reply", REPLY)
    events = [{"type": "step", "id": "lists", "label": "持牌名单", "phase": "start", "t": 0.0},
              {"type": "step", "id": "lists", "label": "持牌名单", "phase": "done", "t": 0.05}]
    data = {"demo_id": "T", "built_at": BUILT_AT, "material_pipeline": demo_prebuilt.MATERIAL_PIPELINE, "stages": [
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
    assert seen[0] == {"type": "prebuilt", "demo_id": "T", "built_at": BUILT_AT}
    assert [e["phase"] for e in seen[1:]] == ["start", "done"] and all("t" not in e for e in seen)
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


def test_old_material_pipeline_bundle_is_not_replayed_as_current_analysis(bundle, monkeypatch):
    case = demo_prebuilt.start_case(bundle, "browser-1")
    legacy = deepcopy(bundle)
    legacy.pop("material_pipeline", None)
    monkeypatch.setattr(demo_prebuilt, "_bundles", lambda: [legacy])
    assert demo_prebuilt.for_supplement(case, SupplementIn(kind="reply", text=REPLY)) is None


def test_later_prebuilt_supplement_keeps_its_own_build_date_and_old_snapshot(bundle):
    bundle["built_at"] = "2026-10-03 04:55"
    bundle["stages"][1]["built_at"] = "2026-10-03 15:43"
    case = demo_prebuilt.start_case(bundle, "browser-1")
    assert case.versions[0].prebuilt.built_at == "2026-10-03 04:55"
    nxt = demo_prebuilt.next_case(case, bundle, 1)
    assert nxt.versions[0].prebuilt.built_at == "2026-10-03 04:55"
    assert nxt.versions[1].prebuilt.built_at == "2026-10-03 15:43"


def test_api_hands_out_the_prebuilt_case(bundle):
    client = TestClient(app)   # 不用 with：那会触发应用关闭，影响后面的测试
    lines = client.post("/api/cases/stream", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED}).text.splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["type"] for e in events][:4] == ["begin", "prebuilt", "step", "step"] and events[-1]["type"] == "case"
    built = events[-1]["case"]
    assert built["versions"][0]["created_at"] == bundle["stages"][0]["case"]["versions"][0]["created_at"]


def test_turned_off_means_live(bundle, monkeypatch):
    monkeypatch.setenv("XRAY_DEMO_PREBUILT", "0")
    assert demo_prebuilt.for_create(CaseIn(company_name=DEMO_COMPANY, need=SAVINGS_NEED)) is None


def test_prebuilt_metadata_does_not_rewrite_snapshot_facts_or_package(bundle):
    before = deepcopy(bundle)
    case = demo_prebuilt.start_case(bundle, "browser-1")
    assert case.versions[0].prebuilt.model_dump() == {"demo_id": "T", "built_at": BUILT_AT}
    original = deepcopy(bundle["stages"][0]["case"]["versions"][0])
    original.pop("prebuilt", None)
    assert case.versions[0].model_dump(mode="json", exclude={"prebuilt"}) == original
    assert [r.model_dump(mode="json") for r in case.raw] == bundle["stages"][0]["case"]["raw"]
    assert bundle == before


@pytest.mark.parametrize("missing", [("built_at",), ("demo_id", "built_at")])
def test_old_package_without_metadata_is_still_marked_as_prebuilt(bundle, missing):
    for field in missing:
        bundle.pop(field)
    case = demo_prebuilt.start_case(bundle, "browser-1")
    assert case.versions[0].prebuilt is not None
    assert case.versions[0].prebuilt.built_at is None
    assert case.versions[0].prebuilt.demo_id == bundle.get("demo_id")
    assert case.versions[0].notes[0] == LEGACY_NOTE


def test_provenance_is_emitted_before_any_replay_wait(bundle, monkeypatch):
    history = []
    monkeypatch.setattr(demo_prebuilt, "time", SimpleNamespace(
        monotonic=lambda: 0.0, sleep=lambda seconds: history.append(("wait", seconds))))
    bundle["stages"][0]["events"][0]["t"] = 0.01
    with progress.reporting(lambda event: history.append(("event", event))):
        demo_prebuilt.start_case(bundle, "browser-1")
    assert history[0] == ("event", {"type": "prebuilt", "demo_id": "T", "built_at": BUILT_AT})
    assert history[1][0] == "wait"
    steps = [value for kind, value in history if kind == "event" and value["type"] == "step"]
    assert steps == [{k: v for k, v in event.items() if k != "t"}
                     for event in bundle["stages"][0]["events"]]


def test_prepared_supplement_preserves_saved_versions_and_all_old_raws(bundle):
    case = demo_prebuilt.start_case(bundle, "browser-1")
    case.versions[0].notes.append("保留这条保存后的说明")
    case.raw.append(case.raw[0].model_copy(update={"id": "R999", "title": "原案卷附录"}, deep=True))
    case.versions[0].raw_ids.append("R999")
    before = case.model_dump(mode="json")
    nxt = demo_prebuilt.next_case(case, bundle, 1)
    assert nxt.versions[0].model_dump(mode="json") == before["versions"][0]
    assert [r.model_dump(mode="json") for r in nxt.raw[:len(case.raw)]] == before["raw"]
    assert nxt.versions[-1].prebuilt.model_dump() == {"demo_id": "T", "built_at": BUILT_AT}
    original = deepcopy(bundle["stages"][1]["case"]["versions"][-1])
    original.pop("prebuilt", None)
    assert nxt.versions[-1].model_dump(mode="json", exclude={"prebuilt"}) == original
    assert {rid for v in nxt.versions for rid in v.raw_ids} <= {r.id for r in nxt.raw}
    assert len({r.id for r in nxt.raw}) == len(nxt.raw)
    assert case.model_dump(mode="json") == before


def test_prepared_supplement_rejects_changed_content_at_an_existing_raw_id(bundle):
    case = demo_prebuilt.start_case(bundle, "browser-1")
    before = case.model_dump(mode="json")
    bundle["stages"][1]["case"]["raw"][0]["title"] = "同一个编号却换了原始资料"
    with pytest.raises(ValueError, match="原始记录"):
        demo_prebuilt.next_case(case, bundle, 1)
    assert case.model_dump(mode="json") == before


@pytest.mark.parametrize("refresh", [False, True])
def test_real_supplement_does_not_inherit_prebuilt_or_change_old_version(bundle, tmp_path, monkeypatch, refresh):
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    case = demo_prebuilt.start_case(bundle, "browser-1")
    before = case.versions[0].model_dump(mode="json")
    body = SupplementIn(kind="reply", text=REPLY if refresh else "另一段回复，请提供合同第六条。", refresh_sources=refresh)
    assert demo_prebuilt.for_supplement(case, body) is None
    result = main._supplement(case, body)
    assert result.versions[-1].prebuilt is None
    assert result.versions[0].model_dump(mode="json") == before


def test_timestamp_match_alone_does_not_turn_a_real_version_into_a_prebuilt_sequence(bundle):
    case = Case.model_validate(bundle["stages"][0]["case"])
    assert case.versions[0].prebuilt is None
    assert demo_prebuilt.for_supplement(case, SupplementIn(kind="reply", text=REPLY)) is None


def test_review_refresh_does_not_inherit_prebuilt(bundle, tmp_path):
    case = demo_prebuilt.start_case(bundle, "browser-1")
    before = case.versions[0].model_dump(mode="json")
    reviews = ReviewStore(tmp_path / "reviews")
    reviews.add(ReviewIn(company=DEMO_COMPANY, stars=3, relation="customer",
                         text="已收到合同，部分条款还需要进一步核对。", author="browser-review"))
    updated = refresh_reviews(case, replace(svc, reviews=reviews))
    assert updated.versions[-1].prebuilt is None
    assert updated.versions[0].model_dump(mode="json") == before


@pytest.mark.parametrize("legacy", [False, True])
def test_resolve_is_a_new_human_version_with_snapshot_origin_in_notes(bundle, legacy):
    case = (Case.model_validate(bundle["stages"][0]["case"]) if legacy
            else demo_prebuilt.start_case(bundle, "browser-1"))
    before = case.model_dump(mode="json")
    updated = resolve(case, ResolveIn(judgment_id=case.versions[0].judgments[0].id,
                                     action="recheck", by="核对者", note="需要补原件"))
    assert updated.versions[-1].prebuilt is None
    assert any(n.startswith("基于预制快照") and "未重新联网查询" in n for n in updated.versions[-1].notes)
    assert not any(n.startswith("预制示例") for n in updated.versions[-1].notes)
    assert any(LEGACY_NOTE in n for n in updated.versions[-1].notes)
    assert updated.versions[0].model_dump(mode="json") == before["versions"][0]
    assert [r.model_dump(mode="json") for r in updated.raw] == before["raw"]


@pytest.mark.parametrize("transport", ["ordinary", "stream", "polling"])
def test_api_transports_expose_only_server_prebuilt_metadata(bundle, tmp_path, monkeypatch, transport):
    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setattr(main, "RUNS_DIR", tmp_path / "runs")
    client = TestClient(app)
    body = {"company_name": DEMO_COMPANY, "need": SAVINGS_NEED,
            "prebuilt": {"demo_id": "untrusted", "built_at": "tomorrow"}}
    events = []
    if transport == "ordinary":
        response = client.post("/api/cases", json=body)
        assert response.status_code == 200
        saved = response.json()
    elif transport == "stream":
        response = client.post("/api/cases/stream", json=body)
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        saved = events[-1]["case"]
    else:
        completed = Event()
        original_append = main.runs.append

        def append(directory, run_id, event):
            result = original_append(directory, run_id, event)
            if event["type"] in ("complete", "error"):
                completed.set()
            return result

        monkeypatch.setattr(main.runs, "append", append)
        response = client.post("/api/runs", json=body)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        assert completed.wait(5), "local task did not settle"
        page = client.get(f"/api/runs/{run_id}").json()
        assert page["status"] == "complete"
        events = page["events"]
        saved = client.get(f"/api/cases/{page['case_id']}").json()
        assert client.get(f"/api/runs/{run_id}").json()["events"] == events
    assert saved["versions"][0]["prebuilt"] == {"demo_id": "T", "built_at": BUILT_AT}
    assert client.get(f"/api/cases/{saved['id']}").json() == saved
    if events:
        assert [e["type"] for e in events[:4]] == ["begin", "prebuilt", "step", "step"]
        assert {k: v for k, v in events[1].items() if k != "t"} == {
            "type": "prebuilt", "demo_id": "T", "built_at": BUILT_AT}
