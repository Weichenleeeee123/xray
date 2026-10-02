import json

from app.store import CaseStore
from tests.helpers import DEMO_COMPANY, make_case


def saved(store, owner, *, created="2026-10-03T00:00:00"):
    case = make_case(DEMO_COMPANY, need="了解公司")
    case.owner_id = owner
    case.created_at = created
    store.save(case)
    return case


def test_warm_private_listing_uses_summaries_without_parsing_case_histories(tmp_path, monkeypatch):
    store = CaseStore(tmp_path)
    a, b = saved(store, "guest-a"), saved(store, "guest-b")
    saved(store, None)
    monkeypatch.setattr(store, "get", lambda _: (_ for _ in ()).throw(AssertionError("full case parsed")))
    assert [s.id for s in store.list(owner_id="guest-a")] == [a.id]
    assert [s.id for s in store.list(owner_id="guest-b")] == [b.id]
    assert store.list(owner_id="guest-c") == []
    assert "owner_id" not in store.list(owner_id="guest-a")[0].model_dump()


def test_legacy_summary_without_owner_rebuilds_once_and_filters_privately(tmp_path, monkeypatch):
    store = CaseStore(tmp_path)
    case = saved(store, "guest-a")
    path = tmp_path / "summaries" / f"{case.id}.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry.pop("owner_id", None)
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert store.list(owner_id="guest-b") == []
    assert json.loads(path.read_text(encoding="utf-8"))["owner_id"] == "guest-a"
    monkeypatch.setattr(store, "get", lambda _: (_ for _ in ()).throw(AssertionError("legacy cache not upgraded")))
    assert [s.id for s in store.list(owner_id="guest-a")] == [case.id]


def test_stale_owner_cache_cannot_reveal_a_transferred_case(tmp_path):
    store = CaseStore(tmp_path)
    case = saved(store, "guest-a")
    # Simulate a stale cached summary after an external case-file repair.
    case.owner_id = "guest-b-longer"
    store._path(case.id).write_text(case.model_dump_json(), encoding="utf-8")
    assert store.list(owner_id="guest-a") == []
    assert [s.id for s in store.list(owner_id="guest-b-longer")] == [case.id]


def test_corrupt_summary_and_wrong_case_identity_rebuild_from_source(tmp_path):
    store = CaseStore(tmp_path)
    case = saved(store, "guest-a")
    path = tmp_path / "summaries" / f"{case.id}.json"
    path.write_text("not JSON", encoding="utf-8")
    assert [s.id for s in store.list(owner_id="guest-a")] == [case.id]
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["summary"]["id"] = "wrong-case"
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert [s.id for s in store.list(owner_id="guest-a")] == [case.id]


def test_private_pagination_filters_before_sorting_and_slicing(tmp_path):
    store = CaseStore(tmp_path)
    old = saved(store, "guest-a", created="2026-10-01T00:00:00")
    new = saved(store, "guest-a", created="2026-10-03T00:00:00")
    saved(store, "guest-b", created="2026-10-04T00:00:00")
    assert [s.id for s in store.list(owner_id="guest-a", limit=1)] == [new.id]
    assert [s.id for s in store.list(owner_id="guest-a", offset=1, limit=1)] == [old.id]


def test_invalid_owner_cache_type_is_not_trusted(tmp_path):
    store = CaseStore(tmp_path)
    case = saved(store, "guest-a")
    path = tmp_path / "summaries" / f"{case.id}.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["owner_id"] = ["guest-b"]
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert [s.id for s in store.list(owner_id="guest-a")] == [case.id]
    assert json.loads(path.read_text(encoding="utf-8"))["owner_id"] == "guest-a"
