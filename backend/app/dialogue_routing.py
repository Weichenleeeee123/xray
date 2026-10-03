"""Bounded conversational routing, separate from company evidence retrieval.

A conversational overview is not a complete investigation. These labels only
select a response scope; they never supply facts, verify an alias, or waive
source, number, ownership, selected-version or contradictory-evidence checks.
Unrecognized or concrete questions return None for the existing strict path.
"""
import re
from typing import Literal

DialogueIntent = Literal["overview", "impression", "clarification", "other_company"]

_POLITE = re.compile(r"^(?:(?:你好|小企|请问|麻烦|能不能|能否|可以|请|帮我|给我|我想问一下|我想问|问一下)[，,：:]?)+")
_TAIL = re.compile(r"[呀啊呢吗吧呗啦哇嘛么～~]+$")
_PRONOUNS = {"", "它", "这家", "这家公司", "这个公司", "这家企业", "这家机构", "这家银行", "该公司",
             "该企业", "该机构", "当前公司", "当前企业", "当前这家公司", "报告里的公司", "报告中的公司",
             "这份报告里的公司", "这份报告中的公司", "案卷里的公司", "它这家公司", "本公司", "这家公司的整体情况"}
_REPORTS = {"报告", "这份报告", "这个报告", "当前报告", "案卷", "这份案卷", "这个案卷", "当前案卷"}
_GENERIC_NAMES = {"中国", "中华", "杭州", "北京", "上海", "深圳", "广州", "银行", "公司", "集团", "科技",
                  "技术", "网络", "信息", "投资", "股份", "实业", "贸易", "有限", "控股", "文化", "发展"}
_ORG_SUFFIX = re.compile(r"(?:股份有限公司|有限责任公司|股份公司|有限公司|有限合伙|公司)$")
_REGION = re.compile(r"^[\u4e00-\u9fff]{2,8}?(?:省|市)")
_NAME_TAIL = re.compile(r"(?:计算机系统|网络技术|网络科技|信息技术|信息科技|技术|科技|实业|控股|集团)$")

# Concrete facts and transaction rights must retain complete relevant evidence.
# This check precedes overview matching, including when the broad wording is a
# prefix to a more important question. No safe-looking clause hides the rest.
_CONCRETE = re.compile(
    r"\d|[零一二三四五六七八九十百千万亿两]+(?:元|万|亿|条|笔|件|年|月|天|日|%|％)|"
    r"退款|退钱|退费|取回|取出|取用|取款|取不|退不|拿回|赎回|兑付|急用|"
    r"合同|条款|违约|赔付|赔偿|扣费|手续费|保证金|押金|培训费|期限|到期|"
    r"保本|保息|收益|回报率|利息|利率|年化|本金|亏损|盈利|净利润|营业收入|"
    r"资产|负债|注册资本|实缴|认缴|股东|董事|法人|成立|存续|注销|吊销|登记状态|"
    r"牌照|资质|资格|持牌|许可|合法|违法|违规|处罚|失信|执行|官司|裁判|"
    r"诉讼|投诉|纠纷|欠薪|欠税|欠款|破产|倒闭|骗局|诈骗|骗子|风险|"
    r"安全|靠谱|可靠|可信|信任|上市|裁员|正常营业|经营状况|专利|排名|竞争力|"
    r"员工|人数|薪资|营收|利润|市值|偿付|持有|现金流|几名|几条|"
    r"财报|财务|报表|年报|季报|半年报|审计|股权|股本|权益|分红|抵押|质押|出质|担保|"
    r"应收|应付|商誉|周转|毛利|净利|成本|费用|债务|资本|估值|杠杆|税务|纳税|税收|"
    r"营业执照|工商|登记|备案|注册地址|经营地址|法定代表|信用代码|经营异常|经营期限|"
    r"社保|参保|招聘|岗位|入职|试用|离职|仲裁|司法|诉前|开庭|公告|判决|监管|"
    r"持股|控股人|实际控制|实控人|关联交易|关联方|受益人|子公司|分公司|"
    r"网站|官网|品牌|旗下|新闻|舆情|报道|口碑|技术水平|市场份额|"
    r"收款|账户|转账|付款|打款|付钱|收费|多少钱|多少|几家|几人|几次|"
    r"股票|股价|基金|债券|理财|存款|融资|投资|出资|工资|薪酬|待遇|"
    r"技术实力|产品质量|营业范围|经营范围|主营|做什么|干什么|产品|业务|"
    r"完整|所有|全部|逐条|逐项|每一|证明|保证|肯定|绝对|忽略|无视|"
    r"system\s*prompt|ignore\s+(?:all|previous|the)", re.I
)
_CLAUSE = re.compile(r"[，,；;。.!！?？\n]|并且|同时|以及|而且|但是|然后|另外|顺便|还想问")
_SUBJECT = r"(?P<subject>[^，,；;。.!！?？\n]{0,70}?)"

