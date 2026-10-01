"""拿宣传说法逐条对照记录。全部是确定性规则：同样的输入，永远得到同样的结论。

每条检查都带 source（指回 sources/catalog.py），没查的地方标 Status.none，
不把"没数据"说成"没问题"，也不把"没数据"说成"有问题"。
"""
import re

from app.analysis.extract import Extraction, RawClaim
from app.analysis.fmt import money, wan
from app.config import HIGH_RETURN_RATIO, LOW_PAID_RATIO, REF_DEPOSIT_RATE
from app.models import (AmacHit, Assertion, Check, ClaimKind, CompanyProfile, Coverage, LicenseHit,
                        MissingItem, Status, Verdict)
from app.sources.licenses import LicenseIndex

KIND_META = {
    ClaimKind.qualification: ("A1", "资格"),
    ClaimKind.return_promise: ("A2", "收益承诺"),
    ClaimKind.partner: ("A3", "合作机构"),
    ClaimKind.background: ("A4", "背景"),
    ClaimKind.capital: ("A5", "规模"),
    ClaimKind.scale: ("A6", "规模"),
}
VERDICT_META = {
    Verdict.mismatch: ("与记录不符", "red"),
    Verdict.redline: ("不合规承诺", "red"),
    Verdict.misleading: ("说法有误导", "amber"),
    Verdict.attention: ("需要留意", "amber"),
    Verdict.unverifiable: ("无法核验", "grey"),
    Verdict.consistent: ("与记录相符", "green"),
}

FIN_SCOPE = re.compile(r"金融|理财|资产管理|基金|存款|贷款|保险|证券|期货|信托|融资")
# 经营范围里常见"（未经金融监管部门批准，不得从事……金融业务）"，这段是禁止性说明，不能算金融业务
NEGATED_SCOPE = re.compile(r"[（(][^）)]*不得[^）)]*[）)]")
STATE_OWNED = re.compile(r"国有资产监督管理|人民政府|财政(?:局|厅|部)|国资|国有")
GENERIC_BANK = re.compile(r"某|大型|知名|多家|国有大行")

NOT_COVERED = "没查：演示版没有这家公司的登记数据"

Review = tuple[list[Check], Verdict, str]


def financial_scope(scope: str) -> str | None:
    m = FIN_SCOPE.search(NEGATED_SCOPE.sub("", scope))
    return m.group(0) if m else None


def _short(s: str, n: int = 26) -> str:
    return s if len(s) <= n else s[:n] + "……"


def qualification_review(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit) -> Review:
    checks = []
    if lic.found:
        checks.append(Check(label="银行业金融机构法人名单", result=f"已收录：{lic.record.type}（机构编码 {lic.record.code}）",
                            status=Status.ok, source=lic.source))
    else:
        hint = f"；名称相近的有：{lic.suggestions[0].name}" if lic.suggestions else ""
        checks.append(Check(label="银行业金融机构法人名单", result=f"未收录{hint}", status=Status.bad, source=lic.source))

    if amac.coverage is Coverage.not_covered:
        checks.append(Check(label="私募基金管理人登记", result="没查：演示版未接入中基协实时查询",
                            status=Status.none, source=amac.source))
    else:
        checks.append(Check(label="私募基金管理人登记", result="已登记" if amac.registered else "未登记",
                            status=Status.ok if amac.registered else Status.bad, source=amac.source))

    if ext.product_codes:
        checks.append(Check(label="理财产品登记编码", result=f"材料上写了 {'、'.join(ext.product_codes)}，待到中国理财网核验",
                            status=Status.warn, source="flyer"))
    else:
        checks.append(Check(label="理财产品登记编码", result="材料上没有", status=Status.miss, source="flyer"))

    if company is None:
        checks.append(Check(label="经营范围", result=NOT_COVERED, status=Status.none, source="registry"))
    elif word := financial_scope(company.scope):
        checks.append(Check(label="经营范围", result=f"含\"{word}\"——经营范围里写了，不等于有金融牌照",
                            status=Status.warn, source="registry"))
    else:
        checks.append(Check(label="经营范围", result=f"{_short(company.scope)}不含任何金融业务",
                            status=Status.bad, source="registry"))

    if lic.found:
        return checks, Verdict.consistent, f"它在银行业金融机构名单里（{lic.record.type}），是持牌机构。"
    if amac.registered:
        return checks, Verdict.attention, "它登记了私募基金管理人；但私募只能非公开卖给合格投资者，不能对大众公开宣传。"
    if amac.coverage is Coverage.not_found and company is not None:
        return checks, Verdict.mismatch, "查不到它有卖理财的资格。"
    return checks, Verdict.unverifiable, "不在银行业金融机构名单里；证券、保险、私募等名单演示版还没接入，暂时下不了结论。"


