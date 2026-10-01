"""持牌机构名单：金融监管总局公布的《银行业金融机构法人名单》本地索引（真实数据）。

只覆盖银行业金融机构（银行、信托、理财子公司、消费金融等），
不含证券、基金、保险、私募——查不到不等于没有牌照。
"""
import csv
import json
import re
from pathlib import Path

from app.config import LICENSE_CSV, LICENSE_META
from app.models import LicenseHit, LicenseRecord

_PAREN = str.maketrans({"(": "（", ")": "）"})


def normalize(name: str) -> str:
    return re.sub(r"\s+", "", name).translate(_PAREN)


class LicenseIndex:
    def __init__(self, records: list[LicenseRecord], meta: dict):
        self.meta = meta
        self._by_name = {normalize(r.name): r for r in records}

    @classmethod
    def load(cls, csv_path: Path = LICENSE_CSV, meta_path: Path = LICENSE_META) -> "LicenseIndex":
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            records = [LicenseRecord(name=r["name"], name_en=r["name_en"], code=r["code"],
                                     type=r["type"], regulator=r["regulator"]) for r in csv.DictReader(f)]
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        return cls(records, meta)

    def __len__(self) -> int:
        return len(self._by_name)

    def lookup(self, query: str, limit: int = 5) -> LicenseHit:
        q = normalize(query)
        record = self._by_name.get(q)
        suggestions: list[LicenseRecord] = []
        if record is None and len(q) >= 2:
            # 输入了简称（"杭州银行"）：给出包含它的全称
            suggestions = [r for k, r in self._by_name.items() if q in k][:limit]
            # 输入了分支机构（"杭州银行股份有限公司西湖支行"）：给出它所属的法人
            if not suggestions:
                suggestions = [r for k, r in self._by_name.items() if len(k) >= 6 and k in q][:limit]
        return LicenseHit(query=query, found=record is not None, record=record, suggestions=suggestions,
                          count=len(self))
