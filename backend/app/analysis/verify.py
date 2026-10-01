"""拿宣传说法逐条对照记录。全部是确定性规则：同样的输入，永远得到同样的结论。

每条检查都带 source（指回 sources/catalog.py），没查的地方标 Status.none，
不把"没数据"说成"没问题"，也不把"没数据"说成"有问题"。
"""
import re

from app.analysis.extract import Extraction, RawClaim
from app.analysis.fmt import money, wan
from app.config import HIGH_RETURN_RATIO, LOW_PAID_RATIO, REF_DEPOSIT_RATE
from app.models import (AmacHit, Assertion, Check, ClaimKind, CompanyProfile, Coverage, LicenseHit,
                        MissingItem, RegistryHit, Status, Verdict)
from app.sources.licenses import LicenseIndex, normalize

KIND_META = {
    ClaimKind.qualification: ("A1", "资格"),
    ClaimKind.return_promise: ("A2", "收益承诺"),
    ClaimKind.partner: ("A3", "合作机构"),
    ClaimKind.background: ("A4", "背景"),
    ClaimKind.capital: ("A5", "规模"),
    ClaimKind.scale: ("A6", "规模"),
    ClaimKind.payee: ("A7", "收款信息"),
    ClaimKind.refund: ("A8", "退款承诺"),
    ClaimKind.upfront_fee: ("A9", "先交钱"),
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

NOT_COVERED = "没查：还没有这家公司的登记数据"
NO_DATA_PLAIN = "还没有这家公司的登记数据，暂时无法核验。"

Review = tuple[list[Check], Verdict, str]


def financial_scope(scope: str) -> str | None:
    m = FIN_SCOPE.search(NEGATED_SCOPE.sub("", scope))
    return m.group(0) if m else None


def _short(s: str, n: int = 26) -> str:
    return s if len(s) <= n else s[:n] + "……"


LICENSE_SHORT = {"nfra_insurance": "保险", "csrc_futures": "期货", "pbc_payment": "支付"}
# 名字像证券公司、公募基金：这两份名录还没接入，查不到也不能下结论
MAYBE_SECURITIES = re.compile(r"证券|基金管理|期货")


def _license_check(lic: LicenseHit, others: list[RegistryHit]) -> tuple[Check, RegistryHit | None]:
    """几份持牌名单合成一条检查：命中哪份写哪份；都没有就写查了几份、共多少家。"""
    if lic.found:
        return Check(label="持牌机构名单", result=f"银行业金融机构法人名单已收录：{lic.record.type}（机构编码 {lic.record.code}）",
                     status=Status.ok, source=lic.source), None
    for h in others:
        if not h.found:
            continue
        r = h.record or {}
        if h.registry == "pbc_payment":
            return Check(label="持牌机构名单", status=Status.warn, source=h.registry,
                         result=f"{h.title}已收录：许可证 {r.get('license_no', '')}，业务 {_short(r.get('business', ''), 30)}。"
                                f"支付牌照只能做收付款，不能卖理财"), h
        kind = r.get("type") or LICENSE_SHORT.get(h.registry, "")
        return Check(label="持牌机构名单", result=f"{h.title}已收录：{kind}", status=Status.ok, source=h.registry), h
    counts = [f"银行业 {lic.count:,} 家" if lic.count else "银行业"]
    counts += [f"{LICENSE_SHORT.get(h.registry, h.title)} {h.count:,} 家" for h in others]
    near = lic.suggestions[0].name if lic.suggestions else next((h.suggestions[0] for h in others if h.suggestions), None)
    hint = f"；名称相近的有：{near}" if near else ""
    return Check(label="持牌机构名单", result=f"查了 {len(counts)} 份持牌名单（{'、'.join(counts)}），都没有它{hint}",
                 status=Status.bad, source=lic.source), None


def _amac_check(amac: AmacHit) -> Check:
    if amac.coverage is Coverage.not_covered:
        return Check(label="私募基金管理人登记", result="没查：中基协名单还没下载，也没有人工查询记录",
                     status=Status.none, source=amac.source)
    if amac.registered:
        r = amac.record or {}
        credit, special = str(r.get("credit_tips")) == "1", str(r.get("special_tips")) == "1"
        detail = f"：{r['register_no']}，{r.get('invest_type', '')}，在管基金 {r.get('fund_count', 0)} 只" if r else ""
        tail = ("；协会公示了它的诚信信息（可能是处罚或纪律处分），要点开详情看" if credit else
                "；协会对它有特别提示（这类提示很常见，多是信息报送问题）" if special else "")
        return Check(label="私募基金管理人登记", result=f"已登记{detail}{tail}",
                     status=Status.warn if credit else Status.ok, source=amac.source)
    scope = f"（截至 {amac.as_of} 登记的 {amac.count:,} 家私募管理人里没有它）" if amac.count else ""
    return Check(label="私募基金管理人登记", result=f"未登记{scope}", status=Status.bad, source=amac.source)


def qualification_review(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
                         others: list[RegistryHit] = ()) -> Review:
    others = list(others)
    license_check, other_hit = _license_check(lic, others)
    amac_check = _amac_check(amac)
    if license_check.status is Status.ok and amac_check.status is Status.bad:
        # 持牌机构本来就不靠私募登记卖产品，没登记不算问题
        amac_check = amac_check.model_copy(update={"status": Status.ok, "result": "未登记（它是持牌机构，不需要私募登记）"})
    if amac.registered and license_check.status is Status.bad:
        license_check = license_check.model_copy(update={"status": Status.warn})  # 私募本来就没有这几类牌照
    checks = [license_check, amac_check]

    if ext.product_codes:
        checks.append(Check(label="理财产品登记编码", result=f"材料上写了 {'、'.join(ext.product_codes)}，待到中国理财网核验",
                            status=Status.warn, source="material"))
    elif not ext.is_financial:
        checks.append(Check(label="理财产品登记编码", result="还没有理财宣传材料，无从核对", status=Status.none,
                            source="material"))
    else:
        checks.append(Check(label="理财产品登记编码", result="材料上没有", status=Status.miss, source="material"))

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
    if other_hit and other_hit.registry == "pbc_payment":
        return checks, Verdict.attention, "它有支付牌照，但支付牌照只能做收付款，不能卖理财、不能吸收存款。"
    if other_hit:
        return checks, Verdict.consistent, f"它在{other_hit.title}里，是持牌机构。"
    if amac.registered:
        tips = "协会公示了它的诚信信息，" if checks[1].status is Status.warn else ""
        return checks, Verdict.attention, f"它登记了私募基金管理人；{tips}私募只能非公开卖给合格投资者，不能对大众公开宣传。"
    if MAYBE_SECURITIES.search(lic.query):
        return checks, Verdict.unverifiable, "名字像证券或基金公司，证券公司、公募基金名录还没接入，暂时下不了结论。"
    if amac.coverage is Coverage.not_found and (company is not None or others):
        return checks, Verdict.mismatch, f"{1 + len(others)} 份持牌名单和私募登记里都查不到它：查不到它有卖理财的资格。"
    return checks, Verdict.unverifiable, "不在银行业金融机构名单里；其他名单还没接入，私募登记也没查到记录，暂时下不了结论。"


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
        checks.append(Check(label="存管银行", result="材料没写明是哪家银行", status=Status.miss, source="material"))
    for bank in named:
        hit = licenses.lookup(bank)
        record = hit.record or (hit.suggestions[0] if hit.suggestions else None)
        if record:
            checks.append(Check(label="存管银行", result=f"{record.name}是持牌机构；但存管关系要看协议",
                                status=Status.warn, source="nfra_bank_list"))
        else:
            checks.append(Check(label="存管银行", result=f"名单中查不到\"{bank}\"", status=Status.bad, source="nfra_bank_list"))
    checks.append(Check(label="存管协议", result="未提供", status=Status.miss, source="material"))
    lead = f"写了{named[0]}，但没给存管协议" if named else "没写是哪家银行、没给协议"
    return checks, Verdict.unverifiable, f"{lead}，无法核验；而且资金存管不等于担保。"


def background_review(claim: RawClaim, company: CompanyProfile | None) -> Review:
    checks = []
    if any("上市" in w for w in claim.words):
        checks.append(Check(label="上市公司", result="没查：上市公司名单还没接入", status=Status.none, source="registry"))
    if company is None or not company.shareholders:
        checks.append(Check(label="股东", result=NOT_COVERED, status=Status.none, source="registry"))
        return checks, Verdict.unverifiable, NO_DATA_PLAIN

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
                Verdict.unverifiable, NO_DATA_PLAIN)
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
                Verdict.unverifiable, NO_DATA_PLAIN)
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
        checks.append(Check(label="会员数", result="没有公开来源，无法核验", status=Status.miss, source="material"))

    if gaps:
        return checks, Verdict.misleading, f"宣称 {stores:g} 家门店；{'，'.join(gaps)}。"
    if stores is None:
        return checks, Verdict.unverifiable, "会员数没有公开来源，无法核验。"
    return checks, Verdict.consistent, "登记的规模和宣传大致相符。"


