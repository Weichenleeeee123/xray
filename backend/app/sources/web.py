"""联网查证：用比赛网关的搜索（博查为主，UniFuncs 兜底）按公司名查两类公开信息。

1. 官方文件：只搜监管、法院、地方政府网站，找点名这家公司的处罚、监管措施、风险提示、判决。
2. 公开报道和投诉：全网搜"公司名 + 投诉/维权/兑付"，看口碑。

规矩：
- 只留正文摘要里真出现公司全称的结果，同名、简称、无关页面一律丢掉。
- 不碰天眼查、企查查这类商业数据网站（要授权）；不读要登录、有验证码的页面。
- 分类（处罚 / 风险提示 / 司法 / 许可 / 投诉 / 兑付问题）用关键词，确定性的，不让模型判断。
- 每次搜索都缓存到 data/cache/web/，断网时回放；XRAY_LLM_MODE=off 时不联网。
- 搜不到只说明"没搜到"，不等于没有。
"""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from app import config
from app.sources.licenses import normalize

OFFICIAL_DOMAINS = ["nfra.gov.cn", "csrc.gov.cn", "pbc.gov.cn", "samr.gov.cn", "court.gov.cn", "chinacourt.org",
                    "creditchina.gov.cn", "12315.cn", "zj.gov.cn", "hangzhou.gov.cn", "mps.gov.cn", "spp.gov.cn",
                    "chinatax.gov.cn", "mohrss.gov.cn", "mofcom.gov.cn", "amac.org.cn"]
# 商业数据网站：内容要授权，不用
AGGREGATORS = ["tianyancha.com", "qcc.com", "qixin.com", "aiqicha.baidu.com", "qichacha.com", "xiniudata.com",
               "riskbird.com", "11467.com", "shuidi.cn"]
OFFICIAL_CATS = [
    ("penalty", "行政处罚 / 监管措施", re.compile(r"处罚|罚决|罚款|责令改正|监管措施|警示函|没收|吊销|取缔|通报批评")),
    ("warning", "风险提示 / 非法金融", re.compile(r"非法集资|非法金融|风险提示|不具备.{0,10}资质|涉嫌|黑名单|未经批准|冒用|假冒")),
    ("judicial", "法院文书", re.compile(r"法院|判决|裁定|被执行|破产|开庭|诉讼|仲裁")),
    ("license", "许可 / 批复", re.compile(r"批复|核准|许可|备案|准予|同意.{0,8}(设立|开业|变更)")),
]
NEWS_CATS = [
    # 不用"逾期""拖欠"：银行起诉逾期借款人这类文章会被误判成"它兑付不了"
    ("cash", "兑付 / 提现 / 跑路", re.compile(r"兑付|提现难|提不了现|无法提现|取不出|无法赎回|跑路|失联|爆雷|暴雷|"
                                          r"退款难|退不了|退费难|关门|闭店")),
    ("complaint", "投诉 / 维权", re.compile(r"投诉|维权|举报|报警|立案|被骗|上当")),
]


@dataclass
class WebHit:
    category: str          # penalty / warning / judicial / license / other，或 cash / complaint / other
    category_label: str
    official: bool
    title: str
    url: str
    site: str
    date: str | None
    excerpt: str           # 摘要里公司名前后的原文
    by_short_name: bool = False  # 只匹配上了简称


@dataclass
class WebFindings:
    searched: bool
    official: list[WebHit] = field(default_factory=list)
    news: list[WebHit] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    replay: bool = False   # 用的是录下来的搜索结果


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _matches(domain: str, suffixes: list[str]) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in suffixes)


COMPANY_SUFFIX = re.compile(r"(集团)?(股份有限公司|有限责任公司|有限公司|股份公司|集团公司)$")


def short_name(name: str) -> str | None:
    """"杭州银行股份有限公司" → "杭州银行"。新闻和投诉多用简称；太短的不用，免得误配。"""
    s = COMPANY_SUFFIX.sub("", normalize(name))
    return s if len(s) >= 4 and s != normalize(name) else None


def _excerpt(text: str, name: str, width: int = 70) -> str | None:
    flat = re.sub(r"\s+", "", text)
    i = flat.find(normalize(name))
    if i < 0:
        return None
    return flat[max(0, i - width): i + len(normalize(name)) + width * 2]


