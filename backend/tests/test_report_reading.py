"""The short report must preserve evidence coverage and avoid blanket assurances."""
from app.analysis.report import _columns, _headline
from app.models import MissingItem, Signal, SignalItem, Source, Status


def signal(*items):
    return Signal(key="credit", title="信用", lede="", flags=0, items=list(items))


def item(key, status=Status.none, *, gap=None, source="registry"):
    return SignalItem(key=key, label=key, value="查询状态", status=status, source=source, gap=gap,
                      ref=f"raw-{key}")


def test_unavailable_evidence_is_pending_not_a_clean_bill():
    signals = [signal(item("penalties", gap="failed"), item("status", gap="not_covered"))]
    _, _, unknown = _columns([], [], signals)
    text = _headline([], [], signals, len(unknown))
    assert "2 项尚待确认" in text
    assert "尚无足够记录判断" in text
    assert "没查到" not in text
    assert "没有不良情况" not in text


def test_reference_and_inapplicable_rows_are_not_unresolved_checks():
    signals = [signal(*(item(key, gap=key) for key in ("listed", "reference", "not_applicable")),
                      item("failed", gap="failed"), item("not_found", gap="not_found"))]
    _, _, unknown = _columns([], [], signals)
    assert [row.refs[0] for row in unknown] == ["credit.failed", "credit.not_found"]


def test_unverified_user_reviews_do_not_create_an_abnormal_record_count():
    signals = [signal(item("reviews", Status.bad, source="user_reviews"), item("status", Status.ok))]
    text = _headline([], [], signals, 0)
    assert "1 项异常" not in text
    assert "已核查的记录暂未见异常" in text
    assert "0 项" not in text


def test_warning_only_records_are_not_summarized_as_no_abnormalities():
    text = _headline([], [], [signal(item("penalties", Status.warn))], 0)
    assert "1 项需留意" in text
    assert "未见异常" not in text


def test_missing_disclosure_is_not_mislabeled_a_record_mismatch():
    missing = [MissingItem(id="M1", text="风险提示", plain="未提供风险提示", source="material")]
    text = _headline([], missing, [], 0)
    assert "1 项需重点核实" in text
    assert "和记录对不上" not in text


def test_real_job_signals_without_company_data_do_not_claim_record_coverage():
    from datetime import date
    from app.analysis.extract import RuleExtractor
    from app.analysis.signals import build_signals
    from app.models import LicenseHit, AmacHit
    from app.scenarios import get_scenario

    signals = build_signals(RuleExtractor().extract(""), None,
                            LicenseHit(query="Unlisted employer", found=False),
                            AmacHit(coverage="not_covered"), None, date(2026, 10, 3), get_scenario("job"))
    _, _, unknown = _columns([], [], signals)
    text = _headline([], [], signals, len(unknown))
    assert "尚无足够记录判断" in text
    assert "4 项尚待确认" in text
    assert "未见异常" not in text


def test_source_catalog_kinds_define_external_record_coverage():
    for kind in ("user_material", "regulation", "parameter", "user_review"):
        sources = {"custom": Source(id="custom", name="测试来源", kind=kind)}
        text = _headline([], [], [signal(item("note", Status.ok, source="custom"))], 0, sources)
        assert "尚无足够记录判断" in text
    sources = {"custom": Source(id="custom", name="公开记录", kind="official")}
    text = _headline([], [], [signal(item("status", Status.ok, source="custom"))], 0, sources)
    assert "已核查的记录暂未见异常" in text