_OVERVIEW = [
    re.compile(_SUBJECT + r"(?:的)?(?:整体情况|总体情况|整体表现|总体表现|公司概况|总体印象|整体印象|概况|概览|大概情况)(?:怎么样|如何)?$"),
    re.compile(r"(?:介绍|说说|聊聊|谈谈|评价|点评|分析|了解|概括|总结|讲讲|讲一讲|看一看|看看)(?:一下)?" + _SUBJECT + r"$"),
    re.compile(r"(?:我想|想)(?:了解|认识)(?:一下)?" + _SUBJECT + r"$"),
    re.compile(r"(?:给个|给我一个|说个)(?:整体|总体|大致|简单)?(?:看法|评价|印象)$"),
    re.compile(r"(?:简单|大致|简要)(?:介绍|概括|总结|说说|讲讲)(?:一下)?" + _SUBJECT + r"$"),
    re.compile(_SUBJECT + r"(?:整体|总体|大概)?(?:怎么样|如何|好不好|行不行|怎样)$"),
]
_IMPRESSION = [
    re.compile(_SUBJECT + r"(?:厉不厉害|强不强|有名吗|出名吗|有多厉害)$"),
    re.compile(r"(?:你觉得|你认为|你看)" + _SUBJECT + r"(?:整体|总体|大概)?(?:怎么样|如何|好不好|行不行|怎样)$"),
    re.compile(r"(?:你怎么看|你如何看待|怎么看待|如何看待|怎么看)" + _SUBJECT + r"$"),
    re.compile(_SUBJECT + r"(?:你怎么看|你怎么看待)$"),
    re.compile(r"(?:你觉得|你认为)?" + _SUBJECT + r"(?:是一家什么样的公司|是个什么样的公司)$"),
    re.compile(r"(?:听说|听人说|听朋友说)" + _SUBJECT + r"(?:怎么样|如何|好不好)$"),
    re.compile(r"(?:听说|听人说|有人说|大家说|听朋友说)?" + _SUBJECT
               + r"(?:是不是|是否|真的|真|感觉|看起来|好像)?(?:特别|非常|很|挺|蛮|这么|那么)?(?:厉害|牛|牛逼|优秀|强|出名|有名)(?:是吗|对吗|真的)?$"),
    re.compile(r"(?:你对|对)" + _SUBJECT + r"(?:的|有什么|有何|什么)?(?:印象|看法)(?:怎么样|如何|是什么)?$"),
]
_CLARIFICATION = [
    re.compile(r"(?:你觉得|你认为)?" + _SUBJECT + r"(?:适合我吗)$"),
    re.compile(r"(?:我该|该|可以|能)(?:从哪|从哪里|怎么看|怎么了解|怎么判断|看什么)(?:开始)?$"),
]
_FOLLOWUP = re.compile(r"(?:那|那么|嗯|好|好的)?(?:继续|接着说|展开讲讲|展开说说|多说一点|详细说说|再介绍一下|再说说|再讲讲|展开一下)$")


def _clean(text: str) -> str:
    # Preserve punctuation inside the message so mixed clauses stay detectable.
    text = re.sub(r"[ \t\r\u3000]+", "", str(text or "")).strip()
    text = text.strip("？?。！!～~")
    text = _POLITE.sub("", text)
    return text


def _name(text: str) -> str:
    return re.sub(r"[\s（）()“”\"'‘’]", "", text).casefold()