def _classify(text: str, cats) -> tuple[str, str]:
    for key, label, pattern in cats:
        if pattern.search(text):
            return key, label
    return "other", "其他提及"


class WebClient:
    def __init__(self, base_url: str = config.LLM_BASE_URL, api_key: str = config.LLM_API_KEY,
                 mode: str = config.LLM_MODE, cache_dir: Path = config.CACHE_DIR / "web",
                 transport: httpx.BaseTransport | None = None, timeout: float = 25):
        self.root = re.sub(r"/v1/?$", "", base_url or "")
        self.api_key, self.mode, self.cache_dir, self.transport, self.timeout = api_key, mode, cache_dir, transport, timeout

    @property
    def configured(self) -> bool:
        return bool(self.root and self.api_key) and self.mode != "off"

    def _cached(self, kind: str, params: dict, fetch) -> tuple[list[dict], bool]:
        key = hashlib.sha256(json.dumps([kind, params], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
        path = self.cache_dir / f"{key}.json"
        if self.mode != "replay":
            try:
                pages = fetch()
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"params": params, "recorded_at": datetime.now().isoformat(timespec="seconds"),
                                            "pages": pages}, ensure_ascii=False), encoding="utf-8")
                return pages, False
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                if not path.exists():
                    raise
        if not path.exists():
            raise ValueError("没有录好的搜索结果")
        return json.loads(path.read_text(encoding="utf-8"))["pages"], True

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
            r = c.post(self.root + path, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        return r.json()

    def search(self, query: str, include: list[str] | None = None, exclude: list[str] | None = None,
               count: int = 20) -> tuple[list[dict], bool]:
        """返回 (网页列表, 是否回放)。网页字段统一成 name / url / site / date / text。"""
        params = {"query": query, "include": include, "exclude": exclude, "count": count}

        def fetch() -> list[dict]:
            body = {"query": query, "summary": True, "count": count, "freshness": "noLimit"}
            if include:
                body["include"] = "|".join(include)
            if exclude:
                body["exclude"] = "|".join(exclude)
            try:
                pages = self._post("/bocha/v1/web-search", body)["data"]["webPages"]["value"]
            except (httpx.HTTPError, KeyError, TypeError):
                if include:
                    raise  # UniFuncs 不支持限定域名，官方搜索不降级
                pages = self._post("/unifuncs/web-search", {"query": query, "count": count})["data"]["webPages"]
            return [{"name": p.get("name") or "", "url": p.get("url") or "", "site": p.get("siteName") or "",
                     "date": (p.get("datePublished") or "")[:10] or None,
                     "text": " ".join(filter(None, [p.get("name"), p.get("summary"), p.get("snippet")]))} for p in pages]

        return self._cached("search", params, fetch)

    def findings(self, name: str) -> WebFindings:
        out = WebFindings(searched=True)
        short = short_name(name)
        jobs = {"official": (name, OFFICIAL_DOMAINS, None),
                "news": (f"{short or name} 投诉 维权 兑付", None, AGGREGATORS)}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {k: pool.submit(self.search, q, inc, exc) for k, (q, inc, exc) in jobs.items()}
            for k, (q, _, _) in jobs.items():
                out.queries.append(q)
                try:
                    pages, replay = futures[k].result()
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
                    out.errors.append(f"{'官方网站' if k == 'official' else '公开报道'}搜索失败：{type(e).__name__}")
                    continue
                out.replay = out.replay or replay
                seen = set()
                for p in pages:
                    domain = _domain(p["url"])
                    excerpt = _excerpt(p["text"], name)
                    by_short = False
                    if not excerpt and k == "news" and short:  # 官方文件必须有全称；报道可以用简称
                        excerpt, by_short = _excerpt(p["text"], short), True
                    if not excerpt or p["url"] in seen or _matches(domain, AGGREGATORS):
                        continue
                    seen.add(p["url"])
                    official = _matches(domain, OFFICIAL_DOMAINS) or domain.endswith(".gov.cn")
                    if k == "news" and official:
                        continue  # 官方页面由第一路搜索负责
                    cat, label = _classify(p["name"] + excerpt, OFFICIAL_CATS if official else NEWS_CATS)
                    hit = WebHit(cat, label, official, p["name"], p["url"], p["site"] or domain, p["date"], excerpt,
                                 by_short)
                    (out.official if k == "official" else out.news).append(hit)
        return out
