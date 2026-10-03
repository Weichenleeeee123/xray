"""可追踪的判断：把一次分析整理成一条条能被准确更新的判断，并算出判断级的变化。

为什么要单独一层
    报告只是"某一次发布时，这些判断长什么样"。会被保存、被更新、被追踪的是判断本身。
    "这家公司整体比较可靠"追不了、也纠正不了；
    "合同草案约定服务未使用可申请退款，但还没核对待签的最终版本"可以。

三层必须分开
    said      材料里写了什么   —— 只代表文字读对了。OCR 正确不等于材料真实、不等于账户归属已认证。
    confirmed 现实中确认了什么 —— 登记、名单、年报这类可核来源。
    inferred  系统据此推断了什么 —— 规则推的，一定带 premise（前提）和 unknown（未知项），
                                    并用 cannot 写明"不能因此推出什么"，不许跳到定性、定罪、下结论。

新材料进来做两件事
    一、对已有判断的影响检查；
    二、对当前场景关键事项的补充检查（原来没有这条判断，也要提示）。
矛盾时两边证据并列保留（Judgment.dispute），不让最后上传的那份材料"获胜"。
"""
from __future__ import annotations

import re

from app.models import (Assertion, Basis, ClaimKind, CompanyProfile, Judgment, JudgmentChange, MissingItem,
                        Question, RawRecord, Scenario, Signal, Status, Verdict)

LAYER_LABEL = {"said": "材料里写的", "confirmed": "记录里查到的", "inferred": "系统推断的"}

STATE_LABEL = {"holds": "成立", "needs_check": "需要核实", "unconfirmed": "尚不能确认",
               "revised": "已修订", "clarified": "已澄清", "withdrawn": "已撤回"}

# 记录类判断说的是"查到的是什么"，不是"该怎么办"。状态词另用一套，免得每条都像在报警。
RECORD_LABEL = {"holds": "记录如此", "needs_check": "记录里有情况", "unconfirmed": "没查到",
                "revised": "已修订", "clarified": "已澄清", "withdrawn": "已撤回"}

STATE_OF_VERDICT = {Verdict.consistent: "holds", Verdict.attention: "needs_check", Verdict.misleading: "needs_check",
                    Verdict.mismatch: "needs_check", Verdict.redline: "needs_check",
                    Verdict.unverifiable: "unconfirmed"}

STATE_OF_STATUS = {Status.ok: "holds", Status.bad: "needs_check", Status.warn: "needs_check",
                   Status.miss: "unconfirmed", Status.none: "unconfirmed"}

# 每种说法被核验后，明确写出"不能因此推出什么"。定性、定罪、推测后果都不在这里给。
CANNOT: dict[ClaimKind, list[str]] = {
    ClaimKind.payee: ["收款账户真实属于材料上写的这个人", "这家公司在违法收款", "这是诈骗"],
    ClaimKind.return_promise: ["这家公司一定会按承诺兑付", "它已经在做非法集资"],
    ClaimKind.qualification: ["没在名单里就等于诈骗", "它一定没有金融业务资格"],
    ClaimKind.background: ["国资持股等于国家或银行给它担保"],
    ClaimKind.capital: ["注册资本等于这家公司的实际实力"],
    ClaimKind.scale: ["规模大就等于可靠"],
    ClaimKind.partner: ["写了资金存管就等于钱是安全的"],
    ClaimKind.refund: ["材料上的口头承诺可以当合同条款用"],
    ClaimKind.upfront_fee: ["收钱招人的公司一定有诈骗意图"],
}

# 需要核实这条判断的时候，还缺什么要说清楚：缺的是一个证据、一个人，还是一个说法。
UNKNOWN_OF_KIND: dict[ClaimKind, list[str]] = {
    ClaimKind.payee: ["材料上那个收款名是不是真的", "这个收款人和公司是什么关系", "钱最后到了谁手上"],
    ClaimKind.return_promise: ["承诺有没有写进合同、有没有盖章"],
    ClaimKind.qualification: ["它实际在做什么业务"],
    ClaimKind.refund: ["最终要签的那一版是怎么写的"],
    ClaimKind.upfront_fee: ["收的这笔钱名义上是什么"],
}

