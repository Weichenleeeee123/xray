"""一眼看懂：报告生成时一并写好的短句和名词解释。

判定、颜色、排序全部来自规则。模型只做两件事：
1. 把规则写的长句缩成 18 个字以内的短句，只能用原句里的事实和数字；
2. 找出报告里固定词表没有的专业名词，写一句一般含义（前端标"AI 解释"）。
每条都由程序校验：短句里的数字必须在原句里出现，不许越界；名词必须在报告里一字不差出现、不提这家公司。
校验不过的丢掉，前端退回规则原句。模型不可用时，短句为空、名词只用固定词表，报告照常生成。
上一版已经写好、原句没变的短句和名词直接沿用，不重新生成，二次分析时没变的条目措辞也不变。
"""
import hashlib
import json
import re

from pydantic import BaseModel, Field

from app import config, progress
from app.assistant import SPECULATION, VERDICT_WORDS, citable, evidence_text, overreach
from app.glossary import find_terms, load_glossary
from app.llm import LLM, LLMError, request_budget
from app.models import Case, Glance, Status, Term, Version
from app.scenarios import get_scenario
from app.sources.web import short_name

SHORT_MAX = 18
TERM_MAX = 6
NUM = re.compile(r"\d+(?:[.,]\d+)*")
FLAGGED = {Status.bad, Status.warn, Status.miss}
STATUS_LABEL = {"bad": "有问题", "warn": "要留意", "miss": "该有的没有", "none": "没查", "ok": "没问题",
                "red": "与记录不符或不合规", "amber": "有误导或要留意", "grey": "无法核验", "green": "与记录相符"}
# 原句里有这些词，短句也必须有：丢了意思就反了（"未登记（不需要私募登记）"缩成"未登记"）
QUALIFIERS = ("不需要", "不等于", "不代表")

SYSTEM = """你是 X-Ray 的编辑，把企业核查报告里规则写的长句缩成一眼能看懂的短句，并找出普通人看不懂的名词。必须遵守：
1. 每个条目都要给短句，id 原样返回；每条短句只能用它自己那条原句里的内容，不要串到别的条目。短句不超过 16 个字，只能用原句里的事实和数字，不许加原句里没有的数字、判断或推测。
   保留"查不到""没写""是个人"这类关键否定，也保留括号里改变意思的原因（比如"它是持牌机构，不需要私募登记"）。
   短句的意思要和"状态"一致：状态是"没问题"的，读起来就该是没问题。
2. 不说"安全""可靠""诈骗"之类的定性，不推测后果。
3. 名词：从<报告文字>里找出普通人可能看不懂、又不在<已有词表>里的专业名词，最多 6 个；名词必须是报告里一字不差出现的写法。每个用一句话（不超过 50 字）解释这个词的一般含义，不要提这家公司。没有就给空列表。
只输出 JSON：{"short": {"A1": "短句"}, "terms": [{"term": "名词", "plain": "解释"}]}"""


class _GenTerm(BaseModel):
    term: str
    plain: str


class _Gen(BaseModel):
    short: dict[str, str] = Field(default_factory=dict)
    terms: list[_GenTerm] = Field(default_factory=list)


def first_items(v: Version) -> list[str]:
    """场景配置里回答"第一问"的条目，只留这一版里有的。"""
    have = {a.id for a in v.assertions} | {f"{s.key}.{i.key}" for s in v.signals for i in s.items}
    return [i for i in get_scenario(v.scenario).first_items if i in have]


def short_status(v: Version) -> dict[str, str]:
    """条目 id → 规则给的状态，告诉模型短句该是什么口气。"""
    out = {a.id: STATUS_LABEL[a.color] for a in v.assertions}
    out.update({m.id: STATUS_LABEL["miss"] for m in v.missing})
    out.update({f"{s.key}.{i.key}": STATUS_LABEL[i.status.value] for s in v.signals for i in s.items})
    return out


def short_context(v: Version) -> dict[str, str]:
    """每条的全部文字（原句、说法原文、检查明细），只用来校验短句，不发给模型。"""
    out = {a.id: " ".join([a.plain, a.text, *(f"{c.label} {c.result}" for c in a.checks)]) for a in v.assertions}
    out.update({m.id: f"{m.text} {m.plain}" for m in v.missing})
    out.update({f"{s.key}.{i.key}": " ".join(filter(None, [i.label, i.value, i.detail])) for s in v.signals for i in s.items})
    return out


def short_sources(v: Version) -> dict[str, str]:
    """要缩短的条目 id → 规则原句：每条说法、缺项、要看的信号条目、回答第一问的条目。"""
    out = {a.id: a.plain for a in v.assertions}
    out.update({m.id: m.plain for m in v.missing})
    first = set(first_items(v))
    for s in v.signals:
        for i in s.items:
            iid = f"{s.key}.{i.key}"
            if i.status in FLAGGED or iid in first:
                out[iid] = f"{i.label}：{i.value}" + (f"（{i.detail}）" if i.detail else "")
    return out


