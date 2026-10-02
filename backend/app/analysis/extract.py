"""从宣传材料文字里找出需要核验的说法。

RuleExtractor 只用正则，不需要任何模型 key，结果可复现。
以后接大模型（读图片、处理改写过的说法）时，实现同一个 ClaimExtractor 接口即可；
模型只负责"找出说法并给出原文"，核验一律走 verify.py 里的确定性规则。
"""
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.models import ClaimKind


@dataclass
class RawClaim:
    kind: ClaimKind
    quotes: list[str] = field(default_factory=list)
    numbers: dict[str, float] = field(default_factory=dict)
    words: list[str] = field(default_factory=list)
    banks: list[str] = field(default_factory=list)
    licenses: list[str] = field(default_factory=list)  # 宣称拥有的牌照类型：信托、证券、期货……

    def add(self, quote: str, words: list[str] = (), banks: list[str] = ()) -> None:
        if quote not in self.quotes:
            self.quotes.append(quote)
        self.words += [w for w in words if w not in self.words]
        self.banks += [b for b in banks if b not in self.banks]


@dataclass
class Extraction:
    text: str
    claims: dict[ClaimKind, RawClaim]
    is_financial: bool
    has_risk_disclosure: bool
    has_bank_wm_disclosure: bool
    product_codes: list[str]
    benchmark_rates: list[float]
    pressure: list[str]
    refund_limits: list[str] = field(default_factory=list)  # 材料里限制退款的条款原文


class ClaimExtractor(Protocol):
    def extract(self, text: str) -> Extraction: ...


QUALIFICATION = re.compile(r"正规理财|正规金融|持牌|合法合规|安全稳健|受监管|监管备案")
GUARANTEE = re.compile(r"保本|保息|还本付息|本息无忧|刚性兑付|稳赚|零风险|无风险")
NEGATABLE = {"保本", "保息", "还本付息", "刚性兑付"}
ANNUAL_RATE = re.compile(r"年化(?:收益率?|回报率?)?[^\d%％]{0,4}(\d+(?:\.\d+)?)[%％]")
BENCHMARK = re.compile(r"业绩比较基准[^\d%％]{0,4}(\d+(?:\.\d+)?)[%％]")
PARTNER = re.compile(r"(?P<bank>[一-龥]{0,10}银行)?(?:资金)?存管|银行(?:战略)?合作")
BACKGROUND = re.compile(r"国资背景|国企背景|央企|国有控股|国有企业|政府背景|政府支持|上市公司|上市集团|上市银行|"
                        r"(?:证券交易所|上交所|深交所|北交所|主板|A股|港股)[^。；]{0,12}上市")
