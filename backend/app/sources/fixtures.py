"""演示数据源：企业登记、私募登记、投诉。

公司全部虚构。每个类都对应一个以后要换成真实接口的位置，
对外只暴露 get / lookup，换接口时调用方不用改。
"""
import json
from pathlib import Path

from app.config import FIXTURES_DIR
from app.models import AmacHit, CompanyProfile, Coverage
from app.sources.licenses import normalize


def _read(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FixtureRegistry:
    """企业登记与年报。正式版替换为企业信用信息公示系统或企查查等授权接口。"""

    def __init__(self, companies: list[CompanyProfile], as_of: str):
        self.as_of = as_of
        self._by_name = {normalize(c.name): c for c in companies}

    @classmethod
    def load(cls, path: Path | None = None) -> "FixtureRegistry":
        raw = _read("companies.json") if path is None else json.loads(path.read_text(encoding="utf-8"))
        return cls([CompanyProfile(**c) for c in raw["companies"]], raw["as_of"])

    def get(self, name: str) -> CompanyProfile | None:
        return self._by_name.get(normalize(name))


class FixtureAmac:
    """中基协私募基金管理人登记。实时查询接口在本地测试返回 500，暂用快照。"""

    def __init__(self, covered: list[str], registered: list[str], as_of: str):
        self.as_of = as_of
        self._covered = {normalize(n) for n in covered}
        self._registered = {normalize(n) for n in registered}

    @classmethod
    def load(cls) -> "FixtureAmac":
        raw = _read("amac.json")
        return cls(raw["covered"], raw["registered"], raw["as_of"])

    def lookup(self, name: str) -> AmacHit:
        n = normalize(name)
        if n in self._registered:
            return AmacHit(coverage=Coverage.found, registered=True)
        if n in self._covered:
            return AmacHit(coverage=Coverage.not_found, registered=False)
        return AmacHit(coverage=Coverage.not_covered)


class FixtureComplaints:
    """投诉平台数据。正式版由大模型做主题归类（每类附原文），计数由程序完成。"""

    def __init__(self, companies: dict[str, dict], as_of: str):
        self.as_of = as_of
        self._by_name = {normalize(k): v for k, v in companies.items()}

    @classmethod
    def load(cls) -> "FixtureComplaints":
        raw = _read("complaints.json")
        return cls(raw["companies"], raw["as_of"])

    def get(self, name: str) -> dict | None:
        return self._by_name.get(normalize(name))
