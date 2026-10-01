"""官方名单索引：保险机构、期货公司、支付机构、私募基金管理人（都是真实数据，整份下载到本地）。

数据由 tools/ 下的脚本生成，放在 data/registries/<id>.csv + <id>.meta.json。
文件不存在就不加载，查询时记"没查"，不当作没有。银行业名单历史原因单独在 licenses.py。
"""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import DATA_DIR
from app.models import RegistryHit
from app.sources.licenses import normalize

REGISTRY_DIR = DATA_DIR / "registries"
# id → (这份名单证明的是什么资格, 机构类型字段)
LICENSE_LISTS = {
    "nfra_insurance": ("保险机构", "type"),
    "csrc_futures": ("期货公司", None),
    "pbc_payment": ("支付机构", "business"),
}
AMAC_ID = "amac_managers"


@dataclass
class RegistryIndex:
    id: str
    meta: dict
    rows: dict[str, dict]

    @classmethod
    def load(cls, rid: str, directory: Path = REGISTRY_DIR) -> "RegistryIndex | None":
        path, meta_path = directory / f"{rid}.csv", directory / f"{rid}.meta.json"
        if not path.exists() or not meta_path.exists():
            return None
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = {normalize(r["name"]): r for r in csv.DictReader(f)}
        return cls(rid, json.loads(meta_path.read_text(encoding="utf-8")), rows)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def title(self) -> str:
        return self.meta["title"]

    def lookup(self, query: str, limit: int = 3) -> RegistryHit:
        q = normalize(query)
        record = self.rows.get(q)
        suggestions = []
        if record is None and len(q) >= 4:
            suggestions = [r["name"] for k, r in self.rows.items() if q in k][:limit]
        return RegistryHit(registry=self.id, title=self.title, query=query, found=record is not None, record=record,
                           suggestions=suggestions, as_of=self.meta.get("as_of"),
                           count=self.meta.get("count", len(self)))  # 用官方条数：同名去重后会少几家


def load_registries(directory: Path = REGISTRY_DIR) -> dict[str, RegistryIndex]:
    out = {}
    for rid in [*LICENSE_LISTS, AMAC_ID]:
        if index := RegistryIndex.load(rid, directory):
            out[rid] = index
    return out
