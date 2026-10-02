"""登记数据整份没拿到时，说清楚是哪一种：查了没成功、查了没有这家、还是没接数据源。

条目生成时只知道"没有公司记录"，不知道为什么；原因在登记那条原始记录的 coverage 和 note 里。
这里在一版报告生成时统一补上，免得积分用完、名字对不上、网络出错都显示成同一句"没查"。
"""
from app.models import Assertion, Coverage, RawRecord, Signal, Status

REGISTRY_SOURCES = ("registry", "annual_report")
FICTIONAL_WEB = "虚构的演示公司，不联网搜索"


def registry_reason(registry: RawRecord | None) -> tuple[str, str, str] | None:
    """(gap, 条目值, 原因)。登记查到了，或者根本没有登记记录，返回 None。"""
    if registry is None or registry.coverage is Coverage.found:
        return None
    note = (registry.note or "").removeprefix("没查：")
    if "对不上" in note:
        return "not_found", "名字对不上", ("按这个名字查到的是别的公司，没有采用。请用营业执照上的全称，"
                                         "或者从候选公司里选一家再查")
    if registry.coverage is Coverage.failed:
        if "积分" in note:
            return "failed", "没查成", f"登记信息这次没查成：企业数据查询额度用完了（{note}）。调高额度或重启服务后重查"
        return "failed", "没查成", f"登记信息这次没查成：{note or '查询出错'}。稍后重查即可"
    if registry.coverage is Coverage.not_found:
        return "not_found", "查无记录", note or "按这个名字没有查到登记记录，请核对公司全称"
    return "not_covered", "没查", note or "还没有这家公司的登记数据"


def explain_gaps(signals: list[Signal], assertions: list[Assertion], registry: RawRecord | None,
                 fictional: bool) -> str | None:
    """改写受影响的条目和检查；返回给"版本与阅读说明"的一句话（登记查到了返回 None）。"""
    reason = registry_reason(registry)
    for s in signals:
        for it in s.items:
            if it.status is not Status.none:
                continue
            if fictional and it.key == "official_web" and it.gap == "not_covered":
                it.value, it.detail, it.gap = "不适用", FICTIONAL_WEB, "not_applicable"
            elif reason and it.gap == "not_covered" and it.source in REGISTRY_SOURCES:
                it.gap, it.value, it.detail = reason[0], reason[1], reason[2]
    if reason:
        for a in assertions:
            for c in a.checks:
                if c.status is Status.none and c.gap == "not_covered" and c.source in REGISTRY_SOURCES:
                    c.gap, c.result = reason[0], f"{reason[1]}：{reason[2]}"
    if reason is None:
        return None
    gap, _, why = reason
    if gap == "failed":
        return f"{why}；股东、资本、处罚等核验这一版暂时没有结果。持牌名单是真实数据，照常核验。"
    if gap == "not_found":
        return f"{why}。股东、资本、处罚等核验没有结果；查不到登记的公司，交钱前务必先弄清它的全称和身份。"
    return f"{why}：股东、资本、处罚等核验显示为\"没查\"。持牌名单是真实数据，照常核验。"
