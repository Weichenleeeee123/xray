"""证据包：人工采集的真实记录（公示系统、中基协、投诉平台等有验证码或接口不通的来源）。

一家公司一个文件：data/evidence_packs/<公司全称>.json，格式见同目录 _template.json 和 README.md。
每一段都带来源说明（谁发布、网址、采集时间、截图），读进来后来源类型是 collected。
以下划线开头的文件不读。
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import EVIDENCE_DIR
from app.models import Source
from app.sources.licenses import normalize

# 证据包每一段对应的来源 id 和默认名称
SECTIONS = {
    "registry": "国家企业信用信息公示系统 · 登记信息",
    "annual_report": "国家企业信用信息公示系统 · 年度报告",
    "amac": "中国证券投资基金业协会 · 私募基金管理人公示",
    "complaints": "投诉平台与新闻（人工摘录）",
}


@dataclass
class Section:
    source: Source
    retrieved_at: str
    screenshot: str | None
    data: Any
    title: str | None = None


def _section(sid: str, raw: dict, pack: dict) -> Section:
    meta = raw.get("source", {})
    retrieved = meta.get("retrieved_at") or pack.get("as_of", "")
    source = Source(id=sid, name=meta.get("name") or SECTIONS.get(sid, sid), kind="collected",
                    as_of=meta.get("as_of") or retrieved[:10] or None, url=meta.get("url"),
                    note=meta.get("note") or f"人工采集，{pack.get('collected_by') or '采集人未填'}")
    return Section(source=source, retrieved_at=retrieved, screenshot=meta.get("screenshot"),
                   data=raw.get("data", raw.get("text")), title=raw.get("title"))


@dataclass
class Pack:
    company: str
    note: str | None
    as_of: str
    sections: dict[str, Section]
    self_description: list[Section]
    extra: list[Section]


def parse_pack(raw: dict) -> Pack:
    sections = {sid: _section(sid, raw[sid], raw) for sid in SECTIONS if raw.get(sid)}
    selfs = [_section("self_description", s, raw) for s in raw.get("self_description", [])]
    for s in selfs:
        s.source.kind = "web"
    extra = [_section(s.get("source_id", "extra"), s, raw) for s in raw.get("extra", [])]
    return Pack(company=raw["company"], note=raw.get("note"), as_of=raw.get("as_of", ""),
                sections=sections, self_description=selfs, extra=extra)


class EvidencePacks:
    def __init__(self, packs: list[dict]):
        self._by_name: dict[str, dict] = {}
        for raw in packs:
            for name in [raw["company"], *raw.get("aliases", [])]:
                self._by_name[normalize(name)] = raw

    @classmethod
    def load(cls, directory: Path = EVIDENCE_DIR) -> "EvidencePacks":
        if not directory.exists():
            return cls([])
        return cls([json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))
                    if not p.name.startswith("_")])

    def get(self, name: str) -> Pack | None:
        raw = self._by_name.get(normalize(name))
        return parse_pack(raw) if raw else None

    def names(self) -> list[str]:
        return sorted({raw["company"] for raw in self._by_name.values()})
