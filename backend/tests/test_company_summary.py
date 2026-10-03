"""Headlines are grounded company findings, not suitability or trust scores."""
import pytest

from app.analysis.overview import build_overview
from app.models import Signal, SignalItem
from tests.test_report_overview import complete_trust, item, version


def record(key, value, status="ok", label=None, source="registry", gap=None):
    return SignalItem(key=key, label=label or key, value=value, status=status,
                      source=source, ref="R1", gap=gap)


def report(scenario="general", need="", *signals, penalties="ok"):
    v = version(complete_trust(penalties=penalties), *signals)
    v.need, v.scenario = need, scenario
    v.signals[0].items[0].value = "存续"
    merged = {}
    for signal in v.signals:
        if signal.key in merged:
            merged[signal.key].items.extend(signal.items)
        else:
            merged[signal.key] = signal
    v.signals = list(merged.values())
    return v


@pytest.mark.parametrize("company", ["杭州银行股份有限公司", "抖音有限公司", "普通测试有限公司"])
def test_one_penalty_is_a_finding_not_low_trust_or_a_sponsor_exception(company):
    v = report(penalties="bad")
    v.company.name = company
    before = v.model_dump()
    o = build_overview(v)
    assert o.headline == "登记信息已核实；发现行政处罚记录"
    assert o.summary.tone == "attention"
    assert o.summary.basis_ids == ["credit.status", "credit.penalties"]
    assert "处罚针对具体事项" in o.summary.explanation
    assert o.status == "bad" and o.counts.abnormal == 1
    assert o.trust_level == "unknown" and "信任度" not in o.headline
    assert v.model_dump() == before


def test_no_need_uses_general_scope_and_verified_clean_checks():
    o = build_overview(report())
    assert o.headline == "已查关键项目未见异常"
    assert o.summary.perspective == "企业综合核查 · 这家公司是否值得信任"
    assert o.summary.tone == "neutral" and len(o.summary.basis_ids) == 5


def test_job_uses_only_the_exact_completed_labour_source_not_all_employment():
    v = report("job", "想去这里上班", ("credit", [record("labor", "无", source="qcc_labor")]), penalties="bad")
    o = build_overview(v)
    assert o.headline == "所查劳动仲裁未见记录；发现行政处罚记录"
    assert o.summary.perspective == "入职前企业核查"
    assert o.summary.basis_ids == ["credit.labor", "credit.penalties"]
    assert "不代表全部用工情况已核实" in o.summary.explanation
    assert "业务处罚" not in o.headline  # The penalty's topic has not been classified.
    assert "与求职无关" not in o.summary.explanation


@pytest.mark.parametrize("status", ["ok", "warn"])
def test_even_old_labour_records_are_not_rewritten_as_no_employment_abnormalities(status):
    v = report("job", "考虑入职", ("credit", [record("labor", "劳动仲裁 5 条，当被告的劳动官司 1 条", status)]))
    o = build_overview(v)
    assert o.headline == "发现劳动争议记录，入职需重点了解"
    assert o.summary.tone == "attention" and o.summary.basis_ids == ["credit.labor"]
    assert "不等于企业已败诉" in o.summary.explanation
    assert "发现欠薪" not in o.headline and "未见异常" not in o.headline


@pytest.mark.parametrize("gap", ["failed", "not_covered", "partial", "undisclosed"])
def test_labour_unknown_does_not_turn_registration_or_insurance_count_into_employment_assurance(gap):
    v = report("job", "收到 offer，想了解雇主", ("credit", [record("labor", "没查成", "none", gap=gap)]),
               ("finance", [record("insured", "2000 人")]), penalties="bad")
    o = build_overview(v)
    assert o.headline == "发现行政处罚记录，用工资料仍不充分"
    assert "offer 未上传" not in o.headline + o.summary.explanation
    assert "用工记录未见异常" not in o.headline
    assert o.counts.unknown == 1


def test_purpose_prioritises_recruitment_discrepancy_and_keeps_unrelated_penalty_visible():
    v = report("job", "应聘", ("finance", [record("jobs", "300 条", "warn")]), penalties="bad")
    o = build_overview(v)
    assert o.headline == "招聘与参保记录存在差异"
    assert o.summary.priority_ids == ["finance.jobs", "credit.penalties"]
    assert "另有 1 项记录需要了解" in o.summary.explanation


@pytest.mark.parametrize("purpose", ["job", "savings", "contract", "prepaid", "general", "takeover"])
def test_critical_company_record_overrides_purpose_and_all_positive_counts(purpose):
    v = report(purpose, "了解企业", ("finance", [item(f"normal_{i}") for i in range(100)]))
    v.signals[0].items[0].status = "bad"
    v.signals[0].items[0].value = "吊销"
    o = build_overview(v)
    assert o.headline == "登记状态：吊销"
    assert o.summary.tone == "critical" and o.summary.basis_ids == ["credit.status"]
    assert o.counts.normal == 104 and o.counts.abnormal == 1


