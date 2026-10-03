"""A bounded report reading must keep scope, conditions and source ownership."""
import pytest

from app.assistant_overview import MAX_ITEM_CHARS, SCOPE_NOTE, build_overview_reply
from app.demo_presentation import bind_presentation
from app.models import PrebuiltProvenance, RawRecord, Signal, SignalItem, Status
from tests.helpers import DEMO_COMPANY, make_case


def prepared(*, scenario="general", need="", penalties="ok"):
    case = make_case(DEMO_COMPANY, need=need)
    version = case.versions[0]
    version.scenario, version.need = scenario, need
    version.company.status = "存续"
    version.company.scope = "软件开发；技术咨询"
    case.owner_id = "overview-owner"
    version.signals = [Signal(key="credit", title="信用", lede="", flags=0, items=[
        SignalItem(key=key, label=label, value="存续" if key == "status" else "1 条" if state == "bad" else "无",
                   status=state, source="registry", ref="R201")
        for key, label, state in [("status", "登记状态", "ok"), ("penalties", "行政处罚", penalties),
                                 ("abnormal", "经营异常名录", "ok"), ("serious_illegal", "严重违法失信名单", "ok"),
                                 ("dishonest", "失信被执行人", "ok")]
    ])]
    case.raw = [RawRecord(id="R201", source_id="registry", title="合成公开登记记录", kind="commercial",
                         as_of="2025-12-31", retrieved_at="2026-10-04T00:00:00Z",
                         content={"登记状态": "存续", "经营范围": "软件开发；技术咨询", "处罚": []})]
    version.raw_ids = ["R201"]
    return case, version


def row(case, version, key, *, status="bad", text="有相关记录", detail=None,
        source="registry", raw_ref="R201", gap=None):
    signal_key, item_key = key.split(".")
    signal = next((signal for signal in version.signals if signal.key == signal_key), None)
    if signal is None:
        signal = Signal(key=signal_key, title=signal_key, lede="", flags=0, items=[])
        version.signals.append(signal)
    existing = next((item for item in signal.items if item.key == item_key), None)
    if existing:
        signal.items.remove(existing)
    item = SignalItem(key=item_key, label=key, value=text, status=status, source=source,
                      ref=raw_ref, gap=gap, detail=detail)
    signal.items.append(item)
    return item


def reply(case, version, question="你觉得这家公司怎么样", route="overview"):
    return build_overview_reply(case, version, question, route)


def test_recomputes_report_summary_and_never_mutates_or_reads_large_raw_text(monkeypatch):
    case, version = prepared(penalties="bad")
    version.overview.headline = "伪造的已保存安全保证"
    case.raw.append(RawRecord(id="R900", source_id="news", title="巨量但无需重读的资料", kind="web",
                             retrieved_at="2026-10-04T00:00:00Z", content="完整原始记录。" * 300000))
    version.raw_ids.append("R900")
    before = case.model_dump_json()
    result = reply(case, version)
    assert "发现行政处罚记录" in result.text and "伪造的已保存安全保证" not in result.text
    assert "完整原始记录" not in result.text and not result.error_code
    assert result.answer_kind == "overview" and result.answer_scope == "report_snapshot"
    assert result.context_mode is None and result.mode == "template"
    assert SCOPE_NOTE in result.text and len(result.text) < 4500
    assert {"credit.status", "credit.penalties", "R201"}.issubset(result.citations)
    assert case.model_dump_json() == before


def test_impression_distinguishes_technical_strength_from_company_records():
    case, version = prepared(penalties="bad")
    result = reply(case, version, "听说华为是不是特别厉害呀", "impression")
    assert "技术、产品或经营表现" in result.text
    assert "不用处罚或投诉条数代替实力判断" in result.text
    assert "软件开发" in result.text and "发现行政处罚记录" in result.text
    assert "行业领先" not in result.text and "技术实力很强" not in result.text


def test_generic_impression_does_not_pretend_the_user_asked_about_strength():
    case, version = prepared(penalties="bad")
    result = reply(case, version, "你觉得这家公司怎么样", "impression")
    assert "与这次选择有关" in result.text and "“厉害”" not in result.text


