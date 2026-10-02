"""企查查智能体数据平台（agent.qcc.com）：工商登记、风险扫描、股东、分支机构、上市信息，有记录的风险项再取明细。

- 个人可注册：注册送 500 积分，每天再送；同一家公司一个自然月最多扣 100 积分（平台封顶）。
- 协议是 MCP（JSON-RPC over HTTP）：POST https://agent.qcc.com/mcp/<server>/stream，Authorization: Bearer <Key>。
  不用握手，直接 tools/call；响应是 JSON 或 SSE 的 data: 行，result.content[0].text 是一段 JSON。
- 第三方加工的数据：来源类型 commercial，界面写"商业数据"，有出入以国家企业信用信息公示系统为准。
- 平台的"摘要"里带"合规风控排查安全，允许进入下一步审计"这类定性话。报告只用结构化字段和条数，
  存档前把这类句子删掉，免得被当成结论。
- 隐私（仓库公开）：法定代表人、负责人、联系方式不存；自然人股东写成"自然人股东A"。
- 每个工具的原始响应按"公司名 + 工具"缓存在 data/cache/qcc_agent/（git 忽略），重启、断网都不重复扣分。

配置（backend/.env）：
    XRAY_COMMERCIAL=qcc_agent
    QCC_AGENT_KEY=                 平台个人中心的 API Key；多个用逗号隔开，当前的失效或积分用完自动换下一个
    XRAY_QCC_MAX_POINTS=300        单次运行最多实际花多少积分（缓存命中不算）
"""
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app import config
from app.models import CompanyProfile, Coverage, Pledge, Penalty, RawRecord, Shareholder, Source
from app.sources.commercial import CST, _day, parse_money
from app.sources.licenses import normalize
from app.persistence import atomic_json, locked
from app.sources.cache import read_fresh
from app.sources.commercial import currency

BASE_URL = "https://agent.qcc.com/mcp"
SITE = "https://agent.qcc.com"
TITLE = "企查查智能体数据平台 · 工商登记、风险、股东"
NOTE = "第三方商业数据，由国家企业信用信息公示系统、法院公开信息等加工而来；有出入时以官方公示为准"

# 每个工具每次调用扣的积分（平台工具详情页标的价）
COST = {"get_company_registration_info": 3, "get_company_risk_scan": 5, "get_shareholder_info": 20,
        "get_branches": 5, "get_listing_info": 1, "get_administrative_penalty": 3, "get_judgment_debtor_info": 3,
        "get_dishonest_info": 3, "get_high_consumption_restriction": 3, "get_business_exception": 3,
        "get_serious_violation": 3, "get_equity_pledge_info": 3, "get_chattel_mortgage_info": 3,
        "get_tax_arrears_notice": 3, "get_financial_data": 5, "get_news_sentiment": 5}
# 风险扫描里的因子 → CompanyProfile 字段、明细工具
RISK = {"penalties": ("行政处罚", "get_administrative_penalty"),
        "executions": ("被执行人", "get_judgment_debtor_info"),
        "dishonest": ("失信信息", "get_dishonest_info"),
        "restricted": ("限制高消费", "get_high_consumption_restriction"),
        "abnormal": ("经营异常", "get_business_exception"),
        "serious_illegal": ("严重违法", "get_serious_violation"),
        "pledges": ("股权出质", "get_equity_pledge_info"),
        "mortgages": ("动产抵押", "get_chattel_mortgage_info"),
        "tax_arrears": ("欠税公告", "get_tax_arrears_notice")}
BASIC = ["name", "code", "status", "founded", "reg_capital", "paid_capital", "scope", "insured"]