def _subject_scope(subject: str, company_name: str) -> DialogueIntent | None:
    """None means current subject, not a verified legal identity/brand match.

    A shortened part of the current name can name this conversation's subject;
    it never establishes brand ownership or lets another full legal name borrow
    this case's records. Ambiguous generic nouns ask for clarification.
    """
    subject = subject.strip("“”\"'‘’")
    subject = re.sub(r"(?:的)?(?:整体情况|总体情况|整体表现|总体表现|整体印象|总体印象|公司概况|概况)$", "", subject)
    if subject in _PRONOUNS or subject in _REPORTS:
        return None
    subject = re.sub(r"(?:这家公司|这家企业|这家机构|这家银行)$", "", subject)
    target, company = _name(subject), _name(company_name)
    if not company or not target or target in _GENERIC_NAMES:
        return "clarification"
    if target == company:
        return None
    # Different complete company names (including subsidiaries and branches)
    # are different scopes even if they share a brand prefix.
    if re.search(r"公司|分行|支行|分公司|合伙|集团$", target):
        return "other_company"
    candidates = {company, _ORG_SUFFIX.sub("", company)}
    for candidate in list(candidates):
        candidates.add(_REGION.sub("", candidate))
    for candidate in list(candidates):
        candidates.add(_NAME_TAIL.sub("", candidate))
    if target in candidates:
        return None
    # Conversational shorthand drawn from the active legal name itself, including
    # a brand after a location prefix without 市 (e.g. 北京...科技有限公司).
    # This is a subject hint, never proof of a brand's legal identity.
    if len(target) >= 2 and any(target in candidate for candidate in candidates):
        return None
    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z&·\-]{2,50}", target):
        return "other_company"
    return "clarification"


def _previous_user(history) -> str | None:
    for message in reversed(list(history or ())[-8:]):
        if isinstance(message, str):
            return message
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        if role == "user":
            return message.get("text", "") if isinstance(message, dict) else getattr(message, "text", "")
    return None


def requires_evidence(question: str, company_name: str = "") -> bool:
    """Share the concrete-question boundary with the retrieval fallback.

    A missing retrieval-topic synonym must not turn a known financial or
    transaction question into a claim that the user's purpose is unclear.
    """
    query = _clean(question)
    # A scoped legal name can itself contain terms such as 投资/资产.
    intent_text = query.replace(_clean(company_name), "") if company_name else query
    return bool(_CONCRETE.search(intent_text))


def classify_dialogue(question: str, refs: list[str], company_name: str, history=()) -> DialogueIntent | None:
    """Route only complete broad conversational questions, never factual parts.

    History is a bounded user-intent hint, not evidence. The caller supplies
    same-case, selected-version history; assistant statements are ignored.
    """
    if refs or not isinstance(question, str) or len(question) > 200:
        return None
    query = _clean(question)
    if not query or _CLAUSE.search(query):
        return None
    concrete = requires_evidence(question, company_name)
    if _FOLLOWUP.fullmatch(_TAIL.sub("", query)):
        previous = _previous_user(history)
        if previous:
            intent = classify_dialogue(previous, [], company_name)
            if intent in {"overview", "impression", "clarification"}:
                return "overview"
            if intent == "other_company":
                return "other_company"
        return None
    for intent, patterns in (("clarification", _CLARIFICATION), ("impression", _IMPRESSION), ("overview", _OVERVIEW)):
        for pattern in patterns:
            # Match first with the original particle (e.g. 靠谱吗), then without
            # a trailing conversational particle. Do not strip inside names.
            match = pattern.fullmatch(query) or pattern.fullmatch(_TAIL.sub("", query))
            if match:
                subject = match.groupdict().get("subject") or ""
                scope = _subject_scope(subject, company_name)
                exact_name_piece = bool(subject and _name(subject) in _name(company_name))
                # A possessive object is a specific aspect/document, not another
                # company. Keep even an unlisted topic ("这家公司的某个字段") on
                # the evidence path rather than calling it an entity name.
                broad_aspect = re.fullmatch(r".+的(?:整体情况|总体情况|整体表现|总体表现|整体印象|总体印象|公司概况|概况)", subject)
                if "的" in subject and not exact_name_piece and not broad_aspect and subject not in _PRONOUNS:
                    return None
                if not exact_name_piece and any(word in subject for word in ("和", "与", "比", "或者", "还是", "除了", "包括")):
                    return None
                if re.search(r"是否|是不是|有没有|有无|能否|正常|可以|怎么|怎样|什么|哪里|哪家|哪个|为何|为什么|谁|如何|了吗|的吗|还在|不会|不能|能不能|不", subject):
                    return None
                if concrete:
                    # A different complete legal entity must never borrow this
                    # case even when its name contains words such as 投资.
                    legal_name = bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z（）()·&\-]{2,65}(?:有限公司|有限责任公司|分公司|分行|支行)", subject))
                    if scope == "other_company" and legal_name and not _CONCRETE.search(query.replace(subject, "")):
                        return "other_company"
                    return None
                return scope or intent
    # Bare references to the report ask which aspect to read, not an audit.
    if not concrete and (query in _PRONOUNS - {""} or query in _REPORTS):
        return "clarification"
    return None
