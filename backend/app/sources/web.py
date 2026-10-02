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
from urllib.parse import urlsplit

import httpx

from app import config
from app.sources.licenses import normalize
from app.persistence import atomic_json

OFFICIAL_DOMAINS = ["nfra.gov.cn", "csrc.gov.cn", "pbc.gov.cn", "samr.gov.cn", "court.gov.cn", "chinacourt.org",
                    "creditchina.gov.cn", "12315.cn", "zj.gov.cn", "hangzhou.gov.cn", "mps.gov.cn", "spp.gov.cn",
                    "chinatax.gov.cn", "mohrss.gov.cn", "mofcom.gov.cn", "amac.org.cn"]
# 商业数据网站：内容要授权，不用
AGGREGATORS = ["tianyancha.com", "qcc.com", "qixin.com", "aiqicha.baidu.com", "aiqicha.com", "qichacha.com", "xiniudata.com",
               "riskbird.com", "11467.com", "shuidi.cn"]
OFFICIAL_CATS = [
    ("penalty", "行政处罚 / 监管措施", re.compile(r"处罚|罚决|罚款|责令改正|监管措施|警示函|没收|吊销|取缔|通报批评")),
    ("warning", "风险提示 / 非法金融", re.compile(r"非法集资|非法金融|风险提示|不具备.{0,10}资质|涉嫌|黑名单|未经批准|冒用|假冒")),
    ("judicial", "法院文书", re.compile(r"法院|判决|裁定|被执行|破产|开庭|诉讼|仲裁")),
    ("license", "许可 / 批复", re.compile(r"批复|核准|许可|备案|准予|同意.{0,8}(设立|开业|变更)")),
]
# 权威媒体：中央和地方党报、通讯社、财经媒体、证监会指定的信息披露报刊。只搜这些网站
MEDIA_DOMAINS = ["people.com.cn", "xinhuanet.com", "news.cn", "cctv.com", "ce.cn", "chinanews.com.cn", "gmw.cn",
                 "chinadaily.com.cn", "thepaper.cn", "caixin.com", "yicai.com", "21jingji.com", "eeo.com.cn",
                 "jiemian.com", "stcn.com", "cs.com.cn", "cnstock.com", "zqrb.cn", "financialnews.com.cn",
                 "jjckb.cn", "zjol.com.cn", "hangzhou.com.cn"]
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
    excerpt: str           # 摘要里公司名前后的原文（出生日期、住址等个人信息已遮掉）
    by_short_name: bool = False  # 只匹配上了简称
    subject: bool = True   # 官方文件：它是文件的当事人（标题有全称、或抬头 / 当事人写的是它）；False 只是正文里提到
    dated: bool = False    # 日期取自页面上的发文日期；False 时是搜索引擎的收录日期，可能晚于发文


@dataclass
class WebFindings:
    searched: bool
    official: list[WebHit] = field(default_factory=list)
    news: list[WebHit] = field(default_factory=list)
    media: list[WebHit] = field(default_factory=list)   # 权威媒体的报道
    queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    replay: bool = False   # 用的是录下来的搜索结果


def _domain(url: str) -> str:
    try:
        parsed = urlsplit(url or "")
        return (parsed.hostname or "").lower() if parsed.scheme in ("https", "http") else ""
    except ValueError:
        return ""


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


# 页面上的发文日期。搜索引擎给的 datePublished 常常是收录日期（证监会页面实测差了快一年）
DOC_DATE_MS = re.compile(r"发文日期\s*(\d{13})")
DOC_DATE = re.compile(r"(?:发文|发布|成文)日期[:：]?\s*(\d{4})[-年./](\d{1,2})[-月./](\d{1,2})")
# 处罚决定书里常写当事人的出生年月和住址，存进案卷前遮掉
PERSONAL = [(re.compile(r"[男女][，,]\s*\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?\s*出生"), "（出生信息略）"),
            (re.compile(r"住址[:：][^，。；,;]{1,40}"), "住址：略"),
            (re.compile(r"身份证(?:号码?)?[:：]?\s*\d{6}[\d*]{8,11}[\dXx*]"), "身份证：略"),
            # 法定代表人、实控人的名字（爱企查摘要、媒体报道里常见）。名字按 2~3 个汉字算；
            # 后面紧跟"变更、的、信息……"这类词的不是名字，不动
            (re.compile(r"(法定代表人|法人代表|实际控制人|实控人)(\s*(?:为|是|[:：])?\s*)"
                        r"(?!变更|的|及|和|等|签|身份|职|信息|人|均|都|未|不|已|由|之|与|认定)[一-龥·]{2,3}"),
             r"\1\2（姓名略）"),
            # 处罚决定书里"某某某，男，19xx 年出生"：出生信息先遮掉，前面的名字跟着换
            (re.compile(r"[一-龥·]{2,3}(?=[，,]\s*（出生信息略）)"), "相关个人")]