def return_review(claim: RawClaim) -> Review:
    checks = []
    if claim.words:
        checks.append(Check(label=f"承诺\"{'、'.join(claim.words)}\"", result="资管新规后，资产管理产品不得承诺保本保收益",
                            status=Status.bad, source="reg_amr"))
    rate = claim.numbers.get("annual_rate")
    ratio = rate / 100 / REF_DEPOSIT_RATE if rate is not None else None
    if ratio is not None:
        checks.append(Check(label="收益对比（演示参数）",
                            result=f"年化 {rate:g}% ÷ 一年期定存 {REF_DEPOSIT_RATE:.1%} ≈ {ratio:.1f} 倍",
                            status=Status.warn if ratio >= HIGH_RETURN_RATIO else Status.ok, source="param_rate"))
    if claim.words:
        tail = f"；{rate:g}% 约为定存的 {ratio:.1f} 倍" if ratio is not None else ""
        return checks, Verdict.redline, f"正规理财不允许承诺保本{tail}。"
    if ratio is not None and ratio >= HIGH_RETURN_RATIO:
        return checks, Verdict.attention, f"收益约为定存的 {ratio:.1f} 倍。高收益本身不违法，但要问清楚钱从哪来。"
    return checks, Verdict.consistent, "没有保本承诺，收益表述在常见范围内。"


def partner_review(claim: RawClaim, licenses: LicenseIndex) -> Review:
    checks = []
    named = [b for b in claim.banks if not GENERIC_BANK.search(b)]
    if not named:
        checks.append(Check(label="存管银行", result="材料没写明是哪家银行", status=Status.miss, source="flyer"))
    for bank in named:
        hit = licenses.lookup(bank)
        record = hit.record or (hit.suggestions[0] if hit.suggestions else None)
        if record:
            checks.append(Check(label="存管银行", result=f"{record.name}是持牌机构；但存管关系要看协议",
                                status=Status.warn, source="nfra_bank_list"))
        else:
            checks.append(Check(label="存管银行", result=f"名单中查不到\"{bank}\"", status=Status.bad, source="nfra_bank_list"))
    checks.append(Check(label="存管协议", result="未提供", status=Status.miss, source="flyer"))
    lead = f"写了{named[0]}，但没给存管协议" if named else "没写是哪家银行、没给协议"
    return checks, Verdict.unverifiable, f"{lead}，无法核验；而且资金存管不等于担保。"


def background_review(claim: RawClaim, company: CompanyProfile | None) -> Review:
    checks = []
    if any("上市" in w for w in claim.words):
        checks.append(Check(label="上市公司", result="没查：演示版未接入上市公司名单", status=Status.none, source="registry"))
    if company is None or not company.shareholders:
        checks.append(Check(label="股东", result=NOT_COVERED, status=Status.none, source="registry"))
        return checks, Verdict.unverifiable, "演示版没有这家公司的股东数据，暂时无法核验。"

    holders = "、".join(f"{h.name} {h.pct:g}%" for h in company.shareholders)
    state = [h for h in company.shareholders if STATE_OWNED.search(h.name)]
    if all(h.type == "自然人" for h in company.shareholders):
        checks += [Check(label="股东", result=f"{holders}，均为自然人", status=Status.bad, source="registry"),
                   Check(label="股权穿透", result="无国有企业或政府机构持股", status=Status.bad, source="registry")]
        return checks, Verdict.mismatch, f"{len(company.shareholders)} 个股东都是自然人，没有任何国有持股。"
    if state:
        checks.append(Check(label="股东", result=f"{holders}；其中 {state[0].name} 疑似国有主体",
                            status=Status.warn, source="registry"))
        return checks, Verdict.attention, f"股东中有国有背景的 {state[0].name}（{state[0].pct:g}%）；但国资持股不等于国家担保。"
    checks.append(Check(label="股东", result=f"{holders}；股东是企业，需要继续往上穿透",
                        status=Status.warn, source="registry"))
    return checks, Verdict.unverifiable, "股东是企业，要继续往上查才能确认有没有国资。"