def test_known_job_need_is_used_without_asking_user_to_repeat_it():
    case, version = prepared(scenario="job", need="想入职这家公司", penalties="bad")
    row(case, version, "credit.labor", status="ok", text="劳动仲裁 5 条，当被告的劳动官司 1 条")
    result = reply(case, version)
    assert "入职" in result.text and "发现劳动争议记录" in result.text
    assert "劳动仲裁 5 条" in result.text and "所查劳动仲裁未见记录" not in result.text
    assert "你更想了解" not in result.text
    assert result.text.count("？") == 1
    assert result.text.endswith("接下来想先看劳动争议的具体内容，还是招聘与参保记录？")


def test_all_serious_findings_survive_the_three_item_reading_default():
    case, version = prepared(penalties="bad")
    keys = ["credit.dishonest", "credit.serious_illegal", "credit.other_risks",
            "finance.executions", "finance.tax_arrears", "risk.regulator_warning"]
    for index, key in enumerate(keys):
        row(case, version, key, text=f"严重事项 {index + 1}")
    result = reply(case, version)
    assert all(key in result.citations and f"[{key}]" in result.text for key in keys)
    assert "严重事项 6" in result.text


def test_report_reading_preserves_dated_event_context_from_current_public_evidence():
    case, version = prepared(scenario="job", need="想入职这家公司，关注经营稳定性")
    version.created_at = "2026-10-04T00:00:00+08:00"
    row(case, version, "credit.labor", text="劳动仲裁 2 条，当被告的劳动官司 0 条",
        detail="近两年 0 条")
    case.raw[0].content = {"平台记录总数": 2, "返回的明细": [
        {"日期": "2016-10-12"}, {"日期": "2019-01-21"}]}
    before = case.model_dump_json()
    result = reply(case, version)
    assert "历史劳动争议" in result.text
    assert "2016" in result.text and "2019" in result.text
    assert "近两年 0 条" in result.text
    assert "credit.labor" in result.citations and "R201" in result.citations
    assert case.model_dump_json() == before


def test_long_conditions_are_not_sliced_into_a_favourable_claim():
    case, version = prepared()
    detail = "完整事项的限制说明。" * MAX_ITEM_CHARS + "除外情况：还需要确认执行对象。"
    row(case, version, "finance.executions", text="可以申请处理", detail=detail)
    before = case.model_dump_json()
    result = reply(case, version)
    assert "完整说明较长" in result.text and "不截取片段作为判断" in result.text
    assert "finance.executions" in result.citations and "可以申请处理" not in result.text
    assert case.model_dump_json() == before


@pytest.mark.parametrize("failure", ["missing", "other_version", "private", "wrong_source", "failed", "empty"])
def test_incomplete_or_private_bindings_never_support_the_headline(failure):
    case, version = prepared(penalties="bad")
    record = case.raw[0]
    if failure == "missing":
        case.raw = []
    elif failure == "other_version":
        version.raw_ids = []
    elif failure == "private":
        record.kind = "user_material"
    elif failure == "wrong_source":
        record.source_id = "unrelated"
    elif failure == "failed":
        record.coverage = "failed"
    else:
        record.content = None
    result = reply(case, version)
    assert "登记信息已核实；发现行政处罚记录" not in result.text
    assert "[R201]" not in result.text or failure in {"failed", "empty"}
    assert "核实" in result.text
    if failure == "private":
        assert "credit.penalties" not in result.citations and "行政处罚" not in result.text


def test_duplicate_raw_ids_do_not_select_whichever_record_happened_to_be_last():
    case, version = prepared(penalties="bad")
    case.raw.append(case.raw[0].model_copy(update={"content": "冲突内容"}))
    result = reply(case, version)
    assert "R201" not in result.citations and "出处" in result.text
    assert "登记信息已核实；发现行政处罚记录" not in result.text


def test_conflicting_signal_ids_cannot_cite_a_different_row_or_hide_serious_state():
    case, version = prepared(penalties="bad")
    original = next(item for item in version.signals[0].items if item.key == "penalties")
    version.signals[0].items.append(original.model_copy(update={"value": "无", "status": Status.ok}))
    before = case.model_dump_json()
    result = reply(case, version)
    assert "同一条目编号" in result.text and "其中包含原报告异常状态" in result.text
    assert "credit.penalties" not in result.citations and "R201" in result.citations
    assert "已查关键项目未见异常" not in result.text
    assert case.model_dump_json() == before


