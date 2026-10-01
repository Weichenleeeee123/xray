from app.analysis.pipeline import analyze, load_services
from app.config import FIXTURES_DIR
from app.models import CaseIn, Status, Verdict

svc = load_services()
DEMO_COMPANY = "杭州满盈禾康养健康咨询有限公司"
DEMO = (FIXTURES_DIR / "flyers" / "manyinghe.txt").read_text(encoding="utf-8")


def run(company: str, text: str):
    return analyze(CaseIn(company_name=company, flyer_text=text), svc, "test")


def by_id(out):
    return {a.id: a for a in out.assertions}


demo = run(DEMO_COMPANY, DEMO)


def test_demo_verdicts():
    assert {a.id: a.verdict for a in demo.assertions} == {
        "A1": Verdict.mismatch, "A2": Verdict.redline, "A3": Verdict.unverifiable,
        "A4": Verdict.mismatch, "A5": Verdict.misleading, "A6": Verdict.misleading,
    }


def test_demo_plain_language_carries_computed_numbers():
    a = by_id(demo)
    assert "8.2 倍" in a["A2"].plain
    assert a["A5"].plain == "5000 万是\"承诺\"，实际交了 ¥0。"
    assert a["A6"].plain == "宣称 30 家门店；年报里只有 4 人参保，登记的分支机构 0 家。"


def test_demo_tally_and_missing_disclosure():
    assert demo.tally == {"red": 3, "amber": 2, "grey": 1, "green": 0, "missing": 1}
    assert [m.id for m in demo.missing] == ["M1"]


def test_every_check_cites_a_known_source():
    cited = [c.source for a in demo.assertions for c in a.checks]
    cited += [i.source for s in demo.signals for i in s.items]
    cited += [m.source for m in demo.missing]
    assert set(cited) <= set(demo.sources)


def test_demo_signals():
    sig = {s.key: s for s in demo.signals}
    assert list(sig) == ["risk", "finance", "credit", "reputation"]
    assert sig["finance"].flags == 2          # 实缴为零、股权出质
    assert sig["credit"].flags == 1           # 行政处罚
    status = {i.key: i for i in sig["credit"].items}["status"]
    assert status.detail.endswith("1 年 7 个月") and status.status is Status.warn
    assert sig["reputation"].extra["last3"] == 17
    assert sig["reputation"].extra["total"] == 27


def test_licensed_bank_material_raises_no_red_flag():
    out = run("杭州银行股份有限公司", "非保本浮动收益型理财产品\n业绩比较基准 2.8%\n理财非存款、产品有风险、投资须谨慎")
    assert out.license.found
    assert not [a for a in out.assertions if a.color == "red"]
    assert out.missing == []
    assert {i.key: i.status for i in out.signals[0].items}["bank_list"] is Status.ok


def test_unknown_company_degrades_to_not_checked_instead_of_guessing():
    out = run("某某科技有限公司", "国资背景\n注册资本 1 亿")
    assert out.company is None
    a = by_id(out)
    assert a["A4"].verdict is Verdict.unverifiable
    assert a["A5"].verdict is Verdict.unverifiable
    assert out.notes


def test_ordinary_business_gets_no_red_flags():
    out = run("杭州明澄家政服务有限公司", "明澄家政 · 专业保洁\n全国 3 家门店")
    assert not [a for a in out.assertions if a.color in ("red", "amber")]
    assert out.missing == []
    assert by_id(out)["A6"].verdict is Verdict.consistent


def test_scope_disclaimer_is_not_read_as_financial_business():
    out = run("深圳前海满盈禾资产管理有限公司", "正规理财 · 安全稳健\n年化 9%")
    a = by_id(out)
    assert a["A1"].verdict is Verdict.mismatch
    scope = next(c for c in a["A1"].checks if c.label == "经营范围")
    assert scope.status is Status.warn and "资产管理" in scope.result
    assert a["A2"].verdict is Verdict.attention
