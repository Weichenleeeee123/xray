import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.case_memory import builder
from app.case_memory.store import MemoryStore
from app.models import RawRecord, ChatIn
from tests.helpers import make_case, DEMO_COMPANY, add
from tests.test_llm_assistant import FakeLLM


def owned(rows=0):
    case = make_case(DEMO_COMPANY, "合同写明可以退款。服务开始后不退；提前退出须核对费用。")
    case.owner_id = "guest-a"
    if rows:
        case.raw.append(RawRecord(id="R900", source_id="synthetic", title="合成新闻记录", kind="demo",
            retrieved_at="2026-10-03T00:00:00Z", content=[
                {"标题":f"第{i}条企业活动", "原文":"仅用于规模测试的无关活动记录。" * 40} for i in range(rows)]))
        case.versions[-1].raw_ids.append("R900")
    return case


@pytest.mark.parametrize("rows", [0, 60, 400])
def test_baseline_size_and_model_call_boundary(rows, tmp_path):
    from app.assistant import answer, context
    case = owned(rows)
    llm = FakeLLM([json.dumps({"segments":[{"kind":"support","text":"你会担心是可以理解的。"}]})], tmp_path)
    size = len(json.dumps(context(case, case.versions[-1]), ensure_ascii=False))
    start = time.perf_counter()
    result = answer(case, ChatIn(text="我想存20w但好害怕怎么办"), llm, max_context_chars=240000)
    print(json.dumps({"rows":rows,"full_chars":size,"seconds":round(time.perf_counter()-start,3),
                      "calls":len(llm.calls),"mode":result.mode}, ensure_ascii=False))
    if rows == 400:
        assert size > 120000 and not llm.calls and result.mode == "guard"
    else:
        assert llm.calls


def test_build_keeps_original_conditions_and_exact_locators():
    case = owned()
    before = case.model_dump_json()
    memory = builder.build(case, 1, case.owner_id)
    material = next(r for r in case.raw if r.kind == "user_material")
    unit = next(u for u in memory.evidence_index if u.locator.raw_id == material.id)
    assert unit.locator.path == []
    assert "withdrawal" in unit.topics and "fees" in unit.topics
    assert "服务开始后不退" in builder.locate(material.content, unit.locator.path)
    assert memory.state == "ready" and memory.overview["unknown"]
    assert before == case.model_dump_json()


def test_private_cache_reuse_concurrency_and_ownerless_history(tmp_path, monkeypatch):
    case = owned()
    storage = MemoryStore(tmp_path)
    real = builder.build
    calls = []
    def counted(*args):
        calls.append(1)
        return real(*args)
    monkeypatch.setattr(builder, "build", counted)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: storage.get_or_build(case, 1, "guest-a"), range(4)))
    assert len(calls) == 1 and all(m == results[0] for m in results)
    with pytest.raises(PermissionError):
        storage.get_or_build(case, 1, "guest-b")
    case.owner_id = None
    with pytest.raises(PermissionError):
        storage.get_or_build(case, 1, "")
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_versions_sources_rules_and_owner_are_separate_cache_keys(tmp_path, monkeypatch):
    case = owned()
    storage = MemoryStore(tmp_path)
    first = storage.get_or_build(case, 1, "guest-a")
    newer = add(case, "material", "新的付款对象是乙公司，需要进一步核对与甲公司的关系")
    storage.get_or_build(newer, 2, "guest-a")
    assert storage.get_or_build(newer, 1, "guest-a") == first
    newer.raw[-1].note = "仅为用户上传材料，未核实真实性"
    storage.get_or_build(newer, 2, "guest-a")
    monkeypatch.setattr(builder, "BUILDER_VERSION", "next")
    storage.get_or_build(newer, 2, "guest-a")
    other = newer.model_copy(deep=True)
    other.owner_id = "guest-b"
    storage.get_or_build(other, 2, "guest-b")
    assert len(list(tmp_path.glob("*.json"))) == 5


def test_failed_corrupt_missing_memory_rebuilds_without_touching_case(tmp_path, monkeypatch):
    case = owned()
    original = case.model_dump_json()
    storage = MemoryStore(tmp_path)
    real = builder.build
    def broken(*args):
        raise ValueError("secret material must not be logged or cached as error")
    monkeypatch.setattr(builder, "build", broken)
    with pytest.raises(ValueError):
        storage.get_or_build(case, 1, "guest-a")
    path = next(tmp_path.glob("*.json"))
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "failed"
    assert "secret material" not in path.read_text(encoding="utf-8")
    monkeypatch.setattr(builder, "build", real)
    assert storage.get_or_build(case, 1, "guest-a").state == "ready"
    assert case.model_dump_json() == original


def test_memory_directory_must_not_be_public():
    from app import config
    with pytest.raises(ValueError):
        MemoryStore(config.WEB_DIR / "case-memory")