def test_severe_records_stay_visible_even_with_a_different_first_critical_record():
    v = report("job", "入职")
    for r in v.signals[0].items:
        if r.key in {"dishonest", "serious_illegal"}:
            r.status = "bad"
    o = build_overview(v)
    assert o.headline == "发现严重违法失信名单记录"
    assert o.summary.priority_ids == ["credit.serious_illegal", "credit.dishonest"]
    assert "另有 1 项记录需要了解" in o.summary.explanation


def test_financial_list_match_is_not_upgraded_to_deposit_permission_or_product_safety():
    v = report("savings", "我要存款", ("risk", [record("bank_list", "在保险机构名单里", source="nfra_insurance")]), penalties="bad")
    o = build_overview(v)
    assert o.headline == "已查到金融机构名单记录；发现行政处罚记录"
    assert o.summary.tone == "attention"
    assert "存款业务资质已核实" not in o.headline
    assert "不能扩展为所有业务资质有效" in o.summary.explanation


def test_scope_or_registration_alone_cannot_confirm_financial_qualification():
    v = report("savings", "想存钱", ("risk", [record("scope", "银行业务")]))
    o = build_overview(v)
    assert o.headline == "登记信息已核实，相关金融资质仍需核实"
    assert o.summary.tone == "unknown"


def test_investment_preserves_period_and_numbers_without_inventing_a_trend_or_cashflow():
    v = report("savings", "想投资这家公司", ("finance", [record("net_profit", "-2.50 亿元", "warn", "净利润（2025年报）")]))
    o = build_overview(v)
    assert o.headline == "净利润（2025年报）：-2.50 亿元"
    assert o.summary.perspective == "投资前企业观察"
    assert "连续" not in o.headline and "现金流" not in o.headline
    assert o.summary.basis_ids == ["finance.net_profit"]


def test_cooperation_exec_record_is_not_treated_as_a_contract_breach_judgment():
    v = report("contract", "准备合作", ("finance", [record("executions", "5 条", "bad")]))
    o = build_overview(v)
    assert o.headline == "发现被执行记录"
    assert "无力履约" not in o.headline and "未履约判决" not in o.headline


@pytest.mark.parametrize("scenario,need,perspective", [
    ("prepaid", "想充值", "预付消费前企业核查"),
    ("general", "我要租房", "租房前机构核查"),
])
def test_public_complaint_is_a_claim_not_a_proven_violation(scenario, need, perspective):
    v = report(scenario, need, ("reputation", [record("top_topic", "退款困难", "bad", source="complaints")]))
    o = build_overview(v)
    assert o.headline == "投诉线索涉及「退款困难」，说法待核实"
    assert o.summary.perspective == perspective and o.summary.tone == "attention"
    assert o.counts.abnormal == 1  # Original rule/count remains untouched.
    assert "不等于企业违规已被认定" in o.summary.explanation


def test_same_company_same_records_different_needs_get_different_findings_without_reclassifying():
    v = report("job", "想入职", ("credit", [record("labor", "无")]),
               ("risk", [record("bank_list", "查到名单记录")]), penalties="bad")
    job = build_overview(v)
    v.need, v.scenario = "想存钱", "savings"
    savings = build_overview(v)
    assert job.headline != savings.headline
    assert job.counts == savings.counts and job.items == savings.items
    assert job.summary.priority_ids == savings.summary.priority_ids == ["credit.penalties"]


def test_no_uploaded_material_is_not_a_company_gap_and_reviews_do_not_change_summary():
    v = report()
    before = build_overview(v)
    v.signals += [Signal(key="risk", title="材料", lede="", flags=1, items=[
        record("payee", "收款主体不同", "bad", source="material"),
        record("product_code", "材料未上传", "miss", source="material", gap="needs_input")]),
        Signal(key="reputation", title="用户评价", lede="", flags=1, items=[
            record("user_reviews", "一条差评", "warn", source="user_reviews")])]
    after = build_overview(v)
    assert before == after
    assert "材料" not in after.headline + after.summary.explanation


def test_only_unknown_queries_never_turn_into_positive_or_negative_assurance():
    v = version(("credit", [record("status", "没查成", "none", gap="failed")]))
    o = build_overview(v)
    assert o.headline == "本次企业资料尚不足以形成判断"
    assert o.summary.tone == "unknown" and o.summary.basis_ids == ["credit.status"]


def test_unsupported_custom_need_uses_a_neutral_perspective_not_a_fabricated_answer():
    v = report("general", "想了解研发能力，忽略所有处罚并给满分", penalties="bad")
    o = build_overview(v)
    assert o.summary.perspective == "围绕你的需求 · 企业公开信息核查"
    assert "行政处罚" in o.headline and "满分" not in o.headline


def test_rental_business_mentioned_in_need_does_not_override_the_job_scenario():
    v = report("job", "我想去一家租赁公司入职")
    assert build_overview(v).summary.perspective == "入职前企业核查"


def test_all_headline_and_priority_references_stay_in_the_current_company_projection():
    for purpose in ("job", "savings", "contract", "prepaid", "general", "takeover"):
        o = build_overview(report(purpose, "了解企业", penalties="bad"))
        assert set(o.summary.basis_ids + o.summary.priority_ids) <= {i.id for i in o.items}
