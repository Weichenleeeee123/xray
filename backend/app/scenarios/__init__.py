"""场景模板：一个场景就是一份 JSON，不为每个场景单写代码。

场景只影响三件事：查哪些资格、重点核哪些说法（排序）、报告的排序和措辞。
这里还有关键词兜底识别：模型识别不可用时，用它从需求里认出场景、关注点、替谁看、金额。
"""
import json
import re
from functools import cache

from app.config import SCENARIOS_DIR
from app.models import ClaimKind, Intake, Scenario

DEFAULT_ID = "general"
# 关键词打平时的优先顺序：主演示场景在前
PRIORITY = ["savings", "takeover", "job", "prepaid", "contract", "general"]


@cache
def load_scenarios() -> dict[str, Scenario]:
    found = {}
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        s = Scenario(**json.loads(path.read_text(encoding="utf-8")))
        found[s.id] = s
    return {k: found[k] for k in sorted(found, key=lambda k: PRIORITY.index(k) if k in PRIORITY else 99)}


def get_scenario(sid: str | None) -> Scenario:
    scenarios = load_scenarios()
    return scenarios.get(sid or DEFAULT_ID, scenarios[DEFAULT_ID])


def claim_rank(scenario: Scenario):
    """说法排序：场景关心的在前，其余按默认顺序。什么都不藏。"""
    order = list(scenario.claim_kinds) + [k for k in ClaimKind if k not in scenario.claim_kinds]
    return lambda kind: order.index(kind)


# ---------- 关键词兜底识别 ----------

FOCUS_RULES = [
    (re.compile(r"取不出|取不回|拿不回|急用|随时取|拿回来|取出来|赎回|退出|退钱|退款|退不了|退费"), "急用时钱能不能拿回来"),
    (re.compile(r"亏|保本|本金|血本"), "本金会不会亏"),
    (re.compile(r"收益|利息|回报|分红"), "说的收益是不是真的"),
    (re.compile(r"骗|靠谱|可靠|正规|靠得住|放心|真假|资质|资格"), "这家公司正不正规、有没有资格"),
    (re.compile(r"跑路|倒闭|关门|闭店|失联"), "会不会突然关门跑路"),
    (re.compile(r"社保|劳动合同|签合同"), "签约和交社保的是不是同一家"),
    (re.compile(r"押金|培训费|先交|交钱|收费"), "会不会让我先交钱"),
    (re.compile(r"欠|债|担保|财务|窟窿|亏损|官司|诉讼"), "有没有看不见的债务和官司"),
]
WHO = [
    (re.compile(r"我妈|妈妈|母亲|老妈"), "妈妈"),
    (re.compile(r"我爸|爸爸|父亲|老爸"), "爸爸"),
    (re.compile(r"爸妈|父母|家里老人|老人家"), "父母"),
    (re.compile(r"奶奶|外婆|姥姥"), "奶奶"),
    (re.compile(r"爷爷|外公|姥爷"), "爷爷"),
    (re.compile(r"朋友|同学|室友"), "朋友"),
    (re.compile(r"家人|亲戚"), "家人"),
]
CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
AMOUNT = re.compile(r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千]+)\s*(亿|万|千|元|块)")


def _cn_number(s: str) -> float | None:
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    total, digit = 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            digit = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            total += (digit or 1) * CN_UNITS[ch]
            digit = 0
        else:
            return None
    return float(total + digit) or None


def parse_amount(text: str) -> float | None:
    text = re.sub(r"(?<=\d)[,，](?=\d{3}(?:\D|$))", "", text)
    candidates = []
    for m in AMOUNT.finditer(text):
        clause = re.split(r"[，,。；;]", text[:m.start()])[-1]
        if re.search(r"月薪|年薪|工资|底薪|薪资", clause):
            continue
        n = _cn_number(m.group(1))
        if n is None:
            continue
        candidates.append(n * {"亿": 1e8, "万": 1e4, "千": 1e3}.get(m.group(2), 1.0))
    return candidates[0] if len(set(candidates)) == 1 else None


def parse_for_whom(text: str) -> str | None:
    for pattern, who in WHO:
        if pattern.search(text):
            return who
    return "自己" if re.search(r"我|自己", text) else None


def guess_scenario(need: str) -> tuple[str, list[str]]:
    """按命中关键词打分，长关键词权重大；都不中就是 general。"""
    low = need.lower()
    best, best_score, best_hits = DEFAULT_ID, 0, []
    for sid, s in load_scenarios().items():
        hits = [k for k in s.keywords if k.lower() in low]
        score = sum(len(k) for k in hits)
        if score > best_score:
            best, best_score, best_hits = sid, score, hits
    return best, best_hits


def keyword_intake(need: str, scenario: str | None = None) -> Intake:
    sid, hits = guess_scenario(need)
    method = "keywords"
    if scenario and scenario in load_scenarios():
        sid, method = scenario, "user"
    focus = [label for pattern, label in FOCUS_RULES if pattern.search(need)]
    return Intake(scenario=sid, scenario_label=get_scenario(sid).label, focus=focus[:3],
                  for_whom=parse_for_whom(need), amount=parse_amount(need), method=method, matched=hits)
