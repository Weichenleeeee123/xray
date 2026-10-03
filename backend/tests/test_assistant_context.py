"""Lossless context packing with synthetic records only; no external model calls."""
import json

import pytest

import app.assistant as assistant
from app.assistant import answer, context, rewrite_report
from app.glossary import term_ref
from app.models import ChatIn, PrebuiltProvenance, Term
from tests.helpers import DEMO_COMPANY, make_case
from tests.test_llm_assistant import FakeLLM


SOURCE_KEY = "来源目录（不可作为事实出处）"


def legacy_context(case, version, terms=()):
    """Reconstruct the previous duplicated layout to reproduce the size regression."""
    data = context(case, version, terms)
    data["报告"] = version.model_dump(mode="json", exclude={"created_at", "prebuilt"})
    data["名词解释"] = [{"id": term_ref(t), "名词": t.term, "解释": t.plain, "对你意味着": t.why}
                    for t in terms]
    return data


def expected_terms(terms):
    return [{**term.model_dump(mode="json"), "id": term_ref(term)} for term in terms]


def packed_context(case, version, terms=None):
    return json.loads(assistant._context_json(case, version, terms, max_chars=1))


def sent_case(llm):
    text = next(message["content"] for message in llm.calls[0]
                if message["content"].startswith("<案卷数据>\n"))
    return text.removeprefix("<案卷数据>\n").removesuffix("\n</案卷数据>")


