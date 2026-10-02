"""等结果时的进度：建案卷、补充信息时，每走完一步发一条事件，给前端的等待动画用。

只报真的发生了的事：
- 每一步开始发 start，走完发 done。done 带这一步的真实结果：查到 / 查了没有 / 没查 / 没查成，外加一句话。
- 没走的步骤也发 done，写明为什么没走（比如虚构公司不联网搜），不悄悄跳过。开头的 begin 列出的步骤都会有 done。
- 一句话只说查没查到、查到几条，不下结论；好坏由报告里的规则说。
- 没有总进度百分比：一共要多久，事先不知道。

事件交给当前请求的接收者（ContextVar）；普通接口没有接收者，start / done 什么都不做。
"""
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar

from app.analysis.fmt import wan
from app.models import Coverage, Intake, RawRecord
from app.sources.registries import LICENSE_LISTS

Sink = Callable[[dict], None]
_sink: ContextVar[Sink | None] = ContextVar("xray_progress", default=None)

# 步骤 id → 名字，按实际发生的顺序。前端的等待动画按 id 对应房间里的位置
STEPS = {
    "intake": "读懂需求",
    "lists": "持牌名单",
    "amac": "中基协私募登记",
    "registry": "工商登记",
    "finance": "财务数据",
    "pack": "人工摘录的文书",
    "web": "政府网站",
    "opinion": "新闻舆情和网上投诉",
    "reviews": "本站用户评价",
    "rules": "对照规则",
    "plain": "写成短句",
}
# 查资料的步骤：done 带 coverage。其余三步（读需求、对照规则、写短句）是处理，coverage 为 null
LOOKUPS = {"lists", "amac", "registry", "finance", "pack", "web", "opinion", "reviews"}
GROUPS = {"lists": {"nfra_bank_list", *LICENSE_LISTS}, "amac": {"amac", "amac_detail"},
          "registry": {"registry", "annual_report"}, "finance": {"qcc_finance"}, "web": {"web_official"},
          "opinion": {"qcc_news", "web_news", "complaints"}, "reviews": {"user_reviews"}}
GROUPED = set().union(*GROUPS.values())
KIND_LABEL = {"collected": "人工证据包", "commercial": "企查查商业数据", "demo": "演示数据"}


def _in_step(step: str, r: RawRecord) -> bool:
    if step == "pack":  # 证据包里摘的文书和公司自述；登记、中基协、投诉那几段归各自的步骤
        return r.source_id == "self_description" or (r.kind == "collected" and r.source_id not in GROUPED)
    return r.source_id in GROUPS[step]


def _coverage(recs: list[RawRecord]) -> Coverage:
    covs = {r.coverage for r in recs}
    for c in (Coverage.found, Coverage.failed, Coverage.not_found):
        if c in covs:
            return c
    return Coverage.not_covered


def _found(recs: list[RawRecord]) -> list[RawRecord]:
    return [r for r in recs if r.coverage is Coverage.found]


def _lists_text(recs: list[RawRecord]) -> str:
    hits = [r.title.split(" · ")[0] for r in _found(recs)]
    return f"{len(recs)} 份名单里，{'、'.join(hits)}有它" if hits else f"查了 {len(recs)} 份名单，都没有它"


def _amac_text(recs: list[RawRecord]) -> str:
    main = next((r for r in recs if r.source_id == "amac"), None)
    detail = next((r for r in recs if r.source_id == "amac_detail"), None)
    if main is None or main.coverage is Coverage.not_covered:
        return "没查：中基协名单还没下载"
    if main.coverage is Coverage.not_found:
        return "查了，没有登记"
    rec = (main.content or {}).get("记录") if isinstance(main.content, dict) else None
    no = (rec or {}).get("register_no") if isinstance(rec, dict) else None
    text = f"已登记 {no}" if no else "已登记"
    if detail is not None:
        text += "，取到公示详情页" if detail.coverage is Coverage.found else "，详情页没取到"
    return text + ("（演示数据）" if main.kind == "demo" else "")


def _registry_text(recs: list[RawRecord]) -> str:
    reg = next((r for r in recs if r.source_id == "registry"), None)
    if reg is None or reg.coverage is Coverage.not_covered:
        return "没查：要人工到国家企业信用信息公示系统查"
    label = KIND_LABEL.get(reg.kind, reg.kind)
    return {Coverage.found: f"查到登记信息（{label}）", Coverage.not_found: f"查了，没查到这家公司（{label}）",
            Coverage.failed: f"没查成（{label}）"}[reg.coverage]


def _pack_text(recs: list[RawRecord]) -> str:
    return f"{len(recs)} 份，项目组从官方网站摘录" if recs else "没有人工摘录的材料"


