"""巨潮资讯网（www.cninfo.com.cn，证监会指定的上市公司信息披露网站）：公告列表和年报原文。

- 免费、不用 Key、没有验证码；只对上市公司有用。股票代码取企查查上市信息里的，没有就不查。
- 取两样：最新年度报告（PDF 原文链接，财务数字"以公告原文为准"指向它），最近一年的公告里
  标题带处罚、立案、诉讼、问询这类字样的（标题原样，分类靠关键词）。
- 结果缓存在 data/cache/cninfo/，断网或 XRAY_LLM_MODE=replay 时回放；XRAY_CNINFO=0 时不查（测试默认关）。
"""
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

BASE = "http://www.cninfo.com.cn"
STATIC = "http://static.cninfo.com.cn/"
HEADERS = {"User-Agent": "Mozilla/5.0 (X-Ray research; public disclosures)", "X-Requested-With": "XMLHttpRequest"}
COLUMN = {"6": "sse", "9": "sse", "0": "szse", "3": "szse", "4": "third", "8": "third"}   # 代码首位 → 交易所
CATEGORY_ANNUAL = {"sse": "category_ndbg_szsh;", "szse": "category_ndbg_szsh;", "third": "category_ndbg_szsh;"}
FRESH = 24 * 3600   # 一天内查过就直接用缓存：公告一天更新不了几条，现场不必再等 10 多秒
RISKY = [("penalty", "处罚、监管措施", re.compile(r"处罚|监管措施|警示函|责令改正|立案|调查|纪律处分|通报批评|公开谴责")),
         ("lawsuit", "诉讼、仲裁", re.compile(r"诉讼|仲裁|判决|冻结")),
         ("inquiry", "问询、风险提示", re.compile(r"问询|关注函|风险提示|退市|无法表示意见|保留意见"))]


@dataclass
class Notice:
    date: str
    title: str
    url: str
    category: str = ""
    category_label: str = ""


@dataclass
class CninfoFindings:
    coverage: str                      # found / not_found / failed / not_covered
    code: str | None = None
    annual: Notice | None = None       # 最新年度报告（不含摘要）
    risky: list[Notice] = field(default_factory=list)   # 最近一年标题带风险字样的
    total: int = 0                     # 最近一年的公告总数
    scanned: int = 0                   # 实际看了几条标题（一次最多 100 条）
    error: str | None = None
    replay: bool = False


class CninfoClient:
    def __init__(self, cache_dir: Path, mode: str = "live", transport: httpx.BaseTransport | None = None,
                 timeout: float = 12):
        self.cache_dir, self.mode, self.transport, self.timeout = cache_dir, mode, transport, timeout

    def _post(self, path: str, form: dict) -> tuple[object, bool]:
        key = hashlib.sha256(json.dumps([path, form], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
        cached = self.cache_dir / f"{key}.json"
        fresh = cached.exists() and time.time() - cached.stat().st_mtime < FRESH
        if self.mode != "replay" and not fresh:
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport, headers=HEADERS) as c:
                    r = c.post(BASE + path, data=form)
                r.raise_for_status()
                data = r.json()
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps({"form": form, "recorded_at": datetime.now().isoformat(timespec="seconds"),
                                              "data": data}, ensure_ascii=False), encoding="utf-8")
                return data, False
            except (httpx.HTTPError, ValueError):
                if not cached.exists():
                    raise
        elif fresh and self.mode != "replay":
            return json.loads(cached.read_text(encoding="utf-8"))["data"], False
        if not cached.exists():
            raise ValueError("没有录好的巨潮结果")
        return json.loads(cached.read_text(encoding="utf-8"))["data"], True

    def _org(self, code: str) -> tuple[str | None, bool]:
        data, replay = self._post("/new/information/topSearch/query", {"keyWord": code, "maxNum": 5})
        hit = next((x for x in data or [] if x.get("code") == code), None)
        return (hit or {}).get("orgId"), replay

    def _list(self, code: str, org: str, category: str, size: int, since: str = "", until: str = "",
              page: int = 1) -> tuple[dict, bool]:
        form = {"stock": f"{code},{org}", "tabName": "fulltext", "pageSize": size, "pageNum": page,
                "column": COLUMN.get(code[0], "szse"), "category": category, "plate": "", "seDate": f"{since}~{until}" if since else "",
                "searchkey": "", "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true"}
        return self._post("/new/hisAnnouncement/query", form)

    @staticmethod
    def _notice(a: dict) -> Notice:
        when = time.strftime("%Y-%m-%d", time.localtime((a.get("announcementTime") or 0) / 1000))
        title = re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "")
        return Notice(when, title, STATIC + (a.get("adjunctUrl") or ""))

    def find(self, code: str | None, today: date) -> CninfoFindings:
        if not code or not re.fullmatch(r"\d{6}", code):
            return CninfoFindings("not_covered", code, error="不是上市公司，或没拿到股票代码")
        try:
            org, replay = self._org(code)
            if not org:
                return CninfoFindings("not_found", code)
            annual_data, r1 = self._list(code, org, CATEGORY_ANNUAL.get(COLUMN.get(code[0], "szse")), 6)
            # 一页最多 30 条；最近一年的公告最多看 4 页（120 条）
            window = ((today - timedelta(days=365)).isoformat(), today.isoformat())
            recent_data, r2 = self._list(code, org, "", 30, *window)
            listed = list(recent_data.get("announcements") or [])
            page, total = 1, int(recent_data.get("totalAnnouncement") or 0)
            while len(listed) < total and page < 4:
                page += 1
                more, r3 = self._list(code, org, "", 30, *window, page=page)
                r2 = r2 or r3
                if not more.get("announcements"):
                    break
                listed += more["announcements"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            return CninfoFindings("failed", code, error=type(e).__name__)
        annual = next((self._notice(a) for a in annual_data.get("announcements") or []
                       if "摘要" not in (a.get("announcementTitle") or "") and "英文" not in (a.get("announcementTitle") or "")),
                      None)
        since = (today - timedelta(days=365)).isoformat()
        risky = []
        for a in listed:
            n = self._notice(a)
            if n.date < since:
                continue
            for cat, label, pattern in RISKY:
                if pattern.search(n.title):
                    n.category, n.category_label = cat, label
                    risky.append(n)
                    break
        return CninfoFindings("found", code, annual, risky, total,
                              scanned=len(listed), replay=replay or r1 or r2)