# 这些字段整项不存：人名、联系方式
PERSONAL = re.compile(r"法定代表人|负责人|姓名|联系人|电话|邮箱|住址|身份证|邮政编码|通信地址|主要人员|董监高|高管")
META = {"企业名称", "摘要", "搜索结果", "关联分析", "提示", "检索关键字", "匹配结果"}
# 平台摘要里的定性话：不当结论用
JUDGING = re.compile(r"安全|允许|放心|清晰|无风险|可以继续|可继续|建议|良好|健康|正常经营")
ORG = re.compile(r"公司|合伙|中心|企业|集团|银行|基金|局|厅|委员会|政府|厂|社|所|院|会|部|店|有限|股份|控股|投资|管理|"
                 r"信托|保险|证券|资产|[A-Za-z]{3,}")
EMPTY = re.compile(r"未发现|没有发现|当前无|暂无|未查到|无相关")
DEAD = re.compile(r"注销|吊销|撤销|迁出")


class QccError(Exception):
    def __init__(self, message: str, switch: bool = False):
        super().__init__(message)
        self.switch = switch or bool(SWITCH.search(message))   # 换下一个 Key 再试


# 这几类错误是这个 Key 的问题（失效、积分用完、被限流），换个 Key 可能就好；查不到公司之类的不换
SWITCH = re.compile(r"积分|额度|余额|配额|quota|invalid_token|凭证|token|过期|频率|rate", re.I)


def parse_keys(text: str) -> list[str]:
    """QCC_AGENT_KEY 可以填多个，用逗号隔开；每个前面带不带 "Bearer " 都行。"""
    keys = [re.sub(r"(?i)^bearer\s+", "", k.strip()) for k in re.split(r"[,，;；\n]", text or "")]
    return list(dict.fromkeys(k for k in keys if k))


def parse_response(text: str) -> dict:
    """MCP 响应 → 工具返回的 JSON。SSE 取最后一个能解析的 data: 行。"""
    data = None
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
            except ValueError:
                continue
    if data is None:
        data = json.loads(text)
    if data.get("error"):
        raise QccError(str(data["error"].get("message") or data["error"]))
    result = data.get("result") or {}
    texts = [c.get("text") for c in result.get("content") or [] if c.get("type") == "text"]
    if result.get("isError"):
        raise QccError((texts[0] if texts else "工具返回错误")[:120])
    if not texts:
        return {}
    try:
        out = json.loads(texts[0])
    except ValueError:
        return {"文本": texts[0]}
    return out if isinstance(out, dict) else {"结果": out}


def is_person(name: str) -> bool:
    """股东、出质人是不是自然人：短、没有机构字样。"""
    name = (name or "").strip()
    return bool(re.fullmatch(r"自然人股东[A-Z0-9]*", name)) or (0 < len(name) <= 4 and not ORG.search(name))


def rows(payload: dict) -> list[dict]:
    for k, v in payload.items():
        if k not in META and isinstance(v, list) and all(isinstance(r, dict) for r in v):
            return v
    return []


def total(payload: dict) -> int:
    m = re.search(r"共(?:有)?\s*(\d+)\s*条", str(payload.get("摘要") or payload.get("搜索结果") or ""))
    return int(m.group(1)) if m else len(rows(payload))


def is_empty(payload: dict) -> bool:
    said = str(payload.get("摘要") or payload.get("搜索结果") or "")
    return not rows(payload) and bool(EMPTY.search(said))


def _plain_summary(s: str) -> str:
    """去掉摘要里的定性句，只留事实（有没有记录、多少条）。"""
    keep = [p for p in re.split(r"(?<=。)", s) if p.strip() and not JUDGING.search(p)]
    return "".join(keep).strip()


CLAUSE = re.compile(r"(?=[一二三四五六七八九十]+、)")
NAMED = re.compile(r"对([一-龥·]{2,5}?)(给予|处以|处|责令|采取|没收|罚款|警告)")