def test_unknown_coverage_and_original_dates_stay_explicit():
    case, version = prepared()
    row(case, version, "finance.reports", status="none", text="本次未查成", gap="failed")
    result = reply(case, version)
    assert "来源数据日期：2025-12-31" in result.text
    assert "来源数据日期：2026-10-04" not in result.text
    assert "尚待核实" in result.text and "finance.reports" in result.citations
    assert "本次未查成" in result.text


def test_valid_prebuilt_copy_is_rechecked_and_preserved_without_overwriting_history():
    case, version = prepared(penalties="bad")
    version.prebuilt = PrebuiltProvenance(demo_id="TEST", built_at="2026-10-04T00:00:00Z")
    bind_presentation(case, version, title="指定版本的预制摘要", note="有对应证据绑定",
                      body="这段定稿仅供本版阅读。", refs=["R201"])
    before = case.model_dump_json()
    result = reply(case, version)
    assert "指定版本的预制摘要" in result.text and "这段定稿仅供本版阅读" in result.text
    assert "credit.penalties" in result.citations and "R201" in result.citations
    assert case.model_dump_json() == before


@pytest.mark.parametrize("content,kind", [(None, "commercial"), ({}, "commercial"), ([], "commercial"),
                                         ("", "commercial"), ({"text": "用户说法"}, "user_material")])
def test_a_bound_presentation_still_needs_nonempty_public_evidence(content, kind):
    case, version = prepared()
    case.raw[0].content, case.raw[0].kind = content, kind
    version.prebuilt = PrebuiltProvenance(demo_id="TEST", built_at="2026-10-04T00:00:00Z")
    # The generic presentation binder checks found/ref ownership, not whether
    # its records are sufficient company evidence for this specific route.
    bind_presentation(case, version, title="不合适的预制摘要", note="空或私人出处", body="不应被当作公司概况。", refs=["R201"])
    before = case.model_dump_json()
    result = reply(case, version)
    assert "不合适的预制摘要" not in result.text
    assert case.model_dump_json() == before


@pytest.mark.parametrize("change", ["company", "need", "record", "version", "live"])
def test_stale_prebuilt_copy_is_not_reused_or_deleted_from_saved_history(change):
    case, version = prepared()
    version.prebuilt = PrebuiltProvenance(demo_id="TEST", built_at="2026-10-04T00:00:00Z")
    bind_presentation(case, version, title="过时预制摘要", note="旧范围", body="不应再次展示的旧文案。", refs=["R201"])
    if change == "company":
        case.case.company_name = "另一家公司"
    elif change == "need":
        version.need = "新的研究用途"
    elif change == "record":
        case.raw[0].content = {"变更": "新的来源记录"}
    elif change == "version":
        version.no += 1
    else:
        version.prebuilt = None
    before = case.model_dump_json()
    result = reply(case, version)
    assert "过时预制摘要" not in result.text and "不应再次展示的旧文案" not in result.text
    assert case.model_dump_json() == before


def test_foreign_version_is_rejected_and_older_selected_version_stays_selected():
    case, version = prepared()
    foreign = version.model_copy(update={"no": 999})
    with pytest.raises(ValueError):
        reply(case, foreign)
    newer = version.model_copy(deep=True, update={"no": 2})
    newer.signals[0].items[0].value = "后续已变更"
    case.versions.append(newer)
    case.current = 2
    result = reply(case, version)
    assert result.version == 1 and "后续已变更" not in result.text


def test_untrusted_private_signal_cannot_reenter_through_source_alias():
    case, version = prepared()
    case.raw.append(RawRecord(id="R999", source_id="private-alias", title="私人材料", kind="user_material",
                             retrieved_at="2026-10-04T00:00:00Z", content="私有的未核实说法"))
    version.raw_ids.append("R999")
    row(case, version, "credit.other_risks", text="私有的未核实说法", source="private-alias", raw_ref="R999")
    result = reply(case, version)
    assert "私有的未核实说法" not in result.text and "R999" not in result.citations
    assert "credit.other_risks" not in result.citations
