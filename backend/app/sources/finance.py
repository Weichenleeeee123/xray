"""财务数据：企查查智能体平台的 get_financial_data（上市、发债等公开披露财报的公司才有）。

- 只摘原样给出的数：营业总收入、净利润、总资产、资产负债率、营收同比、加权净资产收益率。
  比率是平台服务端算好的，照抄，不自己重算。
- 不判断高低：银行的资产负债率 90% 以上是常态，经营现金流为负也常见。唯一标出来的是净利润为负（亏损）。
- 查了没有（非上市公司一般不公开财报）写"没有公开的财务数据"，不等于经营差。
"""
import re
from dataclasses import dataclass, field

from app.sources.qcc_agent import EMPTY, is_empty

PERIOD = re.compile(r"(20\d{2})年(年报|三季报|中报|一季报)")
ORDER = {"一季报": 1, "中报": 2, "三季报": 3, "年报": 4}


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "")) if str(v).strip() not in ("", "-", "--", "None") else None
    except ValueError:
        return None


@dataclass
class Period:
    label: str                      # "2025年年报"
    year: int
    kind: str                       # 年报 / 三季报 / 中报 / 一季报
    revenue: float | None = None    # 营业总收入，元
    net_profit: float | None = None
    total_assets: float | None = None
    revenue_yoy: float | None = None   # 营业收入同比，%
    debt_ratio: float | None = None    # 资产负债率，%
    roe: float | None = None           # 加权净资产收益率，%


@dataclass
class FinancialFindings:
    coverage: str                   # found / not_found / failed
    periods: list[Period] = field(default_factory=list)   # 新的在前
    retrieved_at: str | None = None
    error: str | None = None
    summary: str = ""

    @property
    def latest_annual(self) -> Period | None:
        return next((p for p in self.periods if p.kind == "年报"), None)

    @property
    def latest(self) -> Period | None:
        return self.periods[0] if self.periods else None


def parse(data: dict | None) -> list[Period]:
    out = []
    for row in (data or {}).get("财务数据信息") or []:
        m = PERIOD.search(str(row.get("报告期") or ""))
        if not m:
            continue
        d = row.get("指标详情") or {}
        main, report = d.get("主要财务指标") or {}, d.get("财务报表") or {}
        income, sheet = report.get("利润表") or {}, report.get("资产负债表") or {}
        ana = d.get("分析数据") or {}
        p = Period(label=m.group(0), year=int(m.group(1)), kind=m.group(2),
                   revenue=_num(income.get("营业总收入") or main.get("营业总收入")),
                   net_profit=_num(income.get("净利润")),
                   total_assets=_num(sheet.get("资产合计") or main.get("总资产")),
                   revenue_yoy=_num((ana.get("成长能力") or {}).get("营业收入同比")),
                   debt_ratio=_num((ana.get("偿还能力") or {}).get("资产负债率")),
                   roe=_num((ana.get("盈利能力") or {}).get("加权净资产收益率")))
        if any(v is not None for v in (p.revenue, p.net_profit, p.total_assets)):
            out.append(p)
    return sorted(out, key=lambda p: (p.year, ORDER[p.kind]), reverse=True)


def findings(call) -> FinancialFindings:
    """call 是 QccAgentClient.call 的结果（data / error / retrieved_at）。"""
    if call.error:
        return FinancialFindings("failed", retrieved_at=call.retrieved_at, error=call.error)
    data = call.data or {}
    periods = parse(data)
    said = str(data.get("摘要") or data.get("搜索结果") or "")
    if periods:
        return FinancialFindings("found", periods, call.retrieved_at, summary=said)
    if not data or is_empty(data) or EMPTY.search(said):
        return FinancialFindings("not_found", retrieved_at=call.retrieved_at, summary=said)
    return FinancialFindings("failed", retrieved_at=call.retrieved_at, error="返回的数据认不出报告期", summary=said)


def yi(v: float | None) -> str:
    """元 → "387.99 亿元" / "3,174 万元"。"""
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.2f} 亿元"
    if abs(v) >= 1e4:
        return f"{v / 1e4:,.0f} 万元"
    return f"{v:,.0f} 元"


def pct(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"