def scrub_text(text: str, company: str | None = None) -> str:
    """处罚结果这类原文里会点到个人："一、对公司……；二、对某某给予警告，并处罚款"。
    分条的只留讲到本公司的那几条；其余"对某某给予……"里的个人名字换成"相关个人"。"""
    parts = [x.strip() for x in CLAUSE.split(text or "") if x.strip()]
    if company and len(parts) > 1:
        mine = [x for x in parts if company in x]
        if mine:
            text = " ".join(mine)
    return NAMED.sub(lambda m: f"对相关个人{m.group(2)}" if is_person(m.group(1)) else m.group(0), text)


def clean(obj, people: dict[str, str] | None = None, company: str | None = None):
    """存档前清理：删个人信息和定性话，自然人改代号。people 记录真名到代号的对应，同一个人在各处用同一个代号。"""
    people = {} if people is None else people

    def alias(name: str) -> str:
        if name.startswith("自然人股东"):
            people[name] = name
            return name
        if name not in people:
            people[name] = f"自然人股东{chr(ord('A') + len(people))}" if len(people) < 26 else "自然人股东"
        return people[name]

    if isinstance(obj, list):
        return [clean(x, people, company) for x in obj]
    if isinstance(obj, str):
        return scrub_text(obj, company) if NAMED.search(obj) else obj
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if PERSONAL.search(k):
            continue
        if k in ("摘要", "搜索结果", "关联分析") and isinstance(v, str):
            v = _plain_summary(v)
            if not v:
                continue
        elif re.search(r"股东.*名称|^股东$|出质人|投资人", k) and isinstance(v, str) and is_person(v):
            v = alias(v)
        elif re.search(r"人(?:名称)?$", k) and isinstance(v, (str, list)):
            # 申请人、被申请人等是个人时不写名字（平台有时已打码成"华*"，一样换掉）
            person = lambda x: isinstance(x, str) and (is_person(x) or "*" in x)
            v = "自然人" if isinstance(v, str) and person(v) else                 [("自然人" if person(x) else x) for x in v] if isinstance(v, list) else v
        elif k in ("处罚结果", "处罚内容", "处罚事由", "违法事实") and isinstance(v, str):
            v = scrub_text(v, company)
        else:
            v = clean(v, people, company)
        out[k] = v
    return out


def _money_text(v) -> str:
    try:
        x = float(str(v).replace(",", ""))
    except ValueError:
        return str(v)
    return f"{x / 1e4:g} 万元" if x >= 1e4 else f"{x:g} 元"


def fact(rs: list[dict], n: int) -> str:
    """失信、限高、经营异常的一句话：最近一条的日期、机关、案号、金额，多条时注明共几条。"""
    r = max(rs, key=lambda r: _first(r, "发布日期", "立案日期", "列入日期"))
    when = _first(r, "发布日期", "立案日期", "列入日期")
    who = _first(r, "执行法院", "作出决定机关(列入)", "决定机关", "列入机关")
    what = "，".join(x for x in (_first(r, "案号"), _first(r, "涉案金额", "执行标的") and
                                 "涉案 " + _money_text(_first(r, "涉案金额", "执行标的")),
                                 _first(r, "列入经营异常名录原因", "列入原因", "列入严重违法失信企业名单原因")) if x)
    head = f"共 {n} 条，最近一条：" if n > 1 else ""
    return f"{head}{when} {who}{'，' + what if what else ''}".strip()


def _names(v) -> list[str]:
    return [str(x) for x in v if x] if isinstance(v, list) else [str(v)] if v else []


def _own_rows(fld: str, rs: list[dict], company: str) -> tuple[list[dict], list[dict]]:
    """股权出质：标的企业是它，才是它的股权被押出去；动产抵押：抵押人是它，才是它的东西被押出去。"""
    me = normalize(company)
    subject, creditor = ("标的企业", "质权人") if fld == "pledges" else ("抵押人", "抵押权人")
    own, theirs = [], []
    for r in rs:
        if r.get(subject):
            mine = any(normalize(x) == me for x in _names(r.get(subject)))
        else:
            mine = not any(normalize(x) == me for x in _names(r.get(creditor)))
        (own if mine else theirs).append(r)
    return own, theirs