def _replay(recs: list[RawRecord]) -> str:
    return "（离线回放）" if any("离线回放" in (r.note or "") for r in recs) else ""


def _web_text(recs: list[RawRecord]) -> str:
    # 是搜到的页面数，不是"点名它的文件"数：哪些文件以它为当事人，由报告里的规则去分
    n = len(_found(recs))
    if n:
        return f"搜到政府网站页面 {n} 个" + _replay(recs)
    if any(r.coverage is Coverage.failed for r in recs):
        return "搜索失败"
    return ("搜了，没找到点名它的页面" if recs else "没查") + _replay(recs)


def _opinion_text(recs: list[RawRecord]) -> str:
    found = _found(recs)
    parts = []
    news = next((r for r in found if r.source_id == "qcc_news"), None)
    if news is not None and isinstance(news.content, dict):
        neg = len(news.content.get("负面新闻") or [])
        parts.append(f"新闻 {news.content.get('平台记录总数', 0)} 条（最近 {news.content.get('返回的最近几条', 0)} 条里"
                     f"企查查标负面 {neg} 条）")
    parts += [f"网上投诉和报道 {n} 条" for n in [sum(r.source_id == "web_news" for r in found)] if n]
    parts += ["投诉记录（演示数据）" for r in found if r.source_id == "complaints"][:1]
    failed = any(r.coverage is Coverage.failed for r in recs)
    if parts:
        text = "查到" + "、".join(parts) + ("；有一项没查成" if failed else "")
    elif failed:
        text = "没查成"
    elif any(r.coverage is Coverage.not_found for r in recs):
        text = "查了，没有新闻，也没搜到投诉"
    else:
        text = "没查"
    return text + _replay(recs)


def _reviews_text(recs: list[RawRecord]) -> str:
    n = sum(len(r.content) for r in recs if isinstance(r.content, list))
    return f"{n} 条，别人说的，未核实" if n else "还没有人写评价"


def _finance_text(recs: list[RawRecord]) -> str:
    rec = next(iter(recs), None)
    if rec is None or rec.coverage is Coverage.not_covered:
        return "没查"
    if rec.coverage is Coverage.failed:
        return "没查成"
    if rec.coverage is Coverage.not_found:
        return "查了，没有公开的财务数据（非上市公司一般不公开）"
    periods = (rec.content or {}).get("报告期") or []
    return f"取到 {len(periods)} 个报告期，最新是{periods[0]['报告期']}" if periods else "取到财务数据"


TEXT = {"lists": _lists_text, "amac": _amac_text, "registry": _registry_text, "pack": _pack_text,
        "web": _web_text, "finance": _finance_text, "opinion": _opinion_text, "reviews": _reviews_text}


def intake_text(info: Intake) -> str:
    extra = [wan(info.amount) if info.amount else None, f"替{info.for_whom}看" if info.for_whom else None]
    return "识别为：" + info.scenario_label + "".join(f"，{x}" for x in extra if x)


# ---------- 发事件 ----------

def _emit(event: dict) -> None:
    sink = _sink.get()
    if sink is not None:
        sink(event)


def begin(kind: str, company: str, *, intake: bool) -> dict:
    """第一条事件：这次要走哪些步骤。kind 是 create（建案卷）或 supplement（补充信息）。"""
    steps = [s for s in STEPS if intake or s != "intake"]
    return {"type": "begin", "kind": kind, "company": company,
            "steps": [{"id": s, "label": STEPS[s], "lookup": s in LOOKUPS} for s in steps]}


def start(step: str) -> None:
    _emit({"type": "step", "id": step, "label": STEPS[step], "phase": "start"})


def done(step: str, records: Iterable[RawRecord] = (), *, text: str | None = None,
         coverage: Coverage | None = None) -> None:
    """一步走完。查资料的步骤从这一步的原始记录算结果和那句话；处理步骤直接给 text。"""
    if _sink.get() is None:
        return
    event = {"type": "step", "id": step, "label": STEPS[step], "phase": "done", "coverage": None, "counts": None}
    if step in LOOKUPS:
        recs = [r for r in records if _in_step(step, r)]
        cov = coverage or _coverage(recs)
        counts = {c.value: sum(r.coverage is c for r in recs) for c in Coverage}
        event |= {"coverage": cov.value, "counts": counts, "text": text or TEXT[step](recs)}
    else:
        event["text"] = text or ""
    _emit(event)


def skip(step: str, why: str) -> None:
    """这一步没走：照样发 done，coverage 是"没查"，写明为什么。"""
    start(step)
    done(step, coverage=Coverage.not_covered, text=why)


@contextmanager
def reporting(sink: Sink):
    """在这个上下文里（同一个线程）发生的 start / done，都交给 sink。"""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)