def visible_text(v: Version) -> str:
    """报告页上看得到的文字。名词只从这里找，找到的才标得出来。"""
    parts = []
    for a in v.assertions:
        parts += [a.text, a.plain, *(f"{c.label} {c.result}" for c in a.checks)]
    parts += [f"{m.text} {m.plain}" for m in v.missing]
    parts += [" ".join(filter(None, [i.label, i.value, i.detail])) for s in v.signals for i in s.items]
    parts += [f"{q.ask} {q.why} {q.check_where}" for q in v.questions]
    if v.onepager:
        op = v.onepager
        parts += [op.headline, *(line.text for line in op.found + op.mismatch + op.unknown + op.next_steps)]
    return "\n".join(parts)


CJK = re.compile(r"[一-龥]")


def _short_ok(s: str, src: str, data: str, ctx: str | None = None) -> bool:
    s = s.strip()
    if not s or len(s) > SHORT_MAX or overreach(s, data):
        return False
    # 短句里的字大半要出现在这一条自己的原文和检查明细里：模型把 A 的短句错放到 B 上时，这里会拦下
    chars = set(CJK.findall(s))
    if chars and len(chars & set(CJK.findall(ctx or src))) / len(chars) < 0.5:
        return False
    if any(q in src and q not in s for q in QUALIFIERS):
        return False
    # Do not accept removal of negation merely because most Chinese characters overlap.
    for concept in ("登记", "处罚", "转账", "持牌", "退款", "保本", "风险", "注销", "营业"):
        if concept in s and concept in src:
            negative = rf"(?:没有|未|不|无|禁止|不能|不可|不得)[^，。；（）]{{0,8}}{concept}"
            if "不需要" in s and "不需要" in src and concept != "登记":
                continue
            if bool(re.search(negative, src)) != bool(re.search(negative, s)):
                return False
    src_nums = {n.replace(",", "") for n in NUM.findall(src)}
    return all(n.replace(",", "") in src_nums for n in NUM.findall(s))   # 不许冒出原句里没有的数字


def _term_ok(t: _GenTerm, visible: str, known: set[str], company: str) -> bool:
    name, plain = t.term.strip(), t.plain.strip()
    names = {company} | ({short_name(company)} if short_name(company) else set())
    return (2 <= len(name) <= 12 and name in visible and name not in known and 0 < len(plain) <= 60
            and not any(n and n in plain for n in names)
            and not VERDICT_WORDS.search(plain) and not SPECULATION.search(plain))


def _gen_id(name: str) -> str:
    return "g" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]


def build_glance(case: Case, v: Version, llm: LLM, prev: Version | None = None) -> tuple[Glance, list[Term]]:
    sources = short_sources(v)
    visible = visible_text(v)
    data = evidence_text(case, citable(case, v))
    glossary_names = {n for t in load_glossary() for n in (t.term, *t.aliases)}

    # 上一版写好、原句没变的，直接沿用
    short: dict[str, str] = {}
    prev_terms: list[Term] = []
    if prev and prev.glance:
        prev_src = short_sources(prev)
        short = {i: s for i, s in prev.glance.short.items() if i in sources and prev_src.get(i) == sources[i]}
        prev_terms = [t for t in prev.terms if t.origin == "model" and t.term in visible]
    todo = {i: src for i, src in sources.items() if i not in short}
    known = glossary_names | {t.term for t in prev_terms}
    status = short_status(v)
    ctx = short_context(v)

    mode, dropped, new_terms = (prev.glance.mode if prev and prev.glance else "template"), 0, []
    if todo or prev is None or v.trigger in ("material", "reply"):
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps({
                        "需要缩短的条目": [{"id": i, "状态": status.get(i, ""), "原句": src} for i, src in todo.items()],
                        "报告文字": visible[:4000],
                        "已有词表": sorted(known)}, ensure_ascii=False)}]
        try:
            with request_budget(config.PLAIN_TIMEOUT):
                out, reply = llm.chat_json(messages, _Gen, cache_namespace=f"case:{case.id}:v:{v.no}:glance")
            mode = reply.mode
            for i, s in out.short.items():
                if i in todo and _short_ok(s, todo[i], data, ctx.get(i)):
                    short[i] = s.strip()
                else:
                    dropped += 1
            for t in out.terms[:TERM_MAX * 2]:
                if len(new_terms) < TERM_MAX and _term_ok(t, visible, known, case.case.company_name):
                    known.add(t.term.strip())
                    new_terms.append(Term(id=_gen_id(t.term.strip()), term=t.term.strip(), plain=t.plain.strip(),
                                          origin="model"))
                else:
                    dropped += 1
        except LLMError:
            mode = "template"

    terms = find_terms(visible) + prev_terms + new_terms
    return Glance(first=first_items(v), short=short, mode=mode, dropped=dropped), terms


def finish_version(case: Case, llm: LLM) -> Case:
    """给最新一版补上一眼看懂的短句和名词解释。建案卷、二次分析之后调用。"""
    v = case.versions[-1]
    prev = case.versions[-2] if len(case.versions) > 1 else None
    progress.start("plain")
    v.glance, v.terms = build_glance(case, v, llm, prev)
    progress.done("plain", text=_plain_text(v))
    return case


def _plain_text(v: Version) -> str:
    if v.glance.mode == "template":
        return "没用模型，报告用规则原句"
    gen = sum(t.origin == "model" for t in v.terms)
    return (f"写好 {len(v.glance.short)} 条短句" + (f"，补了 {gen} 个名词解释" if gen else "") +
            ("（离线回放）" if v.glance.mode == "replay" else ""))