def _pct(s) -> float:
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group(0)) if m else 0.0


def _first(row: dict, *keys: str) -> str:
    for k in keys:
        if row.get(k):
            return str(row[k])
    return ""


def _int(s) -> int | None:
    s = str(s or "").replace(",", "").strip()
    return int(s) if s.isdigit() else None


@dataclass
class Call:
    data: dict | None
    error: str | None
    cached: bool
    retrieved_at: str


@dataclass
class QccAgentResult:
    query: str
    retrieved_at: str
    profile: CompanyProfile | None
    content: dict                         # 清理过的各工具结果，进原始数据
    note: str
    failed: bool = False
    found: bool = True
    calls: list[str] = field(default_factory=list)

    @property
    def source(self) -> Source:
        return Source(id="registry", name=TITLE, kind="commercial", as_of=self.retrieved_at[:10], url=SITE, note=NOTE)

    def records(self) -> list[RawRecord]:
        cov = Coverage.found if self.profile else Coverage.failed if self.failed else Coverage.not_found
        out = [RawRecord(id="", source_id="registry", title=TITLE, kind="commercial", coverage=cov,
                         retrieved_at=self.retrieved_at, as_of=self.retrieved_at[:10], url=SITE,
                         content=self.content or None, note=self.note)]
        if self.profile:
            out.append(RawRecord(id="", source_id="annual_report", title="实缴资本、参保人数（企查查）", kind="commercial",
                                 coverage=Coverage.found, retrieved_at=self.retrieved_at, as_of=self.retrieved_at[:10],
                                 url=SITE, content={"实缴资本": self.profile.paid_capital, "参保人数": self.profile.insured},
                                 note="来自同一次企查查工商信息查询；企业可选择不公示"))
        return out