@pytest.fixture
def packed_case():
    case = make_case(DEMO_COMPANY, "保本保息\n随时可退")
    version = case.versions[0]
    material = next(raw for raw in case.raw if raw.source_id == "material")
    while len(case.raw) < 60:
        no = len(case.raw) + 100
        case.raw.append(material.model_copy(deep=True, update={
            "id": f"R{no}", "title": f"合成记录 {no}", "as_of": "2026-09-01",
            "url": f"https://example.invalid/record/{no}", "note": "未核实的合成材料，不能当作保证",
            "content": {"材料原句": "第一份材料称允许随时退款。",
                        "另一份条款": "另一份条款明确不允许随时退款。",
                        "未知": None, "附录": [False, 0, "末尾否定：不构成偿付保证。"]},
        }))
    version.raw_ids = [raw.id for raw in case.raw]
    version.terms = [Term(id="synthetic_scope", term="资料范围", aliases=["范围边界", "核对范围"],
                          plain="指这份记录能支持核对的范围。", why="范围以外的事项仍然未知。",
                          basis=material.source_id, law="合成说明出处", origin="model"),
                     Term(id="synthetic_unknown", term="未知项目", plain="记录未能说明的事项。")]
    version.judgments[0].dispute.append("第一份材料与另一份条款的退款说法相反。")
    version.judgments[0].unknown.append("当前无法确认哪一份适用。")
    version.judgments[0].cannot.append("不能由查到记录推断能够偿付。")
    version.judgments[0].history.append("合成旧说明必须保留。")
    # Duplicate source metadata made this otherwise complete case exceed 120k.
    source = next(iter(version.sources.values()))
    baseline = len(json.dumps(legacy_context(case, version, version.terms), ensure_ascii=False))
    source.note = (source.note or "") + "合" * max(0, (125_000 - baseline + 1) // 2)
    assert len(json.dumps(legacy_context(case, version, version.terms), ensure_ascii=False)) > 120_000
    return case


def test_full_report_and_sixty_raw_records_survive_context_deduplication(packed_case):
    case = packed_case
    version = case.versions[0]
    before = case.model_dump_json()
    data = packed_context(case, version, version.terms)
    assert "sources" not in data["报告"] and "terms" not in data["报告"]
    assert data["报告"] == version.model_dump(mode="json", exclude={"created_at", "sources", "terms", "prebuilt"})
    expected_raw = [r.model_dump(mode="json", exclude={"retrieved_at"}) for r in case.raw]
    assert len(data["原始数据"]) == 60
    assert data["原始数据"] == expected_raw
    assert data[SOURCE_KEY] == {sid: s.model_dump(mode="json") for sid, s in version.sources.items()}
    assert {r["source_id"] for r in data["原始数据"]} <= data[SOURCE_KEY].keys()
    assert set(data["报告"]["raw_ids"]) == {r["id"] for r in data["原始数据"]}
    assert data["名词解释"] == expected_terms(version.terms)
    assert case.model_dump_json() == before


def test_duplicate_heavy_case_fits_existing_budget_without_dropping_evidence(packed_case, tmp_path):
    llm = FakeLLM(['{"segments":[{"kind":"fact","fact_id":"credit.status"}],"not_found":false}'], tmp_path)
    before = packed_case.model_dump_json()
    result = answer(packed_case, ChatIn(text="请核对这家公司的登记状态"), llm, max_context_chars=120_000)
    assert result.mode == "model" and not result.not_found and len(llm.calls) == 1
    assert "credit.status" in result.citations
    blob = sent_case(llm)
    data = json.loads(blob)
    assert blob == json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    assert len(blob) + len("请核对这家公司的登记状态") <= 120_000
    assert data["原始数据"] == [r.model_dump(mode="json", exclude={"retrieved_at"}) for r in packed_case.raw]
    assert packed_case.model_dump_json() == before


def test_context_default_and_explicit_terms_keep_complete_metadata(packed_case):
    version = packed_case.versions[0]
    assert packed_context(packed_case, version)["名词解释"] == expected_terms(version.terms)
    extra = Term(id="question_term", term="提问附加名词", aliases=["别名"], plain="仅用于解释本次提问。",
                 basis="basis.ref", law="说明依据", origin="glossary")
    terms = [*version.terms, extra]
    assert packed_context(packed_case, version, terms)["名词解释"] == expected_terms(terms)
    assert packed_context(packed_case, version, [])["名词解释"] == []


def test_old_selected_version_keeps_its_own_records_sources_and_terms(packed_case):
    case = packed_case
    old = case.versions[0]
    expected = packed_context(case, old)
    later = old.model_copy(deep=True, update={"no": 2})
    later.terms = [Term(id="later_only", term="新版独有名词", plain="不能串入旧版。")]
    later.sources = {sid: source.model_copy(update={"note": "新版独有来源说明"})
                     for sid, source in later.sources.items()}
    case.raw.append(case.raw[-1].model_copy(deep=True, update={"id": "R9999", "content": "新版独有原始材料"}))
    later.raw_ids.append("R9999")
    case.versions.append(later)
    case.current, case.sources = 2, later.sources
    actual = packed_context(case, old)
    assert actual == expected
    assert actual["名词解释"] == expected_terms(old.terms)
    assert "新版独有" not in json.dumps(actual, ensure_ascii=False)


def test_old_version_without_source_snapshot_keeps_full_fallback_catalog(packed_case):
    version = packed_case.versions[0]
    version.sources = {}
    data = packed_context(packed_case, version)
    assert "sources" not in data["报告"]
    assert data[SOURCE_KEY] == {sid: source.model_dump(mode="json") for sid, source in packed_case.sources.items()}


def test_rewrite_context_keeps_version_terms_and_uses_compact_complete_json(packed_case, tmp_path):
    llm = FakeLLM(['{"items":[]}'], tmp_path)
    rewrite_report(packed_case, gateway=llm)
    assert len(llm.calls) == 1
    blob = next(message["content"] for message in llm.calls[0] if message["role"] == "user")
    data = json.loads(blob)
    assert blob == json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    assert data["名词解释"] == expected_terms(packed_case.versions[0].terms)
    assert data["原始数据"] == [r.model_dump(mode="json", exclude={"retrieved_at"}) for r in packed_case.raw]


@pytest.mark.parametrize("selected", [[], ["A2"]])
def test_genuinely_oversized_context_remains_guarded_even_with_selected_refs(packed_case, tmp_path, selected):
    packed_case.raw[-1].content = "不可截断的完整材料" * 80_000 + "末尾相反证据：不允许退款。"
    llm = FakeLLM(['{"segments":[]}'], tmp_path)
    result = answer(packed_case, ChatIn(text="请解释这条", refs=selected), llm)
    assert result.mode == "guard" and result.not_found and not llm.calls
    assert "没有截断材料" in result.text
    user_message = result.text + "".join(result.suggest)
    assert "提高服务端预算" not in user_message
    assert "查看报告" in user_message and "原始记录" in user_message
    assert "仍可能超出" in user_message


def test_small_legacy_case_reuses_pre_prebuilt_recording(tmp_path, monkeypatch):
    case = make_case(DEMO_COMPANY, "保本保息")
    case.versions[0].terms = [Term(id="known", term="旧名词", plain="原有释义。", origin="glossary")]
    q = ChatIn(text="请核对这家公司的登记状态")
    llm = FakeLLM(['{"segments":[{"kind":"fact","fact_id":"credit.status"}],"not_found":false}'], tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(assistant, "context", legacy_context)
        recorded = answer(case, q, llm)
    assert recorded.mode == "model" and len(llm.calls) == 1
    recorded_blob = sent_case(llm)
    assert "prebuilt" not in json.loads(recorded_blob)["报告"]
    llm.mode = "replay"
    replayed = answer(case, q, llm)
    assert replayed.mode == "replay" and replayed.text == recorded.text
    assert len(llm.calls) == 1


def test_small_rewrite_keeps_original_serialization_and_version_terms(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息")
    version = case.versions[0]
    version.terms = [Term(id="old_term", term="旧版名词", plain="完整释义。", aliases=["旧别名"], origin="model")]
    llm = FakeLLM(['{"items":[]}'], tmp_path)
    rewrite_report(case, gateway=llm)
    blob = next(message["content"] for message in llm.calls[0] if message["role"] == "user")
    data = json.loads(blob)
    expected = legacy_context(case, version)
    expected["可改写条目"] = data["可改写条目"]
    assert blob == json.dumps(expected, ensure_ascii=False)
    assert data["报告"]["terms"] == [t.model_dump(mode="json") for t in version.terms]


@pytest.mark.parametrize("limit", [1, 120_000])
def test_real_prebuilt_metadata_and_notes_remain_in_both_layouts(limit):
    case = make_case(DEMO_COMPANY, "保本保息")
    version = case.versions[0]
    version.prebuilt = PrebuiltProvenance(demo_id="C", built_at="2026-09-30 10:20")
    version.notes.insert(0, "预制示例：本次直接载入，未重新联网查询。")
    data = json.loads(assistant._context_json(case, version, max_chars=limit))
    assert data["报告"]["prebuilt"] == version.prebuilt.model_dump()
    assert data["报告"]["notes"] == version.notes


@pytest.mark.parametrize("mode", ["full", "shadow"])
def test_memory_integration_retains_lossless_packing_and_full_fallback(packed_case, tmp_path, monkeypatch, mode):
    from app import config, privacy
    monkeypatch.setattr(config, "CASE_MEMORY_ENABLED", True)
    monkeypatch.setattr(config, "ASSISTANT_CONTEXT_MODE", mode)
    monkeypatch.setattr(config, "CASE_MEMORY_DIR", tmp_path / "private_memory")
    packed_case.owner_id = "packing-owner"
    before = packed_case.model_dump_json()
    token = privacy.OWNER.set(packed_case.owner_id)
    llm = FakeLLM(['{"segments":[{"kind":"fact","fact_id":"credit.status"}]}'], tmp_path / "llm")
    try:
        reply = answer(packed_case, ChatIn(text="请核对这家公司的登记状态"), llm, max_context_chars=120_000)
    finally:
        privacy.OWNER.reset(token)
    assert reply.context_mode == "full" and reply.error_code is None
    assert reply.mode == "model" and len(llm.calls) == 1
    data = json.loads(sent_case(llm))
    assert len(data["原始数据"]) == 60
    assert data["原始数据"] == [r.model_dump(mode="json", exclude={"retrieved_at"}) for r in packed_case.raw]
    assert "sources" not in data["报告"] and "terms" not in data["报告"]
    assert packed_case.model_dump_json() == before


def test_large_bank_sized_case_fits_default_budget_with_all_evidence(packed_case, tmp_path):
    version = packed_case.versions[0]
    # Match Hangzhou Bank: even after source deduplication the case exceeds 120k.
    packed = assistant._context_json(packed_case, version, version.terms, max_chars=1)
    packed_case.raw[-1].content["long_material"] = "证" * (122_618 - len(packed))
    before = packed_case.model_dump_json()
    llm = FakeLLM(['{"segments":[{"kind":"fact","fact_id":"credit.status"}]}'], tmp_path)
    reply = answer(packed_case, ChatIn(text="请核对这家公司的登记状态"), llm)
    assert reply.error_code is None and reply.mode == "model" and len(llm.calls) == 1
    data = json.loads(sent_case(llm))
    assert data["原始数据"] == [r.model_dump(mode="json", exclude={"retrieved_at"}) for r in packed_case.raw]
    assert data["报告"]["judgment_changes"] == [c.model_dump(mode="json") for c in version.judgment_changes]
    assert data["报告"]["judgments"] == [j.model_dump(mode="json") for j in version.judgments]
    assert packed_case.model_dump_json() == before


def test_explicit_smaller_budget_still_guards_complete_evidence(packed_case, tmp_path):
    packed_case.raw[-1].content = "必须完整保留的材料" * 20_000 + "末尾否定：不允许退款。"
    llm = FakeLLM(['{"segments":[]}'], tmp_path)
    result = answer(packed_case, ChatIn(text="请核对这家公司的登记状态"), llm, max_context_chars=120_000)
    assert result.error_code == "context_budget" and not llm.calls


def test_default_capacity_accepts_400k_material_without_truncation(packed_case, tmp_path):
    material = "完整保留的原始材料。" * 40_000 + "末尾否定：不允许退款。"
    packed_case.raw[-1].content = material
    llm = FakeLLM(['{"segments":[{"kind":"fact","fact_id":"credit.status"}]}'], tmp_path)
    result = answer(packed_case, ChatIn(text="请核对这家公司的登记状态"), llm)
    assert result.error_code is None and len(llm.calls) == 1
    assert material in sent_case(llm)