CAPITAL = re.compile(r"注册资本[^\d]{0,4}(\d+(?:\.\d+)?)(亿|万)")
STORES = re.compile(r"(\d+)\s*(?:余|多)?\s*家(?:门店|分公司|网点|分店|营业部|分支机构)")
MEMBERS = re.compile(r"(\d+(?:\.\d+)?)(万|亿)?名?(?:会员|客户|用户|投资人)")
# 像不像在卖理财产品。"基金""存管"这类词公司介绍里也常有，不算；公司名里的"理财"（杭银理财有限责任公司）也不算
COMPANY_NAME = re.compile(r"[一-龥]{2,20}(?:有限责任公司|股份有限公司|有限公司)")
FINANCIAL = re.compile(r"理财|年化|保本|保息|收益率|收益权|认购|固定收益|还本付息|业绩比较基准")
# 真实文案的写法：拥有信托、证券……等牌照 / 集团管理资产 3800 亿元 / 公司规模 100-499 人
LICENSE_CLAIM = re.compile(r"(?:拥有|具有|具备|持有|取得|获得|手握)[^。；]{0,30}?牌照|全牌照")
LICENSE_TYPE = re.compile(r"信托|证券|期货|公募|私募|基金|保险|银行|支付|股权投资|融资租赁|小额贷款|小贷")
AUM = re.compile(r"(?:管理|受托管理|资产管理)的?(?:资产|规模|资金)(?:规模)?[^\d]{0,6}(\d+(?:\.\d+)?)\s*(亿|万)")
STAFF = re.compile(r"(\d+)\s*[-~—至到]\s*\d+\s*人|员工(?:人数)?[^\d]{0,4}(\d+)\s*(?:余|多)?\s*人")
GROUP_BACKING = re.compile(r"(?:大型|知名|综合)[^。；，,]{0,8}集团[^。；]{0,8}(?:注资|入股|控股|投资)")
BANK_WM_DISCLOSURE = re.compile(r"理财非存款")
ANY_DISCLOSURE = re.compile(r"理财非存款|投资有风险|投资须谨慎|投资需谨慎|市场有风险|产品有风险")
PRODUCT_CODE = re.compile(r"(?<![A-Za-z0-9])Z\d{10,14}(?!\d)")
PRESSURE = re.compile(r"名额有限|先到先得|限时|仅剩|最后\d+天|错过再等|今日截止|内部名额")
# 收款信息：户名在"开户行""账号"或标点前截断
PAYEE = re.compile(r"(?:户名|收款人|收款方|收款单位|账户名|开户名)\s*[:：为是]?\s*"
                   r"(?P<name>[一-龥A-Za-z·（）()*＊]{2,40}?)(?=开户|账号|卡号|账户|[\s，,。；;：:、]|\d|$)")
PERSONAL_ACCOUNT = re.compile(r"个人账户|个人卡|私人账户|个人银行卡|个人微信|个人支付宝|对私账户|转给我|转我个人")
TRANSFER = re.compile(r"转账|汇款|打款|转入|汇至|打到|转到|收款")
ACCOUNT_NO = re.compile(r"\d{12,19}")
# 退款或退出承诺；以及限制退款的条款
REFUND = re.compile(r"随时(?:都)?(?:可以|可|能)?(?:退|取|赎回|提现|支取|退出)|随存随取|无理由退|保证退款|全额退款|不满意退款")
NO_REFUND = re.compile(r"不予退还|概不退|不退款|不予退款|不得退|不可退|不能退|恕不退|扣除[^。；]{0,10}[%％]|违约金|"
                       r"手续费[^。；]{0,8}[%％]|锁定期|封闭期")
# 招聘时先交钱；只有材料像招聘时才算
FEE = re.compile(r"培训费|押金|保证金|服装费|工装费|体检费|报名费|资料费|介绍费|入职费|上岗费|中介费")
FEE_ASK = re.compile(r"交|缴|收取|支付|先付|预付|自付|自费|需付|\d+元")
JOB = re.compile(r"入职|上岗|招聘|应聘|录用|面试|岗前|offer|试用期|工资|月薪|底薪|岗位", re.I)
UNIT = {"万": 1e4, "亿": 1e8, None: 1.0}


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _guarantees(flat: str) -> list[str]:
    """"非保本""不承诺保本"这类否定说法不算承诺。"""
    words = []
    for m in GUARANTEE.finditer(flat):
        if m.group(0) in NEGATABLE and re.search(r"[非不无]", flat[max(0, m.start() - 4):m.start()]):
            continue
        if m.group(0) not in words:
            words.append(m.group(0))
    return words


