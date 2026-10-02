"""中基协私募基金管理人公示详情页：管理规模区间、员工人数、实缴资本、诚信信息、提示信息、行政处罚。

公开页面，没有验证码。只在名单里查到它、并且有详情页地址时取一次；页面原样缓存在 data/cache/amac/，
断网时用缓存。页面结构是"标签一行、值一行"，按固定的小标题分段解析。
"""
import hashlib
import re
from datetime import datetime
from pathlib import Path

import httpx

FIELDS = ["登记编号", "登记时间", "成立时间", "注册资本(万元)(人民币)", "实缴资本(万元)(人民币)", "注册资本实缴比例",
          "机构类型", "业务类型", "全职员工人数", "取得基金从业人数", "管理规模区间", "机构信息最后更新时间", "当前会员类型"]
SECTIONS = ["机构诚信信息", "机构提示信息", "管理人最近一次重大事项变更", "基金业协会特别提示（针对私募基金管理人）", "机构信息"]
# 诚信信息里属于处罚、纪律处分、失联这类的小标题，判"有问题"
SERIOUS = re.compile(r"行政处罚|纪律处分|失联|异常机构|虚假|违反.{0,4}底线|不良诚信")


def _lines(html: str) -> list[str]:
    html = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    out = []
    for t in re.split(r"<[^>]+>", html):
        t = re.sub(r"\s+", " ", t.replace("&nbsp;", " ")).strip()
        if t:
            out.append(t)
    return out


def _section(lines: list[str], title: str) -> list[str]:
    """小标题之后到下一个小标题之前的行。小标题在页面上常连着出现两次（标签栏和表格），都跳过。"""
    try:
        i = lines.index(title)
    except ValueError:
        return []
    while i + 1 < len(lines) and lines[i + 1] == title:
        i += 1
    out = []
    for line in lines[i + 1:]:
        if line in SECTIONS:
            break
        out.append(line)
    return out


def _is_heading(line: str) -> bool:
    return len(line) <= 24 and not re.search(r"[。；;：:]$", line) and not line.startswith("指")


def parse(html: str) -> dict:
    lines = _lines(html)
    fields = {}
    for k in FIELDS:
        if k in lines:
            i = lines.index(k)
            if i + 1 < len(lines) and lines[i + 1] not in FIELDS:
                fields[k] = lines[i + 1]

    integrity: dict[str, list[str]] = {}
    current = None
    for line in _section(lines, "机构诚信信息"):
        if line in ("异常原因：", "异常原因:"):
            continue
        if _is_heading(line) and not line.endswith("）") or (current is None):
            current = line
            integrity.setdefault(current, [])
        else:
            integrity[current].append(line.rstrip("；;"))
    tips = [line for line in _section(lines, "机构提示信息") if _is_heading(line)]
    special = _section(lines, "基金业协会特别提示（针对私募基金管理人）")
    return {"fields": fields, "integrity": integrity, "tips": tips, "special": special}


def scale_upper(band: str | None) -> float | None:
    """"0-5亿元" → 5 亿；"100亿元以上" → None（没有上限）。"""
    m = re.match(r"\s*([\d.]+)\s*-\s*([\d.]+)\s*亿", band or "")
    return float(m.group(2)) * 1e8 if m else None


def summary(detail: dict) -> dict:
    """存进原始数据、给规则用的字段（中文键，原样可读）。"""
    f = detail.get("fields", {})
    out = {k: f[k] for k in FIELDS if k in f}
    if detail.get("integrity"):
        out["机构诚信信息"] = {k: v for k, v in detail["integrity"].items()}
    if detail.get("tips"):
        out["机构提示信息"] = detail["tips"]
    if detail.get("special"):
        out["协会特别提示"] = detail["special"]
    return out


class AmacDetailClient:
    def __init__(self, cache_dir: Path, transport: httpx.BaseTransport | None = None, timeout: float = 15):
        self.cache_dir, self.transport, self.timeout = Path(cache_dir), transport, timeout

    def _path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")

    def fetch(self, url: str) -> tuple[dict | None, str | None, bool]:
        """返回 (解析结果, 取得时间, 是否用的缓存)。网络和缓存都没有就返回 (None, None, False)。"""
        path = self._path(url)
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport,
                              headers={"User-Agent": "Mozilla/5.0 (X-Ray hackathon demo)"}) as c:
                r = c.get(url)
                r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.text, encoding="utf-8")
            return parse(r.text), datetime.now().isoformat(timespec="seconds"), False
        except (httpx.HTTPError, OSError):
            if path.exists():
                when = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
                return parse(path.read_text(encoding="utf-8")), when, True
            return None, None, False