class QccAgentClient:
    def __init__(self, key: str | None = None, *, max_points: int | None = None, cache_dir=None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 30):
        # 多个 Key：一直用当前这个，失效、积分不够或被限流才换下一个（结果有缓存，轮流换不省积分）
        self.keys = parse_keys(key if key is not None else os.getenv("QCC_AGENT_KEY", ""))
        self.current, self.dropped = 0, {}   # dropped：第几个 Key → 为什么换掉
        self.max_points = max_points if max_points is not None else int(os.getenv("XRAY_QCC_MAX_POINTS", "300"))
        self.cache_dir = cache_dir or config.CACHE_DIR / "qcc_agent"
        self.transport, self.timeout, self.points = transport, timeout, 0
        self.provider = "qcc_agent"
        self._budget_lock = threading.Lock()
        self._key_lock = threading.Lock()
        self._reserved = 0
        self._cooldowns = {}

    @property
    def configured(self) -> bool:
        return bool(self.keys)

    def status(self) -> dict:
        return {"provider": self.provider, "configured": self.configured, "points": self.points,
                "max_points": self.max_points, "keys": len(self.keys), "using": self.current + 1,
                "budget_scope": "process", "dropped": {i + 1: why for i, why in self.dropped.items()}}

    def _path(self, name: str, tool: str):
        return self.cache_dir / (hashlib.sha256(f"{normalize(name)}|{tool}".encode()).hexdigest()[:24] + ".json")

    def _post(self, server: str, tool: str, name: str, key: str) -> dict:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": tool, "arguments": {"searchKey": name}}}
        with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
            r = c.post(f"{BASE_URL}/{server}/stream", json=payload,
                       headers={"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"})
        if r.status_code in (401, 402, 403, 429):
            raise QccError({401: "API Key 无效或过期", 402: "积分不足", 403: "没有权限", 429: "调用太频繁"}[r.status_code],
                           switch=True)
        r.raise_for_status()
        return parse_response(r.text)

    def _post_any(self, server: str, tool: str, name: str) -> dict:
        with self._key_lock:
            return self._post_keys(server, tool, name)

    def _post_keys(self, server: str, tool: str, name: str) -> dict:
        """从当前 Key 开始试；这个 Key 的问题就换下一个，都不行才报错。"""
        recovered = [i for i, until in self._cooldowns.items() if until <= time.monotonic()]
        if recovered and self.current >= len(self.keys):
            self.current = min(recovered)
        for i in recovered:
            self._cooldowns.pop(i, None)
            self.dropped.pop(i, None)
        while self.current < len(self.keys):
            if self.current in self.dropped:
                self.current += 1
                continue
            try:
                return self._post(server, tool, name, self.keys[self.current])
            except QccError as e:
                if not e.switch:
                    raise
                self.dropped[self.current] = str(e)[:60]
                if re.search(r"频繁|频率|rate|429", str(e), re.I):
                    self._cooldowns[self.current] = time.monotonic() + 60
                self.current += 1
        raise QccError(f"{len(self.keys)} 个 Key 都不能用（" +
                       "；".join(f"第 {i + 1} 个：{why}" for i, why in self.dropped.items()) + "）")

    def call(self, server: str, tool: str, name: str, *, force_refresh: bool = False) -> Call:
        path = self._path(name, tool)
        with locked(path):
            return self._call(server, tool, name, path, force_refresh)

    def _call(self, server, tool, name, path, force_refresh):
        saved = read_fresh(path, "data", force=force_refresh)
        if saved:
            data = clean(saved["data"], company=name)
            if data.get("企业名称") and normalize(data["企业名称"]) != normalize(name):
                return Call(None, "缓存的企业名称对不上，没有采用", True, saved["retrieved_at"])
            if data != saved["data"]:
                try:
                    atomic_json(path, {**saved, "data": data})
                except OSError:
                    pass
            return Call(data, None, True, saved["retrieved_at"])
        when = datetime.now(CST).isoformat(timespec="seconds")
        cost = COST.get(tool, 5)
        with self._budget_lock:
            if self.points + self._reserved + cost > self.max_points:
                return Call(None, f"服务进程已花 {self.points} 积分，到上限了，没有再查", False, when)
            self._reserved += cost
        try:
            data = self._post_any(server, tool, name)
            with self._budget_lock:
                self.points += cost
        except (httpx.HTTPError, ValueError, QccError) as e:
            return Call(None, f"查询失败：{e if isinstance(e, QccError) else type(e).__name__}", False, when)
        finally:
            with self._budget_lock:
                self._reserved -= cost
        if data.get("企业名称") and normalize(data["企业名称"]) != normalize(name):
            return Call(None, "返回的企业名称和输入对不上，没有采用", False, when)
        data = clean(data, company=name)
        try:
            atomic_json(path, {"query": name, "tool": tool, "retrieved_at": when, "data": data, "schema_version": 1})
        except OSError:
            pass
        return Call(data, None, False, when)

    def financials(self, name: str) -> Call:
        """财务数据（上市、发债等公开披露的公司才有）。解析在 app/sources/finance.py。"""
        return self.call("company", "get_financial_data", name)

    def news(self, name: str) -> Call:
        """新闻舆情，最近 30 条带情感倾向。解析在 app/sources/news.py。"""
        return self.call("operation", "get_news_sentiment", name)

    def fetch(self, name: str) -> QccAgentResult | None:
        try:
            return self._fetch(name)
        except (ValueError, TypeError, KeyError, AttributeError, OSError):
            return QccAgentResult(name, datetime.now(CST).isoformat(timespec="seconds"), None, {},
                                  "工商数据格式不完整或本地缓存不可用，本次未采用", failed=True)

    def _fetch(self, name: str) -> QccAgentResult | None:
        """没配置返回 None。工商信息查不到或名称对不上，就不再调别的工具（省积分）。"""
        if not self.configured:
            return None
        base = self.call("company", "get_company_registration_info", name)
        when, calls, cached = base.retrieved_at, ["工商信息"], [base.cached]
        if base.error:
            return QccAgentResult(name, when, None, {}, base.error, failed=True)
        reg = base.data or {}
        found = reg.get("企业名称")
        if not found:
            return QccAgentResult(name, when, None, clean(reg), "查了，没有这家公司的记录", found=False)
        if normalize(found) != normalize(name):
            return QccAgentResult(name, when, None, clean(reg),
                                  f"按名称查到的是\"{found}\"，和输入的名字对不上，没有采用。请输入公司全称再查", found=False)

        people: dict[str, str] = {}
        if not _day(reg.get("成立日期")) or parse_money(reg.get("注册资本")) is None:
            return QccAgentResult(name, when, None, clean(reg), "工商响应缺少有效成立日期或注册资本，未采用", failed=True)
        content: dict = {"工商信息": clean(reg, people, found)}
        fields = dict(name="企业名称", code="统一社会信用代码", status="登记状态", founded="成立日期",
                      reg_capital="注册资本", paid_capital="实缴资本", scope="经营范围", insured="参保人数")
        checked = [key for key, field in fields.items() if reg.get(field) not in (None, "")]
        p: dict = dict(name=found, code=reg.get("统一社会信用代码") or None, status=reg.get("登记状态") or "未知",
                       founded=_day(reg.get("成立日期")) or "", reg_capital=parse_money(reg.get("注册资本")) or 0.0,
                       paid_capital=parse_money(reg.get("实缴资本")), scope=reg.get("经营范围") or "",
                       capital_currency=currency(reg.get("注册资本")), paid_currency=currency(reg.get("实缴资本")),
                       insured=_int(reg.get("参保人数")), counts={})
        gaps = []

        scan = self.call("risk", "get_company_risk_scan", name)
        cached.append(scan.cached)
        if scan.error:
            gaps.append(f"风险扫描：{scan.error}")
        else:
            calls.append("风险扫描")
            factors = {f.get("风险因子"): f.get("条目数") for f in (scan.data or {}).get("风险因子扫描", [])}
            content["风险扫描"] = {k: v for k, v in factors.items()}
            p["risk_scan"] = {k: v for k, v in factors.items() if isinstance(k, str) and isinstance(v, int)}
            for fld, (factor, tool) in RISK.items():
                n = factors.get(factor)
                if type(n) is not int or n < 0:
                    continue
                checked.append(fld)
                p["counts"][fld] = n
                if n == 0:
                    if fld in ("abnormal", "serious_illegal", "dishonest", "restricted"):
                        p[fld] = False
                    continue
                if fld in ("abnormal", "serious_illegal", "dishonest", "restricted"):
                    p[fld] = True
                d = self.call("risk", tool, name)
                cached.append(d.cached)
                if d.error:
                    gaps.append(f"{factor}明细：{d.error}")
                    continue
                calls.append(factor)
                content[factor] = clean(d.data or {}, people, found)
                self._details(fld, d.data or {}, p, people, found)

        for label, tool, fld in (("股东", "get_shareholder_info", "shareholders"),
                                 ("分支机构", "get_branches", "branches"),
                                 ("上市信息", "get_listing_info", "listing")):
            c = self.call("company", tool, name)
            cached.append(c.cached)
            if c.error:
                gaps.append(f"{label}：{c.error}")
                continue
            calls.append(label)
            data = c.data or {}
            content[label] = clean(data, people, found)
            if not rows(data) and not is_empty(data) and not (fld == "listing" and self._listing(data)):
                gaps.append(f"{label}：响应未给出记录或明确的查无结果")
                continue
            checked.append(fld)
            if fld == "shareholders":
                p["shareholders"] = [Shareholder(name=self._alias(n, people) if is_person(n) else n,
                                                 type="自然人" if is_person(n) else "企业",
                                                 pct=_pct(r.get("持股比例") or r.get("出资比例")))
                                     for r in rows(data) if (n := _first(r, "股东名称", "股东", "投资人"))]
            elif fld == "branches":
                rs, n = rows(data), total(data)
                live = [r for r in rs if not DEAD.search(str(r.get("登记状态", "")))]
                p["branches"] = len(live) if rs and n <= len(rs) else n
            else:
                p["listing"] = None if is_empty(data) else self._listing(data)

        p["checked"] = [field for field in checked if field not in p.get("partial", [])]
        profile = CompanyProfile(**p)
        note = ("缓存（没有重复扣积分）" if all(cached) else f"实时查询，服务进程累计 {self.points} 积分") + \
               f"；查了：{'、'.join(calls)}" + (f"；没查成：{'；'.join(gaps)}" if gaps else "")
        return QccAgentResult(name, when, profile, content, note, calls=calls)

    @staticmethod
    def _alias(name: str, people: dict[str, str]) -> str:
        clean({"股东名称": name}, people)
        return people[name]

    def _details(self, fld: str, data: dict, p: dict, people: dict[str, str], company: str) -> None:
        raw_rows = rows(data)
        rs = rows(clean(data, people, company))
        if fld == "penalties":
            p["penalties"] = [Penalty(date=_day(_first(r, "处罚日期", "决定日期")) or _first(r, "处罚日期"),
                                      org=_first(r, "处罚单位", "处罚机关", "决定机关"),
                                      reason=_first(r, "处罚事由", "违法事实", "违法行为类型", "决定书文号"),
                                      result=_first(r, "处罚结果", "处罚内容")) for r in rs]
        elif fld in ("pledges", "mortgages"):
            # 平台把它当质权人、抵押权人（别人押给它，比如银行放贷）的记录也算进来了；只留押的是它自己的
            own, creditor = _own_rows(fld, raw_rows, company)
            shown = len(raw_rows) < max(total(data), p["counts"].get(fld, 0))
            p["counts"][fld] = len(own)
            if shown:
                p.setdefault("partial", []).append(fld)
            notes = []
            if creditor:
                notes.append(f"另有 {len(creditor)} 条是别人押给它（它是{'质权人' if fld == 'pledges' else '抵押权人'}），"
                             "不是它的风险")
            if shown:
                notes.append(f"共 {total(data)} 条，平台只给了前 {len(raw_rows)} 条明细，其余没核对")
            if notes:
                p.setdefault("facts", {})[fld] = "；".join(notes)
            if fld == "pledges":
                p["pledges"] = [Pledge(date=_day(_first(r, "登记日期", "公示日期")) or "",
                                       pledgor="、".join(self._alias(x, people) if is_person(x) else x
                                                        for x in _names(r.get("出质人"))),
                                       share=_first(r, "出质股权数额", "股权数额", "出质数额"),
                                       # 质权人是个人时不写名字（和原始数据里的处理一致）
                                       pledgee="、".join("自然人" if is_person(x) or "*" in x else x
                                                        for x in _names(r.get("质权人")))) for r in own]
            else:
                p["mortgages"] = clean(own, people, company)
        elif fld in ("executions", "tax_arrears"):
            p[fld] = rs
        elif (fld == "abnormal" and rs and len(rs) >= max(total(data), p["counts"].get(fld, 0))
              and all(_first(r, "移出日期") for r in rs)):
            p["abnormal"] = False            # 都已移出
        if fld in ("dishonest", "restricted", "abnormal", "serious_illegal") and rs:
            p.setdefault("facts", {})[fld] = fact(rs, total(data))



    @staticmethod
    def _listing(data: dict) -> dict:
        rs = rows(data)
        r = rs[0] if rs else {k: v for k, v in data.items() if k not in META}
        return {k: v for k, v in clean(r).items() if v not in ("", None)}