def _same_entity(name: str, company: str) -> bool:
    n, c = normalize(name), normalize(company)
    return n == c or (len(n) >= 4 and n in c) or c in n


def payee_review(claim: RawClaim, company_name: str) -> Review:
    """收款户名和公司名对不上，或者要求打到个人账户：判与记录不符。所有场景都查。"""
    checks = []
    others = [n for n in claim.banks if not _same_entity(n, company_name)]
    for n in claim.banks:
        same = n not in others
        checks.append(Check(label="收款户名", result=f"\"{n}\"，{'和公司名一致' if same else '不是这家公司'}",
                            status=Status.ok if same else Status.bad, source="material"))
    if claim.words:
        checks.append(Check(label="收款账户", result=f"要求打到{'、'.join(claim.words)}", status=Status.bad, source="material"))
    if not claim.banks and not claim.words:
        checks.append(Check(label="收款户名", result="材料给了转账信息，但没写户名", status=Status.miss, source="material"))
        return checks, Verdict.unverifiable, "只给了账号没写户名，先问清楚钱打给谁。"
    if others or claim.words:
        who = f"\"{others[0]}\"" if others else "个人账户"
        return checks, Verdict.mismatch, f"钱要打给{who}，不是{company_name}本身。钱进了别人的账户，出了事很难追回。"
    return checks, Verdict.consistent, "收款户名就是这家公司。"