# 标题括号里列的当事人："行政处罚决定书（巨鲸财富、某某某）"
PAREN = re.compile(r"[（(]([^（）()]{1,40})[）)]")
NAME_ONLY = re.compile(r"^[一-龥·]{2,4}$")
ORGISH = re.compile(r"公司|合伙|中心|企业|集团|银行|基金|局|厅|委员会|政府|证券|资产|财富|投资|管理|控股|股份|系")


def scrub_title(title: str, company: str) -> str:
    """标题括号里的人名换成"相关个人"；公司简称（出现在全称里）、机构名保留。"""
    def fix(m: re.Match) -> str:
        parts = re.split(r"([、，,；;])", m.group(1))
        keep = [p if i % 2 or not NAME_ONLY.match(p.strip()) or ORGISH.search(p) or p.strip() in company
                else "相关个人" for i, p in enumerate(parts)]
        return m.group(0)[0] + "".join(keep) + m.group(0)[-1]
    return redact(PAREN.sub(fix, title or ""))


def doc_date(text: str) -> str | None:
    m = DOC_DATE_MS.search(text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000).strftime("%Y-%m-%d")
    m = DOC_DATE.search(text)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def redact(text: str) -> str:
    for pattern, repl in PERSONAL:
        text = pattern.sub(repl, text)
    return text


def is_subject(title: str, text: str, name: str) -> bool:
    """官方文件是不是冲着它来的：标题有全称，或者抬头 / 当事人写的是它。只在正文里提到的不算。"""
    flat, n = re.sub(r"\s+", "", text), normalize(name)
    return n in normalize(title) or re.search(rf"(当事人[:：]|^|[。；，,]){re.escape(n)}[（(:：]", flat) is not None


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
                try:
                    atomic_json(path, {"params": params, "recorded_at": datetime.now().isoformat(timespec="seconds"),
                                       "pages": pages})
                except OSError:
                    pass
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

    def _find(self, name: str, kinds: tuple[str, ...]) -> WebFindings:
        out = WebFindings(searched=True)
        short = short_name(name)
        jobs = {"official": (name, OFFICIAL_DOMAINS, None),
                "news": (f"{short or name} 投诉 维权 兑付", None, AGGREGATORS),
                "media": (short or name, MEDIA_DOMAINS, None)}
        jobs = {k: jobs[k] for k in kinds}
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {k: pool.submit(self.search, q, inc, exc) for k, (q, inc, exc) in jobs.items()}
            for k, (q, _, _) in jobs.items():
                out.queries.append(q)
                try:
                    pages, replay = futures[k].result()
                except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError) as e:
                    out.errors.append(f"{'官方网站' if k == 'official' else '权威媒体' if k == 'media' else '公开报道'}搜索失败：{type(e).__name__}")
                    continue
                out.replay = out.replay or replay
                seen = set()
                for p in pages:
                    domain = _domain(p["url"])
                    excerpt = _excerpt(p["text"], name)
                    by_short = False
                    if not excerpt and k != "official" and short:  # 官方文件必须有全称；报道可以用简称
                        excerpt, by_short = _excerpt(p["text"], short), True
                    if not excerpt or p["url"] in seen or _matches(domain, AGGREGATORS):
                        continue
                    seen.add(p["url"])
                    official = _matches(domain, OFFICIAL_DOMAINS) or domain.endswith(".gov.cn")
                    if k == "official" and not official:
                        continue
                    if k == "media" and not _matches(domain, MEDIA_DOMAINS):
                        continue
                    if k != "official" and official:
                        continue  # 官方页面由第一路搜索负责
                    cats = OFFICIAL_CATS if official else OFFICIAL_CATS[:2] + NEWS_CATS if k == "media" else NEWS_CATS
                    cat, label = _classify(p["name"] + excerpt, cats)
                    found = doc_date(p["text"])
                    hit = WebHit(cat, label, official, scrub_title(p["name"], name), p["url"], p["site"] or domain, found or p["date"],
                                 # 风险提示点名的公司多写在正文里，提到就算点名；处罚、法院文书要它是当事人
                                 scrub_title(excerpt, name), by_short,
                                 # 媒体报道：标题里有它的名字才算"写的是它"（同一实控人的兄弟公司常被一起报道）
                                 subject=(normalize(name) in normalize(p["name"]) or bool(short and short in p["name"]))
                                 if k == "media" else
                                 not official or cat == "warning" or is_subject(p["name"], p["text"], name),
                                 dated=found is not None)
                    (out.official if k == "official" else out.media if k == "media" else out.news).append(hit)
        return out

    def find_official(self, name: str) -> WebFindings:
        """只搜监管、法院、政府网站。"""
        return self._find(name, ("official",))

    def find_complaints(self, name: str) -> WebFindings:
        """全网搜"简称 + 投诉 维权 兑付"：网上的投诉和维权帖、报道。"""
        return self._find(name, ("news",))

    def find_media(self, name: str) -> WebFindings:
        """只搜权威媒体网站（人民网、新华网、财新、证券时报……）上提到它的报道。"""
        return self._find(name, ("media",))

    def findings(self, name: str) -> WebFindings:
        return self._find(name, ("official", "news"))
