"""商业数据接口：企查查 / 天眼查开放平台的企业工商信息。任意一家公司都能查，但这是第三方加工的数据。

- 来源类型标 commercial，界面角标写"商业数据"，不冒充官方记录。
- 每次调用都花钱：结果按公司名缓存在 data/cache/commercial/，重启也不重复调用；单次运行有调用上限。
- 查回来的公司名和输入对不上时不采用（防止同名、简称张冠李戴），原始响应照样留档。
- 只取基本工商信息。这个接口不含处罚、出质、被执行等字段，这些项会显示"没查"，不当作"无"。

配置（backend/.env）：
    XRAY_COMMERCIAL=qcc 或 tianyancha（不填就不用）
    QCC_APP_KEY、QCC_SECRET_KEY          企查查
    TIANYANCHA_TOKEN                     天眼查
    XRAY_COMMERCIAL_MAX_CALLS=30         单次运行最多调用几次
"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

from app import config
from app.models import CompanyProfile, Coverage, RawRecord, Source
from app.sources.licenses import normalize

CST = timezone(timedelta(hours=8))
QCC_URL = "https://api.qichacha.com/ECIV4/GetBasicDetailsByName"
TYC_URL = "http://open.api.tianyancha.com/services/open/ic/baseinfo/normal"
TITLES = {"qcc": "企查查开放平台 · 企业工商信息", "tianyancha": "天眼查开放平台 · 企业基本信息"}
SITES = {"qcc": "https://openapi.qcc.com", "tianyancha": "https://open.tianyancha.com"}
# 这个接口给了哪些字段；其余字段（处罚、出质、被执行……）没查
CHECKED = ["name", "code", "status", "founded", "reg_capital", "paid_capital", "scope", "insured"]


def parse_money(text) -> float | None:
    """"5000万元人民币" → 50000000；"1.2亿" → 120000000；数字原样。外币不换算，原样按数字给（报告里会带原文）。"""
    if text is None or text == "":
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(亿|万)?", str(text).replace(",", ""))
    if not m:
        return None
    return float(m.group(1)) * {"亿": 1e8, "万": 1e4}.get(m.group(2), 1.0)


def _day(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # 天眼查给毫秒时间戳
        return datetime.fromtimestamp(value / 1000, CST).date().isoformat()
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return m.group(0) if m else None


def to_profile(provider: str, r: dict) -> CompanyProfile | None:
    """把接口返回的一家公司映射成 CompanyProfile；缺关键字段就不映射。"""
    if provider == "qcc":
        name, code, status = r.get("Name"), r.get("CreditCode"), r.get("Status")
        founded, scope = _day(r.get("StartDate")), r.get("Scope") or ""
        reg, paid, insured = parse_money(r.get("RegistCapi")), parse_money(r.get("RecCap")), None
    else:
        name, code, status = r.get("name"), r.get("creditCode"), r.get("regStatus")
        founded = _day(r.get("estiblishTime") or r.get("establishTime"))
        scope = r.get("businessScope") or ""
        reg, paid = parse_money(r.get("regCapital")), parse_money(r.get("actualCapital"))
        insured = r.get("socialStaffNum") if isinstance(r.get("socialStaffNum"), int) else None
    if not name or not founded or reg is None:
        return None
    return CompanyProfile(name=name, code=code, status=status or "未知", founded=founded, reg_capital=reg,
                          paid_capital=paid, scope=scope, insured=insured, checked=list(CHECKED))


@dataclass
class CommercialResult:
    provider: str
    query: str
    retrieved_at: str
    response: dict                       # 原始响应，原样留档
    record: dict | None                  # 响应里的那家公司
    profile: CompanyProfile | None       # 名称对得上才有
    note: str
    cached: bool

    @property
    def source(self) -> Source:
        return Source(id="registry", name=TITLES[self.provider], kind="commercial", as_of=self.retrieved_at[:10],
                      url=SITES[self.provider], note="第三方商业数据，由工商公示等公开信息加工而来；有出入时以官方公示为准")


    def records(self) -> list[RawRecord]:
        src = self.source
        cov = Coverage.found if self.profile else (Coverage.failed if not self.response else Coverage.not_found)
        out = [RawRecord(id="", source_id="registry", title=src.name, kind="commercial", coverage=cov,
                         retrieved_at=self.retrieved_at, as_of=self.retrieved_at[:10], url=src.url,
                         content=self.record or self.response or None, note=self.note)]
        if self.profile:
            out.append(RawRecord(id="", source_id="annual_report", title="实缴资本、参保人数（商业接口）", kind="commercial",
                                 coverage=Coverage.found, retrieved_at=self.retrieved_at, url=src.url,
                                 content={"paid_capital": self.profile.paid_capital, "insured": self.profile.insured},
                                 note="来自同一次商业接口查询"))
        return out


class CommercialClient:
    def __init__(self, provider: str = os.getenv("XRAY_COMMERCIAL", ""), *,
                 qcc_key: str = os.getenv("QCC_APP_KEY", ""), qcc_secret: str = os.getenv("QCC_SECRET_KEY", ""),
                 tyc_token: str = os.getenv("TIANYANCHA_TOKEN", ""),
                 max_calls: int = int(os.getenv("XRAY_COMMERCIAL_MAX_CALLS", "30")),
                 cache_dir: Path = config.CACHE_DIR / "commercial", transport: httpx.BaseTransport | None = None):
        self.provider = provider.strip().lower()
        self.qcc_key, self.qcc_secret, self.tyc_token = qcc_key, qcc_secret, tyc_token
        self.max_calls, self.calls, self.cache_dir, self.transport = max_calls, 0, cache_dir, transport

    @property
    def configured(self) -> bool:
        return (self.provider == "qcc" and bool(self.qcc_key and self.qcc_secret)) or \
               (self.provider == "tianyancha" and bool(self.tyc_token))

    def status(self) -> dict:
        return {"provider": self.provider or None, "configured": self.configured, "calls": self.calls,
                "max_calls": self.max_calls}

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / self.provider / (hashlib.sha256(normalize(name).encode()).hexdigest()[:24] + ".json")

    def _request(self, name: str) -> dict:
        with httpx.Client(timeout=20, transport=self.transport) as client:
            if self.provider == "qcc":
                ts = str(int(time.time()))
                token = hashlib.md5((self.qcc_key + ts + self.qcc_secret).encode()).hexdigest().upper()
                r = client.get(QCC_URL, params={"key": self.qcc_key, "keyword": name},
                               headers={"Token": token, "Timespan": ts})
            else:
                r = client.get(TYC_URL, params={"keyword": name}, headers={"Authorization": self.tyc_token})
        r.raise_for_status()
        return r.json()

    def _record(self, response: dict) -> dict | None:
        if self.provider == "qcc":
            return response.get("Result") if str(response.get("Status")) == "200" else None
        return response.get("result") if response.get("error_code") == 0 else None

    def fetch(self, name: str) -> CommercialResult | None:
        """没配置返回 None；配置了但失败，返回带说明的结果（记一条"查询失败"，不中断分析）。"""
        if not self.configured:
            return None
        path, cached = self._cache_path(name), True
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            response, retrieved = saved["response"], saved["retrieved_at"]
        else:
            if self.calls >= self.max_calls:
                return CommercialResult(self.provider, name, datetime.now(CST).isoformat(timespec="seconds"), {}, None,
                                        None, f"本次运行已调用 {self.calls} 次，到上限了，没有再查", False)
            self.calls += 1
            retrieved, cached = datetime.now(CST).isoformat(timespec="seconds"), False
            try:
                response = self._request(name)
            except (httpx.HTTPError, ValueError) as e:
                return CommercialResult(self.provider, name, retrieved, {}, None, None,
                                        f"查询失败：{type(e).__name__}", False)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"query": name, "retrieved_at": retrieved, "response": response},
                                       ensure_ascii=False), encoding="utf-8")
        record = self._record(response)
        if record is None:
            return CommercialResult(self.provider, name, retrieved, response, None, None, "查了，没有这家公司的记录", cached)
        profile = to_profile(self.provider, record)
        if profile and normalize(profile.name) != normalize(name):
            return CommercialResult(self.provider, name, retrieved, response, record, None,
                                    f"按名称查到的是\"{profile.name}\"，和输入的名字对不上，没有采用。请输入公司全称再查", cached)
        note = "缓存（没有重复计费）" if cached else "实时查询"
        return CommercialResult(self.provider, name, retrieved, response, record, profile, note, cached)
