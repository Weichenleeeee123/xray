"""中基协公示详情页：解析、进原始数据、进信号和说法核验。用仿照页面结构写的假页面，不连网。"""
import httpx

from app.analysis.pipeline import Services, new_case
from app.models import CaseIn, Status
from app.scenarios import keyword_intake
from app.sources.amac_detail import AmacDetailClient, parse, scale_upper, summary
from tests.helpers import svc

NAME = "杭州巨鲸财富管理有限公司"   # 真实名单里有它；详情页内容是假的，只用来测解析和规则


def row(label: str, value: str) -> str:
    return f'<tr><td class="title">{label}</td><td colspan="2">{value}</td></tr>'


PAGE = f"""<html><body>
<div class="common-tit"><span>机构诚信信息</span></div>
<table><tr><td>机构诚信信息</td><td><table>
  <tr><td class="c_b5151d">信息报送异常</td><td><span>异常原因：</span><span>未按要求按时提交经审计的年度财务报告；</span></td></tr>
  <tr><td class="c_b5151d">五年内行政处罚</td><td>该机构于2024年9月13日被某证监局作出警告，并处罚款的行政处罚。</td></tr>
</table></td></tr></table>
<div class="common-tit"><span>机构提示信息</span></div>
<table><tr><td>机构提示信息</td><td>存在逾期未清算基金</td><td>指私募基金管理人存在超过到期日3个月且未提交清算申请的私募基金。</td></tr></table>
<div><span>管理人最近一次重大事项变更</span></div>
<div><span>基金业协会特别提示（针对私募基金管理人）</span></div>
<p>私募基金管理人名称和经营范围中不得包含“财富管理”等字样或者内容。</p>
<div><span>机构信息</span></div>
<table>
<!-- {row("机构网址", "注释里的不算")} -->
{row("登记编号", "P0000001")}{row("机构类型", "私募证券投资基金管理人")}
{row("注册资本(万元)(人民币)", "2,000")}{row("实缴资本(万元)(人民币)", "2,000")}{row("注册资本实缴比例", "100%")}
{row("全职员工人数", "5")}{row("取得基金从业人数", "4")}{row("管理规模区间", "0-5亿元")}
{row("机构信息最后更新时间", "2023-04-20")}
</table></body></html>"""

SELF_INTRO = ("公司获得国内大型综合金融集团的认可并注资，拥有信托、证券、期货、基金、股权投资、私募等牌照及知名主体，"
              "充分发挥综合金融服务。\n集团管理资产3800亿元，专注于金融服务与股权投资。\n公司规模：100-499人")


def test_parse_detail_page():
    d = parse(PAGE)
    s = summary(d)
    assert s["管理规模区间"] == "0-5亿元" and s["全职员工人数"] == "5" and "机构网址" not in s
    assert list(s["机构诚信信息"]) == ["信息报送异常", "五年内行政处罚"]
    assert s["机构诚信信息"]["信息报送异常"] == ["未按要求按时提交经审计的年度财务报告"]
    assert s["机构提示信息"] == ["存在逾期未清算基金"] and "财富管理" in s["协会特别提示"][0]
    assert scale_upper("0-5亿元") == 5e8 and scale_upper("100亿元以上") is None


def client(tmp_path, ok=True):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=PAGE) if ok else httpx.Response(503)
    return AmacDetailClient(tmp_path, transport=httpx.MockTransport(handler))


def services(detail):
    return Services(svc.licenses, svc.registry, svc.amac, svc.complaints, svc.packs, svc.extractor, svc.sources,
                    svc.registries, None, None, detail)


def make(tmp_path, text=None, ok=True, need="我妈想存 20 万理财"):
    return new_case(CaseIn(company_name=NAME, need=need, material_text=text), keyword_intake(need),
                    services(client(tmp_path, ok)))


def test_detail_flows_into_raw_and_signals(tmp_path):
    case = make(tmp_path)
    v = case.versions[-1]
    raw = next(r for r in case.raw if r.source_id == "amac_detail")
    assert raw.kind == "official" and raw.as_of == "2023-04-20" and raw.url.startswith("https://gs.amac.org.cn")
    items = {f"{s.key}.{i.key}": i for s in v.signals for i in s.items}
    assert items["credit.amac_integrity"].status is Status.bad          # 有行政处罚
    assert items["risk.amac_tips"].status is Status.warn and "财富管理" in items["risk.amac_tips"].detail
    assert items["finance.amac_scale"].value == "0-5亿元" and "全职员工 5 人" in items["finance.amac_scale"].detail
    assert items["risk.pf_threshold"].status is Status.bad              # 20 万买不了私募


def test_own_claims_checked_against_lists_and_amac(tmp_path):
    v = make(tmp_path, SELF_INTRO).versions[-1]
    claims = {a.kind.value: a for a in v.assertions}
    q = claims["qualification"]
    lic = next(c for c in q.checks if c.label == "宣称的牌照")
    assert lic.status is Status.bad and "基金、私募：有" in lic.result and "信托、期货：查了" in lic.result
    assert "证券、股权投资：没有可查的名单" in lic.result
    assert q.verdict.value == "misleading" and "只登记了私募基金管理人" in q.plain
    s = claims["scale"]
    assert s.verdict.value == "misleading" and "0-5亿元" in s.plain and "全职员工 5 人" in s.plain
    charts = {c.id: c for c in v.charts}
    assert [p.value for p in charts["aum"].points] == [3.8e11, 5e8]
    assert [p.value for p in charts["staff"].points] == [100, 5]


def test_cached_page_is_used_when_offline(tmp_path):
    make(tmp_path)                                    # 第一次在线，存下页面
    case = make(tmp_path, ok=False)                   # 第二次网络不通
    raw = next(r for r in case.raw if r.source_id == "amac_detail")
    assert "缓存" in raw.note and raw.content["管理规模区间"] == "0-5亿元"
    gone = make(tmp_path / "empty", ok=False)         # 网络不通、也没缓存
    assert next(r for r in gone.raw if r.source_id == "amac_detail").coverage.value == "failed"


def test_capital_claim_checked_against_amac_when_no_registry_data(tmp_path):
    text = "杭州巨鲸财富管理有限公司成立于2015年4月，注册资本2000万元人民币。"
    v = make(tmp_path, text).versions[-1]
    cap = next(a for a in v.assertions if a.kind.value == "capital")
    assert cap.kind_label == "注册资本" and cap.verdict.value == "consistent"   # 2000 万不超过公示的 2000 万，实缴 100%
    assert any(c.label == "实缴资本（中基协公示）" for c in cap.checks)


def test_background_question_follows_the_claim(tmp_path):
    v = make(tmp_path, SELF_INTRO).versions[-1]
    assert any("金融集团注资" in q.ask for q in v.questions) and not any("国资背景" in q.ask for q in v.questions)


def test_claim_checks_do_not_shift_signal_items(tmp_path):
    # "宣称的牌照"插在资格核验最前面，信号条目要按检查名对上，不能按位置错一位
    v = make(tmp_path, SELF_INTRO).versions[-1]
    items = {f"{s.key}.{i.key}": i for s in v.signals for i in s.items}
    assert items["risk.bank_list"].label == "持牌机构名单" and "持牌名单" in items["risk.bank_list"].value
    assert items["risk.amac"].label == "私募基金管理人登记" and items["risk.amac"].value.startswith("已登记")
    assert items["risk.scope"].label == "经营范围" and items["risk.product_code"].label == "理财产品登记编码"
    assert not any(i.label == "宣称的牌照" for i in items.values())
