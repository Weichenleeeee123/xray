"""一页结论：用模板拼，不依赖模型也能出结果。

只说四件事：查到了什么、哪里对不上、还不知道什么、下一步先确认什么。
不打安全分，不下"诈骗"之类的定性。三栏合计最多 5 条，A4 一页放得下。
"""
from app.analysis.fmt import wan
from app.models import (Assertion, MissingItem, OnePager, OnePagerLine, Question, Scenario, Signal, SignalItem, Source,
                        Status)

LIMIT = 5
# 这些信号条目和某条说法的结论重复，有说法时不再单列
DUP_OF_CLAIM = {"risk.bank_list": "A1", "risk.amac": "A1", "risk.product_code": "A1", "risk.scope": "A1",
                "risk.promise": "A2", "risk.payee": "A7", "risk.refund": "A8", "risk.upfront_fee": "A9",
                "risk.disclosure": "M1"}
# "查到了什么"优先展示的事实
FACT_KEYS = ["risk.bank_list", "credit.status", "finance.paid_capital", "reputation.total", "credit.penalties",
             "finance.insured"]
FOOTER = "结论来自公开记录和规则，AI 只负责读材料和说人话。这不是安全评分，也不是对这家公司的定性；没查到不等于没有问题。"


def _item_line(sig: Signal, item: SignalItem) -> OnePagerLine:
    tail = f"（{item.detail}）" if item.detail and len(item.detail) <= 30 else ""
    return OnePagerLine(text=f"{item.label}：{item.value}{tail}", refs=[f"{sig.key}.{item.key}", *filter(None, [item.ref])])


def _claim_line(a: Assertion) -> OnePagerLine:
    return OnePagerLine(text=f"它说的\"{a.kind_label}\"{a.verdict_label}：{a.plain}", refs=[a.id, *a.refs])


def _columns(assertions: list[Assertion], missing: list[MissingItem], signals: list[Signal]):
    """哪里对不上 = 它的说法和记录对照的结果；查到了什么 = 记录本身；还不知道什么 = 没查和核不了的。"""
    claim_ids = {a.id for a in assertions} | {m.id for m in missing}
    items = [(s, i) for s in signals for i in s.items if DUP_OF_CLAIM.get(f"{s.key}.{i.key}") not in claim_ids]

    mismatch = [_claim_line(a) for a in assertions if a.color == "red"]
    mismatch += [OnePagerLine(text=f"该写的没写：\"{m.text}\"", refs=[m.id, *m.refs]) for m in missing]
    mismatch += [_claim_line(a) for a in assertions if a.color == "amber"]

    by_key = {f"{s.key}.{i.key}": (s, i) for s, i in items}
    found = [_item_line(s, i) for s, i in items if i.status is Status.bad]
    found += [_item_line(s, i) for s, i in items if i.status is Status.warn]
    found += [_item_line(*by_key[k]) for k in FACT_KEYS if k in by_key and by_key[k][1].status is Status.ok]
    found += [_claim_line(a) for a in assertions if a.color == "green"]

    unknown = [_claim_line(a) for a in assertions if a.color == "grey"]
    unknown += [OnePagerLine(text=f"{i.label}：{i.value}" + (f"（{i.detail}）" if i.detail else ""),
                             refs=[f"{s.key}.{i.key}", *filter(None, [i.ref])])
                for s, i in items if i.status in (Status.none, Status.miss)]
    return mismatch, found, unknown


def _headline(assertions: list[Assertion], missing: list[MissingItem], signals: list[Signal], unknown: int) -> str:
    red = sum(a.color == "red" for a in assertions) + len(missing)
    amber = sum(a.color == "amber" for a in assertions)
    bad = sum(i.status is Status.bad for s in signals for i in s.items
              if DUP_OF_CLAIM.get(f"{s.key}.{i.key}") not in {a.id for a in assertions} | {m.id for m in missing})
    parts = []
    if assertions or missing:
        parts.append(f"它的说法里有 {red} 处和记录对不上" + (f"、{amber} 处要留意" if amber else ""))
    else:
        parts.append("还没有它的说法可以对照")
    parts.append(f"记录里有 {bad} 项不良情况" if bad else "查到的记录里没有不良情况")
    parts.append(f"还有 {unknown} 项没查到" + ("，没查不等于没问题" if not bad and not red else ""))
    return "；".join(parts) + "。"


def _fit(mismatch: list, found: list, unknown: list) -> tuple[list, list, list]:
    """三栏合计最多 5 条：对不上的先放（最多 3 条），查到的和不知道的各至少留 1 条。"""
    m = mismatch[:3]
    f = found[:1]
    u = unknown[:1]
    for pool, col in ((mismatch, m), (found, f), (unknown, u)):
        for line in pool[len(col):]:
            if len(m) + len(f) + len(u) >= LIMIT:
                break
            col.append(line)
    return m, f, u


def _as_of(sources: dict[str, Source], used: set[str]) -> str:
    parts = []
    for sid in ("nfra_bank_list", "registry", "complaints"):
        s = sources.get(sid)
        if s and sid in used and s.as_of:
            tag = "（演示数据）" if s.kind == "demo" else ""
            parts.append(f"{s.name} {s.as_of}{tag}")
    return "资料截至：" + "；".join(parts) if parts else ""


def onepager(*, company_name: str, for_whom: str | None, amount: float | None, scenario: Scenario,
             assertions: list[Assertion], missing: list[MissingItem], signals: list[Signal],
             questions: list[Question], sources: dict[str, Source], audience: str = "family") -> OnePager:
    mismatch, found, unknown = _columns(assertions, missing, signals)
    m, f, u = _fit(mismatch, found, unknown)
    used = {i.source for s in signals for i in s.items if i.status is not Status.none}
    money = f" · {scenario.hand_over} {wan(amount)}" if amount else ""
    headline = _headline(assertions, missing, signals, len(unknown))
    next_steps = [OnePagerLine(text=f"{q.ask}（{q.check_where}）", refs=[q.id, *q.linked]) for q in questions[:3]]
    footer = " ".join(filter(None, [FOOTER, _as_of(sources, used)]))

    if audience == "teller":
        subject = f"客户拟交给 {company_name}：{scenario.hand_over}" + (f" {wan(amount)}" if amount else "")
        return OnePager(audience="teller", title="网点提示单", subject=subject,
                        headline=headline + "建议客户先核实下面三件事，再办理。",
                        found=found[:LIMIT], mismatch=mismatch[:LIMIT], unknown=u, next_steps=next_steps,
                        footer="供柜面参考：依据为公开记录和客户提供的材料，不构成对该公司的法律定性。 " + _as_of(sources, used))
    who = "给自己看" if for_whom in (None, "自己") else f"替{for_whom}看"
    return OnePager(audience="family", title=scenario.onepager_title, subject=f"{who}：{company_name}{money}",
                    headline=headline, found=f, mismatch=m, unknown=u, next_steps=next_steps, footer=footer)