def capital_review(claim: RawClaim, company: CompanyProfile | None) -> Review:
    if company is None:
        return ([Check(label="注册资本", result=NOT_COVERED, status=Status.none, source="registry")],
                Verdict.unverifiable, "演示版没有这家公司的登记数据，暂时无法核验。")
    checks = []
    claimed, reg, paid = claim.numbers.get("capital"), company.reg_capital, company.paid_capital
    same = claimed is not None and abs(claimed - reg) <= reg * 0.01
    due = f"，认缴期限 {company.capital_due}" if company.capital_due else ""
    if claimed is not None:
        checks.append(Check(label="注册资本（认缴）",
                            result=f"{money(reg)}{due}，与宣传一致" if same else f"登记为 {money(reg)}，宣传写 {money(claimed)}",
                            status=Status.ok if same else Status.bad, source="registry"))
    if paid is None:
        checks.append(Check(label="实缴资本", result="年报未公示", status=Status.none, source="annual_report"))
    else:
        checks.append(Check(label="实缴资本（2025 年报）", result=f"{money(paid)}（企业自行填报，未经审计）",
                            status=Status.bad if paid < reg * LOW_PAID_RATIO else Status.ok, source="annual_report"))

    if claimed is not None and not same:
        return checks, Verdict.mismatch, f"宣传写注册资本 {wan(claimed)}，登记的是 {wan(reg)}。"
    if paid is None:
        return checks, Verdict.unverifiable, "注册资本是\"承诺\"，实际交了多少年报没公示，判断不了实力。"
    if paid < reg * LOW_PAID_RATIO:
        return checks, Verdict.misleading, f"{wan(reg)}是\"承诺\"，实际交了 {money(paid)}。"
    return checks, Verdict.consistent, f"注册资本 {wan(reg)}，实缴 {wan(paid)}，与宣传相符。"


def scale_review(claim: RawClaim, company: CompanyProfile | None) -> Review:
    stores, members = claim.numbers.get("stores"), claim.numbers.get("members")
    if company is None:
        return ([Check(label="规模", result=NOT_COVERED, status=Status.none, source="registry")],
                Verdict.unverifiable, "演示版没有这家公司的登记数据，暂时无法核验。")
    checks, gaps = [], []
    if company.insured is None:
        checks.append(Check(label="参保人数（年报）", result="未公示（企业可选择不公示）", status=Status.none, source="annual_report"))
    else:
        short = stores is not None and company.insured < stores
        if short:
            gaps.append(f"年报里只有 {company.insured} 人参保")
        checks.append(Check(label="参保人数（年报）", result=f"{company.insured} 人",
                            status=Status.warn if short else Status.ok, source="annual_report"))
    if company.branches is not None and stores is not None:
        few = company.branches < stores / 2
        if few:
            gaps.append(f"登记的分支机构 {company.branches} 家")
        checks.append(Check(label="分支机构（登记）", result=f"{company.branches} 家",
                            status=Status.warn if few else Status.ok, source="registry"))
    if members is not None:
        checks.append(Check(label="会员数", result="没有公开来源，无法核验", status=Status.miss, source="flyer"))

    if gaps:
        return checks, Verdict.misleading, f"宣称 {stores:g} 家门店；{'，'.join(gaps)}。"
    if stores is None:
        return checks, Verdict.unverifiable, "会员数没有公开来源，无法核验。"
    return checks, Verdict.consistent, "登记的规模和宣传大致相符。"


def missing_items(ext: Extraction) -> list[MissingItem]:
    if ext.is_financial and not ext.has_risk_disclosure:
        return [MissingItem(id="M1", text="理财非存款、产品有风险、投资须谨慎", source="reg_wm_sales",
                            plain="正规理财的销售材料都要写风险提示，银行理财按规定要写这句话。这份材料上一句风险提示都没有。")]
    return []


def verify(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
           licenses: LicenseIndex) -> tuple[list[Assertion], list[MissingItem]]:
    assertions = []
    for kind in ClaimKind:
        claim = ext.claims.get(kind)
        if claim is None:
            continue
        match kind:
            case ClaimKind.qualification:
                checks, verdict, plain = qualification_review(ext, company, lic, amac)
            case ClaimKind.return_promise:
                checks, verdict, plain = return_review(claim)
            case ClaimKind.partner:
                checks, verdict, plain = partner_review(claim, licenses)
            case ClaimKind.background:
                checks, verdict, plain = background_review(claim, company)
            case ClaimKind.capital:
                checks, verdict, plain = capital_review(claim, company)
            case ClaimKind.scale:
                checks, verdict, plain = scale_review(claim, company)
        aid, kind_label = KIND_META[kind]
        verdict_label, color = VERDICT_META[verdict]
        assertions.append(Assertion(id=aid, kind=kind, kind_label=kind_label, text=" / ".join(claim.quotes),
                                    quotes=claim.quotes, verdict=verdict, verdict_label=verdict_label, color=color,
                                    plain=plain, checks=checks))
    return assertions, missing_items(ext)