def refund_review(claim: RawClaim, ext: Extraction) -> Review:
    """说随时可退：材料里有限制退款的条款就对照条款，没有合同就无法核验。"""
    said = "、".join(f"\"{w}\"" for w in claim.words)
    if ext.refund_limits:
        clause = ext.refund_limits[0]
        checks = [Check(label="退款条款", result=f"材料里另有：{_short(clause, 40)}", status=Status.bad, source="material")]
        return checks, Verdict.mismatch, f"嘴上说{said}，但材料里写着\"{_short(clause, 30)}\"。以合同条款为准。"
    checks = [Check(label="退款条款", result="没有看到合同或退款条款", status=Status.miss, source="material")]
    return checks, Verdict.unverifiable, f"说{said}，但没有合同条款可以对照。口头承诺出了事很难作数，先要合同。"


def upfront_fee_review(claim: RawClaim) -> Review:
    fees = "、".join(claim.words)
    checks = [Check(label="入职前收费", result=f"要求交{fees}", status=Status.bad, source="reg_labor9")]
    return checks, Verdict.redline, f"招人时要求先交{fees}。《劳动合同法》第九条规定，用人单位不得以任何名义向劳动者收取财物。"


def missing_items(ext: Extraction) -> list[MissingItem]:
    if ext.is_financial and not ext.has_risk_disclosure:
        return [MissingItem(id="M1", text="理财非存款、产品有风险、投资须谨慎", source="reg_wm_sales",
                            plain="正规理财的销售材料都要写风险提示，银行理财按规定要写这句话。这份材料上一句风险提示都没有。")]
    return []


def review(kind: ClaimKind, claim: RawClaim, ext: Extraction, company: CompanyProfile | None, lic: LicenseHit,
           amac: AmacHit, licenses: LicenseIndex, company_name: str, others: list[RegistryHit] = ()) -> Review:
    match kind:
        case ClaimKind.qualification:
            return qualification_review(ext, company, lic, amac, others)
        case ClaimKind.return_promise:
            return return_review(claim)
        case ClaimKind.partner:
            return partner_review(claim, licenses)
        case ClaimKind.background:
            return background_review(claim, company)
        case ClaimKind.capital:
            return capital_review(claim, company)
        case ClaimKind.scale:
            return scale_review(claim, company)
        case ClaimKind.payee:
            return payee_review(claim, company_name)
        case ClaimKind.refund:
            return refund_review(claim, ext)
        case ClaimKind.upfront_fee:
            return upfront_fee_review(claim)


def verify(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
           licenses: LicenseIndex, company_name: str = "",
           others: list[RegistryHit] = ()) -> tuple[list[Assertion], list[MissingItem]]:
    assertions = []
    for kind in ClaimKind:
        claim = ext.claims.get(kind)
        if claim is None:
            continue
        checks, verdict, plain = review(kind, claim, ext, company, lic, amac, licenses, company_name or lic.query,
                                        others)
        aid, kind_label = KIND_META[kind]
        verdict_label, color = VERDICT_META[verdict]
        assertions.append(Assertion(id=aid, kind=kind, kind_label=kind_label, text=" / ".join(claim.quotes),
                                    quotes=claim.quotes, verdict=verdict, verdict_label=verdict_label, color=color,
                                    plain=plain, checks=checks))
    return assertions, missing_items(ext)