class RuleExtractor:
    def extract(self, text: str) -> Extraction:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        claims: dict[ClaimKind, RawClaim] = {}
        refund_limits: list[str] = []
        job_like = bool(JOB.search(text))

        def claim(kind: ClaimKind) -> RawClaim:
            return claims.setdefault(kind, RawClaim(kind))

        # 长段落按句拆开，说法的原文只取那一句
        units = [u.strip() for line in lines
                 for u in (re.split(r"(?<=[。；！!？?])", line) if len(line) > 40 else [line]) if u.strip()]
        for line in units:
            f = _flat(line)
            words = QUALIFICATION.findall(f)
            lic = LICENSE_CLAIM.search(f)
            if words or lic:
                c = claim(ClaimKind.qualification)
                c.add(line, words + (["牌照"] if lic else []))
                if lic:
                    c.licenses += [t for t in LICENSE_TYPE.findall(lic.group(0)) if t not in c.licenses]
            guarantees, rate = _guarantees(f), ANNUAL_RATE.search(f)
            if guarantees or rate:
                c = claim(ClaimKind.return_promise)
                c.add(line, guarantees)
                if rate:
                    c.numbers["annual_rate"] = max(c.numbers.get("annual_rate", 0), float(rate.group(1)))
            if m := PARTNER.search(f):
                claim(ClaimKind.partner).add(line, banks=[m.group("bank")] if m.group("bank") else [])
            if words := BACKGROUND.findall(f) + GROUP_BACKING.findall(f):
                claim(ClaimKind.background).add(line, words)
            if m := CAPITAL.search(f):
                c = claim(ClaimKind.capital)
                c.add(line)
                c.numbers["capital"] = float(m.group(1)) * UNIT[m.group(2)]
            stores, members, aum, staff = STORES.search(f), MEMBERS.search(f), AUM.search(f), STAFF.search(f)
            if stores or members or aum or staff:
                c = claim(ClaimKind.scale)
                c.add(line)
                if stores:
                    c.numbers["stores"] = float(stores.group(1))
                if members:
                    c.numbers["members"] = float(members.group(1)) * UNIT[members.group(2)]
                if aum:
                    c.numbers["aum"] = float(aum.group(1)) * UNIT[aum.group(2)]
                    if "集团" in f:
                        c.numbers["aum_group"] = 1  # 说的是"集团"的规模，不是它自己
                if staff:
                    c.numbers["staff"] = float(staff.group(1) or staff.group(2))
            names = [m.group("name") for m in PAYEE.finditer(line)]  # 用原行：空格是户名的分隔
            personal = PERSONAL_ACCOUNT.findall(f)
            if names or personal or (TRANSFER.search(f) and ACCOUNT_NO.search(f)):
                claim(ClaimKind.payee).add(line, personal, banks=names)  # banks 字段在这里存户名
            if words := REFUND.findall(f):
                claim(ClaimKind.refund).add(line, words)
            if NO_REFUND.search(f) and line not in refund_limits:
                refund_limits.append(line)
            if job_like and (fees := FEE.findall(f)) and FEE_ASK.search(f):
                claim(ClaimKind.upfront_fee).add(line, fees)

        # OCR 常把"年化"和"9%"拆成两行：单行没找到数字时，再看相邻两行
        for i in range(len(lines) - 1):
            pair, f = f"{lines[i]} {lines[i + 1]}", _flat(lines[i] + lines[i + 1])
            if "annual_rate" not in claims.get(ClaimKind.return_promise, RawClaim(ClaimKind.return_promise)).numbers:
                if rate := ANNUAL_RATE.search(f):
                    c = claim(ClaimKind.return_promise)
                    c.add(pair)
                    c.numbers["annual_rate"] = float(rate.group(1))
            if ClaimKind.capital not in claims and (m := CAPITAL.search(f)):
                c = claim(ClaimKind.capital)
                c.add(pair)
                c.numbers["capital"] = float(m.group(1)) * UNIT[m.group(2)]

        flat = _flat(text)
        return Extraction(
            text=text,
            claims=claims,
            is_financial=bool(FINANCIAL.search(COMPANY_NAME.sub("", flat))),
            has_risk_disclosure=bool(ANY_DISCLOSURE.search(flat)),
            has_bank_wm_disclosure=bool(BANK_WM_DISCLOSURE.search(flat)),
            product_codes=list(dict.fromkeys(PRODUCT_CODE.findall(flat))),
            benchmark_rates=[float(x) for x in BENCHMARK.findall(flat)],
            pressure=list(dict.fromkeys(PRESSURE.findall(flat))),
            refund_limits=refund_limits,
        )
