"""二次分析的变化清单：程序逐条比对两版，不靠模型判断"有没有变"。

比对单位：说法（A1…A9，id 按类型固定）、缺项（M1）、信号条目（risk.bank_list 这样的 key）。
没变的也列出来："没有变化"本身就是结论。
"""
import re

from app.models import Change, Status, Verdict, Version

VERDICT_RANK = {Verdict.mismatch: 4, Verdict.redline: 4, Verdict.misleading: 3, Verdict.attention: 3,
                Verdict.unverifiable: 2, Verdict.consistent: 1}
STATUS_RANK = {Status.bad: 4, Status.warn: 3, Status.miss: 2, Status.none: 1, Status.ok: 0}
STATUS_LABEL = {Status.bad: "有问题", Status.warn: "要留意", Status.miss: "该有的没有", Status.none: "没查", Status.ok: "没问题"}
CONCERN = 3  # 新出现的条目达到这个严重程度，算"新疑点"


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _entries(v: Version) -> dict[str, tuple[str, int, str, list[str]]]:
    """key → (名称, 严重程度, 状态描述, 原文)"""
    out = {}
    for a in v.assertions:
        out[a.id] = (f"它说的\"{a.kind_label}\"", VERDICT_RANK[a.verdict], a.verdict_label, a.quotes)
    for m in v.missing:
        out[m.id] = (f"该写的没写：{m.text}", STATUS_RANK[Status.miss], "该有的没有", [])
    for s in v.signals:
        for i in s.items:
            out[f"{s.key}.{i.key}"] = (f"{s.title} · {i.label}", STATUS_RANK[i.status],
                                       f"{STATUS_LABEL[i.status]}（{i.value}）", [])
    return out


def _evidence(quotes: list[str], new_texts: dict[str, str]) -> tuple[list[str], str | None]:
    for q in quotes:
        for rid, text in new_texts.items():
            if _flat(q) in _flat(text):
                return [rid], q
    return [], None


def diff(prev: Version, cur: Version, new_texts: dict[str, str]) -> tuple[list[Change], str]:
    """new_texts：这次补充的信息，RawRecord id → 原文。改需求时为空。"""
    before, after = _entries(prev), _entries(cur)
    changes: list[Change] = []
    for key in list(after) + [k for k in before if k not in after]:
        if key in after:
            label, rank, state, quotes = after[key]
        else:
            label, rank, state, quotes = before[key]
        because, quote = _evidence(quotes, new_texts)
        because = because or (list(new_texts) if new_texts else [])
        said = f"，新信息里写着\"{quote}\"" if quote else ""

        if cur.trigger == "need" and (key not in before or key not in after):
            # 只改了需求：事实没变，是看的范围变了
            kind, state_ = ("added", state) if key not in before else ("removed", before[key][2])
            plain = f"换了需求，{'要多看一项' if kind == 'added' else '这一项不再需要看'}：{label}（{state_}）。"
            changes.append(Change(target=key, label=label, kind=kind, before=None if kind == "added" else state_,
                                  after=state_ if kind == "added" else None, plain=plain))
            continue
        if key not in before:
            kind = "new_concern" if rank >= CONCERN else "added"
            plain = f"{'新疑点' if kind == 'new_concern' else '新增'}：{label}，{state}{said}。"
            changes.append(Change(target=key, label=label, kind=kind, after=state, because=because, quote=quote,
                                  plain=plain))
            continue
        b_label, b_rank, b_state, _ = before[key]
        if key not in after:
            plain = f"{label}这一条不再出现（上一版是：{b_state}）。"
            changes.append(Change(target=key, label=label, kind="removed", before=b_state, because=because,
                                  plain=plain))
        elif rank > b_rank:
            changes.append(Change(target=key, label=label, kind="worse", before=b_state, after=state, because=because,
                                  quote=quote, plain=f"{label}从\"{b_state}\"变成\"{state}\"{said}。"))
        elif rank < b_rank:
            changes.append(Change(target=key, label=label, kind="clarified", before=b_state, after=state,
                                  because=because, quote=quote,
                                  plain=f"{label}从\"{b_state}\"变成\"{state}\"{said}，比上一版轻了。"))
        else:
            changes.append(Change(target=key, label=label, kind="unchanged", before=b_state, after=state, because=[],
                                  plain=f"{label}没变，仍是\"{state}\"。"))
    return changes, summarize(prev, cur, changes)


def summarize(prev: Version, cur: Version, changes: list[Change]) -> str:
    count = {k: sum(c.kind == k for c in changes) for k in
             ("new_concern", "worse", "clarified", "added", "removed", "unchanged")}
    moved = len(changes) - count["unchanged"]
    if cur.trigger == "need":
        head = (f"事实没变，看的重点变了：从\"{prev.scenario_label}\"改成\"{cur.scenario_label}\"，报告的排序和措辞跟着调整。"
                if prev.scenario != cur.scenario else "事实没变，需求的说法变了，报告的排序和措辞跟着调整。")
        if moved:
            head += f"有 {moved} 项检查因为需求不同而加上或去掉。"
        return head
    if not moved:
        return f"没有影响判断的变化：{count['unchanged']} 项都和上一版一样。"
    parts = [f"{count['new_concern'] + count['worse']} 项更严重" if count["new_concern"] + count["worse"] else "",
             f"{count['clarified']} 项减轻" if count["clarified"] else "",
             f"{count['added']} 项新增" if count["added"] else "",
             f"{count['removed']} 项不再出现" if count["removed"] else ""]
    return f"{moved} 项有变化（{'，'.join(p for p in parts if p)}），其余 {count['unchanged']} 项没变。"