# 成立时才适用：这条判断挂在什么前提上
PREMISE: dict[ClaimKind, list[str]] = {
    ClaimKind.payee: ["这份付款信息确实对应这笔交易", "材料上的户名没有被改动过"],
    ClaimKind.return_promise: ["监管口径按资管新规执行"],
    ClaimKind.qualification: ["名单本身是最新的（名单有截止日期）"],
    ClaimKind.background: ["股东结构自上而下能穿透到最终出资人"],
    ClaimKind.capital: ["年报数据由企业自行填报，未经审计"],
    ClaimKind.scale: ["年报里的参保人数由企业自行填报，可以选不公示"],
    ClaimKind.partner: ["存管关系以存管协议为准，不是名单里有这家银行就算"],
    ClaimKind.refund: ["以最终签署的合同条款为准"],
    ClaimKind.upfront_fee: ["这笔费用确实发生在入职之前"],
}

MATERIAL_UNKNOWN = ["这份材料本身是否真实", "截图或照片有没有被改动过"]

STATUS_WORDS = re.compile(r"注销|吊销|停业|撤销|解散|清算")
QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _short(s: str, n: int = 60) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "……"


def _grade(source: str) -> str:
    if source == "material":
        return "material"
    if source.startswith("reg_"):
        return "regulation"
    if source.startswith("param"):
        return "parameter"
    if source.startswith("web_"):
        return "web"
    if source in ("commercial",):
        return "commercial"
    if source == "demo":
        return "demo"
    return "official"


def _locate(text: str, quote: str) -> str | None:
    """在材料原文里找到这句话的位置，让依据能点回到具体那一行。"""
    flat = _flat(quote)
    if not flat:
        return None
    for i, line in enumerate(text.splitlines(), 1):
        if flat in _flat(line):
            return f"第 {i} 行：{_short(line.strip(), 36)}"
    return None


def _stable(text: str) -> str:
    """判断的 id 要跟着内容走：同一句话永远同一个 id，换了一句新问题就是新的一条。
    不能拿 Q1/Q2 这种位置编号当 id，问题一增减，旧判断就全被认成"变了"。"""
    import hashlib
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:10]


# 场景里"要看的关键事项"用的是内部编号，说成人话。没有对应说法的就照原样标出来，别编。
KEY_NAME = {
    "A1": "有没有资格收这笔钱（牌照、许可证、登记编码）",
    "A4": "公司全称和统一社会信用代码",
    "A5": "经营范围和实际在做什么",
    "A7": "收款户名和合同主体是不是同一个",
    "A9": "入职前要不要先交钱",
    "credit.status": "工商登记状态",
    "credit.penalties": "行政处罚记录",
    "risk.bank_list": "有没有在持牌机构名单里",
    "risk.amac": "私募基金管理人登记",
    "risk.amac_tips": "中基协公示的提示信息",
    "risk.pf_threshold": "门槛和合格投资者要求",
    "risk.scope": "经营范围里有没有这一项",
    "risk.product_code": "理财产品登记编码",
    "risk.payee": "钱打给谁、户名对不对",
    "risk.upfront_fee": "入职前要不要先交钱",
    "finance.insured": "存款有没有保险",
    "finance.paid_capital": "注册资本实缴了多少",
}


def _item_title(key: str, assertions: list[Assertion], signals: list[Signal],
                scenario: Scenario | None = None) -> str | None:
    """内部编号换成报告里给人看的那句话，别把 A1 这种代号漏给用户。

    认不出来就返回 None，让调用方换一句不含代号的话说，绝不把 risk.amac_tips 这种内部编号漏出去。
    队友新加的检查项（2026-10-02 的 amac_tips）就是漏了代号才被测试抓到——所以名字优先从数据里取。
    """
    for a in assertions:
        if a.id == key:
            return _short(a.text, 40)
    for sig in signals:
        for it in sig.items:
            if key in (f"{sig.key}.{it.key}", it.key):
                return f"{sig.title} · {it.label}"
    if key in KEY_NAME:
        return KEY_NAME[key]
    # 数据里没这个名字（这一版没查到），退一步用这个信号自己的那句话
    family = key.split(".")[0]
    if scenario and (lede := (scenario.signal_ledes or {}).get(family)):
        return lede.rstrip("。：:")
    return None


def _material_basis(quote: str, texts: list[RawRecord]) -> Basis:
    """一句话出自哪份材料、哪一行。找不到就当材料原文记下来，不假装有位置。"""
    for t in texts:
        if isinstance(t.content, str) and _flat(quote) and _flat(quote) in _flat(t.content):
            return Basis(ref=t.id, label=t.title, quote=quote, locator=_locate(t.content, quote),
                         grade="material")
    return Basis(label="材料原文", quote=quote, grade="material")


