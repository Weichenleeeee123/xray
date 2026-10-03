"""Conversation policy separate from company evidence and deterministic risk rules.

Guides are questions/actions, not a financial-law knowledge base. Substantive
definitions still come from the versioned glossary; no policy figures invented.
"""
import re
from decimal import Decimal, InvalidOperation

WORRY = re.compile(r"害怕|担心|焦虑|不安|紧张|纠结|心里没底|不放心|慌|压力|难受|委屈|迷茫|失落|(?<!不)怕")
DECISION = re.compile(r"怎么办|怎么做|建议|下一步|该不该|要不要|我想存|准备存|想投|准备付|想签|想入职")
GUIDES = {
    "investment.type": "可以一起看。你说的“投资这家公司”，是买它的股票、购买它销售的产品，还是直接出资合作？先确认这一点，我再帮你梳理该看哪些资料。",
    "savings.product": "你说的“存”，是办理银行存款，还是工作人员介绍的理财或其他产品？可以先告诉我产品名称。",
    "savings.terms": "可以先核对产品名称、办理机构、资金去向，以及合同中的取用条件；把不清楚的条款列出来再问对方。",
    "savings.withdraw": "可以先问对方：“如果我急用这笔钱，何时能取回、是否需要扣费？请指出合同里对应的条款。”拿到书面条款后，我们再一起核对。",
    "job.offer": "可以先告诉我你最在意的是工作内容、薪酬，还是入职要求；拿到书面 offer 后，我们再逐项对照。",
    "job.checklist": "入职前可以核对劳动合同主体、薪酬及试用期条款、岗位职责和是否需要先交费用；口头承诺可请对方书面确认。",
    "contract.parties": "可以先核对签约主体、收款对象、交付内容和退出条件；如果愿意，发来对应条款，我们逐项看。",
    "prepaid.refund": "可以先看费用由谁收取、服务由谁提供，以及退款和未使用余额如何处理；暂时不清楚的地方先问明白。",
    "general.next": "你现在最想弄清楚的是哪一件事？可以先给我具体业务或材料名称，我们从那一点开始。",
    "scope.boundary": "公司层面的资料不能替代对具体产品或合同的核对；目前没有核实的部分，会和已查到的事实分开说明。",
    "scope.no_guarantee": "这些资料不能保证安全，也不能据此承诺本金或收益。",
    "material.private": "你可以补充相关材料用于本案核对；上传材料不会自动公开为企业评价。",
}

# Emotion prose cannot act as a bypass for evidence validation or diagnosis.
SUPPORT_FACT = re.compile(
    r"公司|银行|机构|企业|产品|账户|收益|本金|保本|安全|可靠|靠谱|诈骗|骗子|风险|偿付|"
    r"盈利|欠薪|倒闭|破产|赔付|合法|违法|违规|持牌|许可证|核实|查到|记录|"
    r"信誉|资质|信用|兑付|亏损|亏钱|稳妥|稳健|不会有事|"
    r"(?:钱|款|资金).{0,16}(?:能|会|可以|不会).{0,12}(?:取|退|拿|亏|损|丢|保|回来)|"
    r"保证|绝对|一定|肯定|必然|必定|诊断|焦虑症|抑郁症|都会|所有人|\d|[一二三四五六七八九十百千万亿]+元"
)


def safe_support(text: str, user_text: str) -> bool:
    return (0 < len(text.strip()) <= 350 and not SUPPORT_FACT.search(text)
            and all(word in user_text for word in ("妈妈", "爸爸", "爷爷", "奶奶", "孩子") if word in text)
            and bool(re.search(r"理解|担心|不安|紧张|焦虑|害怕|顾虑|慢慢|不着急|不需要|一起|谢谢|你好|客气", text))
            and (bool(WORRY.search(user_text)) or bool(re.search(r"你好|谢谢|辛苦", user_text))))


def money_from_user(text: str) -> str | None:
    match = re.search(r"(?<![\w.])([0-9]+(?:\.[0-9]+)?)\s*(万|[wW]|元)(?![A-Za-z])", text)
    if not match:
        # Chinese characters are \w, so allow the common '存20w' without changing numeric/date rules.
        match = re.search(r"(?:存|投|付|交|拿出|准备|预算|金额)\s*([0-9]+(?:\.[0-9]+)?)\s*(万|[wW]|元)(?![A-Za-z])", text)
    if not match:
        return None
    try:
        value = Decimal(match[1])
        if value <= 0:
            return None
        formatted = format(value.normalize(), "f")
        return formatted + ("万元" if match[2] in {"万", "w", "W"} else "元")
    except InvalidOperation:
        return None


def guide_for(text: str, scenario: str) -> str:
    # Current explicit intent takes precedence over the report's earlier scenario.
    if re.search(r"取不出|取不回|急用|赎回|拿不回", text):
        return "savings.withdraw"
    if re.search(r"求职|入职|工作|offer|薪酬", text, re.I):
        return "job.checklist" if re.search(r"清单|检查|核对", text) else "job.offer"
    if re.search(r"租房|签约|合同|合作", text):
        return "contract.parties"
    if re.search(r"充值|预付|会员|办卡", text):
        return "prepaid.refund"
    if re.search(r"投资|想投|准备投", text) and not re.search(r"存|理财|产品", text):
        return "investment.type"
    if re.search(r"存|理财|投资", text):
        return "savings.terms" if re.search(r"清单|检查|核对", text) else "savings.product"
    return {"job": "job.offer", "contract": "contract.parties", "prepaid": "prepaid.refund",
            "savings": "savings.product"}.get(scenario, "general.next")


def response_focus(question: str, scenario: str, refs: list[str]) -> str:
    if not refs and (WORRY.search(question) or DECISION.search(question)) and not re.search(
        r"公司|这家|机构|报告|记录|处罚|牌照|保本|诈骗|骗子|风险|靠谱吗", question
    ):
        return ("本轮是顾虑/下一步澄清，不是重新朗读调查报告。优先输出 support（纯情绪，不能带数字或家庭身份）、"
                "可选 user_context（仅复述当前用户金额），以及一个 clarify/guidance。"
                f"本轮最相关的行动是 {guide_for(question, scenario)}。用户当前未问企业事实，不要堆砌 fact 段。")
    return ("围绕本轮明确问题回答企业事实或解释，优先 fact_id，使用报告原有的人话解释；"
            "不要复述用户整句问题。需要建议时选择与本轮问题相关的行动，不机械重复产品类型问题。")


def complete_reply(reply, question: str, scenario: str):
    """Do not call a surviving unrelated fact a complete response to distress.

    This layer can add only non-factual support and bounded next-step questions;
    it never alters report conclusions, cites or previously validated facts.
    """
    worried = bool(WORRY.search(question))
    needs_next = worried or bool(DECISION.search(question))
    if not needs_next:
        return reply
    lines = []
    if worried and not any(safe_support(line, question) for line in reply.text.splitlines()):
        amount = money_from_user(question)
        if amount and amount not in reply.text:
            lines.append(f"你提到准备拿出{amount}。")
        lines.append("这件事让你放心不下，是可以理解的。你不需要急着做决定，我们可以把疑问一件件弄清楚。")
    if reply.text and not (reply.not_found and reply.text.startswith("没查到：")):
        lines.append(reply.text)
    elif reply.not_found:
        lines.append("目前案卷还不足以核实你关心的具体事项，但我们可以先确认下一步需要什么信息。")
    guide = GUIDES[guide_for(question, scenario)]
    if guide not in reply.text and not any(value in reply.text for value in GUIDES.values()):
        lines.append(guide)
    return reply.model_copy(update={"text": "\n\n".join(lines)})