# ---------- 合同/协议这类材料的专属检查 ----------
# 拍一份合同进来，不是"又多了一段文字"。合同要按合同去读：在跟谁签、有没有"先交钱"的条款、
# 该写的（签订日期、签字盖章）写没写。这几件事原有的规则一条都不管——只看已有判断，
# 就会漏掉"这份材料根本没有任何判断碰过它"。

CONTRACT_WORDS = ("合同", "协议", "条款", "甲方")
PARTY_RE = re.compile(r"(?:甲方|乙方|丙方|用人单位|委托方|受托方|出租方|承租方|收购方|发包方|承包方|服务方|供应商)\s*[：:]\s*([^\n，,。；;、]{2,80})")
MONEY_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*万?元")
PREPAY_WORDS = ("保证金", "押金", "定金", "培训费", "服装费", "工装费", "材料费", "预付款", "诚意金", "服务费", "手续费")
PREPAY_VERBS = ("支付", "缴纳", "交纳", "交付", "交", "付", "汇")
DATE_RE = re.compile(r"(?:签订日期|签署日期|签约日期|日期)\s*[:：]?\s*\d{4}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
SIGN_WORDS = ("签字", "盖章", "签章", "捺印", "签署")


def is_contract(r: RawRecord) -> bool:
    """像不像一份合同/协议。既要能看到契约类字眼，也要有当事人或条款的样子——
    免得一句带"合同"两个字的普通材料也被按合同去读。"""
    t = r.content if isinstance(r.content, str) else ""
    if len(t) < 20 or not any(w in t for w in CONTRACT_WORDS):
        return False
    named = any(w in (r.title or "") for w in ("合同", "协议", "合约"))
    clauses = len(re.findall(r"第\s*[0-9一二三四五六七八九十百]{1,4}\s*条", t)) >= 2
    return bool(PARTY_RE.search(t)) or named or clauses


def _party_entity(value: str) -> str:
    # Drafting aliases are not part of a legal name. Keep other parenthetical
    # text (for example a city in the registered name) for exact comparison.
    value = re.sub(r"[（(]\s*(?:以下简称|下称|简称)\s*[^）)]*[）)]", "", value)
    return re.sub(r"[\s（）()]", "", value)


def contract_judgments(company_name: str, version_no: int, texts: list[RawRecord],
                       assertions: list[Assertion]) -> list[Judgment]:
    out: list[Judgment] = []
    # 已经被规则拎出来过的原句（如"先交钱"），这里不再重复开一张卡——
    # 加一条判断是为了"没人看这件事"，不是为了让同一句话在清单里出现两遍。
    claimed = _flat(" ".join(q for a in assertions for q in (a.quotes or [])))
    for r in texts:
        if not is_contract(r):
            continue
        t, one = r.content, [r]
        scope = f"{company_name}｜{r.title}"

        # 1. 在跟谁签。合同上的甲方和查的这家公司不是同一个名字，是首先要说清的事。
        parties = list(dict.fromkeys(n.strip() for n in PARTY_RE.findall(t) if n.strip()))[:6]
        entity = _party_entity
        company_present = any(entity(n) == entity(company_name) for n in parties)
        if not parties:
            out.append(Judgment(
                id=f"contract.party.{_stable(r.id + '没写')}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
                text=f"所提供材料（{r.title}）里没写甲方、乙方的具体名称",
                scope=scope, basis=[Basis(ref=r.id, label=r.title, grade="material")],
                unknown=["签这份东西的到底是哪家公司", "它和查的这家公司是什么关系"],
                cannot=["这份合同是假的", "对方是骗子"],
                state="unconfirmed", state_label=STATE_LABEL["unconfirmed"], since=version_no,
                plain="合同上没写当事人，就没法核对你在跟谁签。"))
        for n in parties:
            same = entity(n) == entity(company_name)
            other_party = company_present and not same
            line = next((l for l in t.splitlines() if _flat(n) in _flat(l)), n)
            out.append(Judgment(
                id=f"contract.party.{_stable(r.id + n)}", layer="said", layer_label=LAYER_LABEL["said"],
                text=f"合同上写的当事人是「{n}」",
                scope=scope, basis=[_material_basis(line, one)],
                premise=["这份是对方给你的、准备照它办的那一份"],
                unknown=list(MATERIAL_UNKNOWN) + ["这份合同是谁起草的", "对方有没有资格签这份"],
                cannot=["这份合同有法律效力", "签了就必须照办"],
                state="holds" if same else "unconfirmed" if other_party else "needs_check",
                state_label=STATE_LABEL["holds" if same else "unconfirmed" if other_party else "needs_check"], since=version_no,
                plain=(f"和查的「{company_name}」是同一个名字。" if same else
                       "这是材料中列出的另一方；被查询企业已在另一方出现，这一方的身份和签约资格仍需核实。" if other_party else
                       f"合同上写的是「{n}」，查的这家叫「{company_name}」，不是同一个名字。"
                       "要么签的是另一家公司，要么这份合同的甲方写错了——先弄清在跟谁签，再谈钱。")))

        # 2. 合同里有没有"先交钱"的条款。方向反了，是这份材料里最该被拎出来的一条。
        seen: set[str] = set()
        for line in t.splitlines():
            if not any(w in line for w in PREPAY_WORDS) or not any(v in line for v in PREPAY_VERBS):
                continue
            if re.search(r"无需(?:支付|缴纳|交纳|交付)?|不(?:用|必|需)(?:支付|缴纳|交纳|交付)?|不收取|不得收取|禁止收取|免收", line):
                continue
            key = _stable(line)
            if key in seen or (_flat(line) and _flat(line)[:24] in claimed):
                continue     # 规则已经拎过这一句了，不重复开卡
            seen.add(key)
            out.append(Judgment(
                id=f"contract.prepay.{_stable(r.id + key)}", layer="said", layer_label=LAYER_LABEL["said"],
                text=f"合同里有一条要你先付钱：{_short(line.strip(), 46)}",
                scope=scope, basis=[_material_basis(line, one)],
                premise=["对方确实照这份合同办"],
                unknown=["这笔钱最后进了谁的账户", "有没有别人真的交过这笔钱", "收这个名目有没有凭据"],
                cannot=["这是诈骗", "这笔钱一定追不回来", "合同上写了就一定合法"],
                state="needs_check", state_label=STATE_LABEL["needs_check"], since=version_no,
                plain="合同里白纸黑字写着要先付钱。这只说明材料上这么写，不代表这笔钱该交，也不代表对方是骗子；"
                       "先确认付款条件、收款主体、交付安排和能否退还。"))

        # 退款/退出与违约责任，即使没有“随时可退”的宣传承诺，也要读合同本身。
        for category, label, pattern, explanation in (
            ("refund", "退款与退出", r"退款|退还|退费|不予退|不可退|不得退|退出|赎回|封闭期|锁定期|解除合同",
             "核对允许退出的条件、申请流程、到账期限与扣费，尤其要和宣传及对方回复对照。"),
            ("breach", "违约责任", r"违约|赔偿|滞纳金|单方(?:变更|修改)|自动续(?:费|约)",
             "确认责任由谁承担、触发条件和金额如何计算；这里仅整理条款，不判断其法律效力。"),
            ("payment", "付款安排", r"付款|支付|收款|账户|户名|分期|尾款|交付|履行期限",
             "确认付款时点、收款户名与交付条件。材料中的账户文字不等于账户归属已经核实。"),
        ):
            lines = [line.strip() for line in t.splitlines() if re.search(pattern, line)]
            if not lines:
                out.append(Judgment(
                    id=f"contract.{category}.{_stable(r.id + '未见')}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
                    text=f"所提供文本未见明确的{label}约定", scope=scope,
                    basis=[Basis(ref=r.id, label=r.title, grade="material")],
                    unknown=[f"完整合同或附件中是否写明{label}"], cannot=["合同没有这些约定", "这份合同无效"],
                    state="unconfirmed", state_label=STATE_LABEL["unconfirmed"], since=version_no,
                    plain="当前可能只是节选或部分页面；需要补充完整文本后核对。"))
                continue
            quote = "\n".join(lines)
            out.append(Judgment(
                id=f"contract.{category}.{_stable(r.id + quote)}", layer="said", layer_label=LAYER_LABEL["said"],
                text=f"{label}：{_short(quote, 100)}", scope=scope,
                basis=[_material_basis(line, one) for line in lines],
                unknown=["所提供文本是否完整，是否为最终约定"],
                cannot=["这份合同无效", "条款一定可以执行"], state="needs_check",
                state_label=STATE_LABEL["needs_check"], since=version_no, plain=explanation))

        sign_lines = [line for line in t.splitlines() if any(w in line for w in SIGN_WORDS)]
        if sign_lines:
            out.append(Judgment(
                id=f"contract.signature.{_stable(r.id)}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
                text="文本中的签字或盖章栏目不能确认实际签署状态", scope=scope,
                basis=[_material_basis(sign_lines[0], one)],
                unknown=["原件是否有双方实际签名或印章", "是否为最终签署版本"],
                cannot=["双方已经签署", "这份合同已生效"], state="unconfirmed",
                state_label=STATE_LABEL["unconfirmed"], since=version_no,
                plain="出现签字、盖章字样可能只是空白栏目或生效条款，需要核对原件；不能仅凭识别文字确认已签署。"))

        # 3. 该写的没写。这是材料本身的问题，不是公司的定性。
        lacks = [w for w, ok in (("签订日期", bool(DATE_RE.search(t))),
                                 ("双方的签字或盖章", any(w in t for w in SIGN_WORDS))) if not ok]
        if lacks:
            out.append(Judgment(
                id=f"contract.blank.{_stable(r.id + '｜'.join(lacks))}", layer="inferred",
                layer_label=LAYER_LABEL["inferred"],
                text=f"所提供文本未见{'，也未见'.join(lacks)}",
                scope=scope,
                basis=[Basis(ref=r.id, label=r.title, grade="material"), Basis(label="规定", grade="regulation")],
                unknown=[f"完整的那一份上有没有{'，'.join(lacks)}", "拍的这一页是不是全部"],
                cannot=["这份合同无效", "这家公司故意隐瞒"],
                state="needs_check", state_label=STATE_LABEL["needs_check"], since=version_no,
                plain="缺的是这份材料上的东西，不等于缺的就是事实——先要到完整的一份再说。"))
    return out


# ---------- 生成一版里的判断 ----------

def build(company_name: str, scenario: Scenario, version_no: int, assertions: list[Assertion],
          missing: list[MissingItem], signals: list[Signal], questions: list[Question],
          texts: list[RawRecord], company: CompanyProfile | None = None) -> list[Judgment]:
    out: list[Judgment] = []
    plain_set = {a.plain for a in assertions}

    # 1. 材料里写了什么。只说"材料上这么写"，不说"事情就是这样"。
    mbasis: dict[str, list[Basis]] = {}
    for a in assertions:
        scope = f"{company_name}｜{texts[-1].title if texts else '用户提供的材料'}"
        mbasis[a.id] = [_material_basis(q, texts) for q in a.quotes]
        out.append(Judgment(
            id=f"said.{a.id}", layer="said", layer_label=LAYER_LABEL["said"],
            text=f"材料里写了「{a.kind_label}」：{_short(a.text, 70)}",
            scope=scope,
            basis=mbasis[a.id],
            unknown=list(MATERIAL_UNKNOWN),
            state="holds", state_label="照录",
            plain="只代表材料上这么写、文字读对了。不代表材料真实，也不代表事情就是这样。",
            since=version_no, target=a.id))

    # 2. 系统据此推断了什么。核验结论一律带前提、未知项和"不能推出"。
    for a in assertions:
        out.append(Judgment(
            id=f"check.{a.id}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
            text=a.plain,
            scope=f"{company_name}｜{a.kind_label}",
            basis=mbasis[a.id] + [Basis(ref=c.ref, label=c.label, grade=_grade(c.source)) for c in a.checks],
            premise=PREMISE.get(a.kind, []),
            unknown=([c.result for c in a.checks if c.status in (Status.miss, Status.none)]
                     + (UNKNOWN_OF_KIND.get(a.kind, []) if STATE_OF_VERDICT[a.verdict] != "holds" else [])),
            cannot=CANNOT.get(a.kind, []),
            state=STATE_OF_VERDICT[a.verdict], state_label=STATE_LABEL[STATE_OF_VERDICT[a.verdict]],
            since=version_no,
            plain=f"判定「{a.verdict_label}」，依据是上面那几条检查。",
            target=a.id))

    # 3. 现实中确认了什么。要看的条目全留，其余只留有问题和没查到的。
    #    说法条目已经在上面单独成判断了，这里不重复一遍。
    for sig in signals:
        for it in sig.items:
            key = f"{sig.key}.{it.key}"
            if it.value in plain_set or it.detail in plain_set:
                continue
            if it.source == "user_reviews":   # 评价是别人说的、没核实，不是"现实中确认了的事"
                continue
            keep = it.status in (Status.bad, Status.warn) or key in scenario.first_items
            if not keep:
                continue
            state = STATE_OF_STATUS[it.status]
            unknown = [it.detail] if it.status in (Status.miss, Status.none) and it.detail else []
            out.append(Judgment(
                id=f"record.{key}", layer="confirmed", layer_label=LAYER_LABEL["confirmed"],
                text=f"{sig.title} · {it.label}：{it.value}",
                scope=f"{company_name}｜{sig.title}",
                basis=[Basis(ref=it.ref, label=it.source, grade=_grade(it.source))],
                unknown=unknown,
                state=state, state_label=RECORD_LABEL[state],
                since=version_no,
                plain=it.detail or "",
                target=key))

    # 4. 该写的没写。这是材料的问题，不是公司的问题。
    for m in missing:
        out.append(Judgment(
            id=f"gap.{m.id}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
            text=f"该写的没写：{m.text}",
            scope=f"{company_name}｜材料完整性",
            basis=[Basis(ref=m.refs[0] if m.refs else None, label="材料", grade="material"),
                   Basis(label="规定", grade="regulation")],
            unknown=[f"材料上别的地方有没有写「{m.text}」"],
            cannot=["这家公司故意隐瞒", "它不合规"],
            state="needs_check", state_label=STATE_LABEL["needs_check"],
            since=version_no, plain=m.plain, target=m.id))

    # 5. 下一步问题。问题本身也是被追踪的对象，不是一次性文本。
    #    编号（Q1/Q2）在报告里会随问题增减整体挪位，所以判断 id 用问题原文算，编号只当跳转目标。
    for q in questions:
        out.append(Judgment(
            id=f"ask.{_stable(q.ask)}", layer="inferred", layer_label=LAYER_LABEL["inferred"],
            text=q.ask, scope=f"{company_name}｜待问对方",
            state="needs_check", state_label=STATE_LABEL["needs_check"],
            since=version_no,
            plain=f"为什么要问：{q.why} 拿到答案后去{qq_check(q)}核对。",
            target=q.id))

    # 6. 补充检查：这一版里，场景要看的关键事项中，还没有任何一条判断的，也要提出来。
    #    （只查已有判断会漏掉"原来根本没分析过"的事）
    covered = {j.target for j in out if j.target}
    named: set[str] = set()   # A9 和 risk.upfront_fee 是同一件事的两面，名一样就只说一遍
    for key in scenario.first_items:
        if key in covered:
            continue
        title = _item_title(key, assertions, signals, scenario)
        if title in named:
            continue
        named.add(title)
        # 认不出名字的就别硬安一个，换一句不含内部代号的话说
        said = f"「{title}」这一项还没有任何记录或判断" if title else "有一项该核的事还没有任何记录或判断"
        out.append(Judgment(
            id=f"key.{key}", layer="confirmed", layer_label=LAYER_LABEL["confirmed"],
            text=said,
            scope=f"{company_name}｜{scenario.label}",
            unknown=["这一版里没有这项记录：可能是数据源没覆盖，也可能是没查"],
            cannot=["没查到就等于没问题"],
            state="unconfirmed", state_label=STATE_LABEL["unconfirmed"],
            since=version_no,
            plain=f"这是「{scenario.label}」第一眼要看的事项，目前没有它的记录。没查不等于没问题。",
            target=key))

    # 7. 合同/协议类材料：合同要按合同去读，不能只当"又多了一段文字"。
    #    材料换了一版、判断却一条没动，用户看到的就是"它根本没看这份合同"。
    out.extend(contract_judgments(company_name, version_no, texts, assertions))

    return out


def qq_check(q: Question) -> str:
    return (q.check_where or "权威渠道").rstrip("。") + ""


# ---------- 冲突：两边都留着 ----------

def disputes(company_name: str, assertions: list[Assertion], texts: list[RawRecord],
             company: CompanyProfile | None = None) -> dict[str, list[str]]:
    """新材料和已知记录对不上时，两边证据并列保留，不让后交的那份材料赢。

    时间新不等于更真实；公司补充的说明也不一定能推翻别的来源。
    """
    out: dict[str, list[str]] = {}
    material = "\n".join(t.content for t in texts if isinstance(t.content, str))
    if not material.strip():
        return out

    for a in assertions:
        if a.kind is not ClaimKind.payee:
            continue
        bad = [c for c in a.checks if c.status is Status.bad]
        if not bad:
            continue
        m = QUOTED.search(bad[0].result)
        who = m.group(1) if m else "另一个人"
        out[f"check.{a.id}"] = [
            f"登记记录里是「{company_name}」",
            f"材料上要求把钱打给「{who}」",
            "两边都留着。材料可能是真的，也可能是印错了或者被改过；记录也可能还没更新。不以后交的材料为准。",
        ]

    m = STATUS_WORDS.search(material)
    if m and company is not None:
        out[f"record.credit.status"] = [
            f"登记记录：{company.status}",
            f"材料上出现「{m.group(0)}」的说法",
            "两边都留着。登记记录是官方口径，但材料上的说法要问清楚。",
        ]
    return out


def attach_disputes(judges: list[Judgment], company_name: str, assertions: list[Assertion],
                    texts: list[RawRecord], company: CompanyProfile | None = None) -> list[Judgment]:
    """对已有判断做一次影响检查：新材料和已知记录对不上时，把两边证据挂在判断上。"""
    found = disputes(company_name, assertions, texts, company)
    ids = {j.id for j in judges}
    for j in judges:
        lines = found.get(j.id)
        if lines:
            j.dispute = lines
    for jid, lines in found.items():
        if jid in ids:
            continue
        judges.append(Judgment(id=jid, layer="confirmed", layer_label=LAYER_LABEL["confirmed"],
                               text=lines[0], scope=company_name, dispute=lines,
                               state="needs_check", state_label=STATE_LABEL["needs_check"],
                               plain=lines[-1]))
    return judges


# ---------- 判断级的变化：五格 ----------

def _core(j: Judgment) -> tuple:
    """一条判断到底在说什么。不含状态，用来判断"内容有没有变"。"""
    text = j.text
    if j.id.startswith("contract.blank."):
        text = text.replace("这份材料上没有", "所提供文本未见").replace("，也没有", "，也未见")
    return (text, tuple(b.quote or "" for b in j.basis), tuple(j.dispute))


def _fingerprint(j: Judgment) -> tuple:
    # 不含 basis 的 ref：条目在报告里的位置会随新材料前后移动，
    # 位置变了不等于这条判断变了。
    return (j.text, j.state, tuple(b.quote or "" for b in j.basis), tuple(j.dispute))


def _change(cur: Judgment, prev: Judgment | None, version_no: int) -> JudgmentChange:
    label = _short(cur.text, 40)
    if prev is None:
        if cur.id.startswith("ask."):
            kind, plain = "next_question", f"新出现一个要问对方的问题：{_short(cur.text, 60)}"
        elif cur.state == "unconfirmed":
            kind, plain = "unconfirmed", f"新增一项还没法确认的：{_short(cur.text, 60)}"
        elif cur.state == "needs_check":
            kind, plain = "recheck", f"新增一项需要核实的：{_short(cur.text, 60)}"
        else:
            kind, plain = "found", f"新增发现：{_short(cur.text, 60)}"
        return JudgmentChange(target=cur.id, label=label, kind=kind, text=cur.text,
                              after=cur.text, plain=plain, basis=cur.basis)

    cur.since = prev.since
    cur.history, cur.changed_at = list(prev.history), prev.changed_at
    # 人已经下过结论的（已澄清 / 已撤回），后面的版本不能悄悄把它推翻回去。
    if prev.state in ("clarified", "withdrawn") and _core(cur) == _core(prev):
        cur.state, cur.state_label, cur.plain = prev.state, prev.state_label, prev.plain
        cur.history, cur.changed_at = list(prev.history), prev.changed_at
        cur.unknown = list(prev.unknown)
        return JudgmentChange(target=cur.id, label=label, kind="same", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"{cur.state_label}过的，这一版还是这个结论：{_short(cur.text, 50)}")

    if _fingerprint(cur) == _fingerprint(prev):
        return JudgmentChange(target=cur.id, label=label, kind="same", text=cur.text,
                              before=prev.text, after=cur.text, plain="和上一版一致，没有变。")

    if cur.id.startswith("ask."):
        return JudgmentChange(target=cur.id, label=label, kind="next_question", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"下一步问题变了：{_short(cur.text, 60)}")

    if cur.state == "holds" and prev.state in ("needs_check", "unconfirmed"):
        cur.state, cur.state_label, cur.changed_at = "clarified", STATE_LABEL["clarified"], version_no
        return JudgmentChange(target=cur.id, label=label, kind="recheck", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"已澄清：{_short(prev.text, 50)}这条不再是疑点了。")
    if cur.state == "unconfirmed" and prev.state != "unconfirmed":
        cur.changed_at = version_no
        return JudgmentChange(target=cur.id, label=label, kind="unconfirmed", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"变成尚不能确认：{_short(cur.text, 50)}")
    if cur.state == "needs_check" and prev.state != "needs_check":
        cur.changed_at = version_no
        return JudgmentChange(target=cur.id, label=label, kind="recheck", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"需要重新核实：{_short(cur.text, 50)}")
    if cur.state == "needs_check":
        cur.state, cur.state_label, cur.changed_at = "revised", STATE_LABEL["revised"], version_no
        return JudgmentChange(target=cur.id, label=label, kind="recheck", text=cur.text,
                              before=prev.text, after=cur.text,
                              plain=f"这条被修订了：{_short(cur.text, 50)}")
    return JudgmentChange(target=cur.id, label=label, kind="found", text=cur.text,
                          before=prev.text, after=cur.text,
                          plain=f"新增发现：{_short(cur.text, 60)}")


def update(prev: list[Judgment], cur: list[Judgment], new_texts: dict[str, str],
           version_no: int) -> tuple[list[Judgment], list[JudgmentChange], str]:
    """把新版这堆判断和上一版逐条对上，算出判断级的变化。"""
    # Older saved contracts used name/title hashes. Reuse an existing identity
    # only for the same document, category and quoted evidence; a second copy
    # of a contract must still get its own ID. Never mutate the saved version.
    by_id = {j.id: j for j in prev}
    used = {j.id for j in cur if j.id in by_id}
    def evidence(j: Judgment) -> tuple:
        return tuple((b.ref, b.quote or "") for b in j.basis if b.ref)
    for j in cur:
        if not j.id.startswith("contract.") or j.id in by_id or not evidence(j):
            continue
        family = j.id.rsplit(".", 1)[0]
        candidates = [old for old in prev if old.id not in used
                      and old.id.rsplit(".", 1)[0] == family and evidence(old) == evidence(j)]
        if len(candidates) == 1:
            j.id = candidates[0].id
            used.add(j.id)
    because = list(new_texts.keys())
    changes: list[JudgmentChange] = []
    for j in cur:
        old = by_id.get(j.id)
        ch = _change(j, old, version_no)
        if ch.kind != "same" and because:
            ch.because = because
        changes.append(ch)
        # "需要重新核实"和"尚不能确认"不是一回事：一个要有人去查，一个现在根本没证据。
        # 一条判断刚变成需要核实，它下面那些还没证明的事要单独摆出来，不能埋在卡片里。
        if ch.kind in ("found", "recheck") and j.state in ("needs_check", "unconfirmed"):
            had = set(old.unknown) if old else set()
            for u in j.unknown:
                if u and u not in had:
                    changes.append(JudgmentChange(target=j.id, label=_short(u, 40), kind="unconfirmed",
                                                  text=u, after=u, because=because, basis=j.basis,
                                                  plain=f"还没证据：{_short(u, 60)}"))
    seen = {j.id for j in cur}
    for j in prev:
        if j.id in seen:
            continue
        changes.append(JudgmentChange(target=j.id, label=_short(j.text, 40), kind="dropped", text=j.text,
                                      before=j.text,
                                      plain=f"这一项在这版里不再出现（上一版是：{_short(j.text, 50)}）。"))
    return cur, changes, summarize(changes, version_no)


ORDER = ["cleared", "recheck", "found", "unconfirmed", "next_question", "dropped", "same"]
NAME = {"same": "保持不变", "found": "新增发现", "recheck": "需要重新核实",
        "unconfirmed": "尚不能确认", "next_question": "下一步问题", "dropped": "不再出现",
        "cleared": "已经澄清"}


def summarize(changes: list[JudgmentChange], version_no: int) -> str:
    if version_no <= 1:
        # 一条判断可能摊出好几行（比如一条需要核实下面挂着两条还没证据的事），
        # 所以"一共几条判断"按去重后的条数说，别把明细行也算成判断。
        count = {k: 0 for k in NAME}
        for c in changes:
            count[c.kind] += 1
        total = len({c.target for c in changes})
        head = "，".join(f"{NAME[k]} {count[k]} 条" for k in ("recheck", "unconfirmed") if count[k])
        tail = f"另有 {count['next_question']} 条要问对方的问题" if count["next_question"] else ""
        return f"第一版：一共 {total} 条判断" + (f"，{head}" if head else "") + (f"，{tail}" if tail else "") + "。"
    count = {k: 0 for k in NAME}
    for c in changes:
        count[c.kind] += 1
    parts = [f"{NAME[k]} {count[k]} 条" for k in ORDER if k != "same" and count[k]]
    head = "，".join(parts) if parts else "没有影响判断的变化"
    return f"和上一版比：{head}；其余 {count['same']} 条保持不变。"
