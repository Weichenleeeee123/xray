"""案卷存储：一个案卷一个 JSON 文件，重启不丢。演示只有一个人操作，不处理并发。"""
from pathlib import Path

from app.models import Case, CaseSummary


class CaseStore:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, case_id: str) -> Path:
        if not case_id.isalnum():
            raise KeyError(case_id)
        return self.dir / f"{case_id}.json"

    def save(self, case: Case) -> Case:
        path = self._path(case.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(case.model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(path)  # 先写临时文件再替换，写到一半断电也不会坏
        return case

    def get(self, case_id: str) -> Case | None:
        try:
            path = self._path(case_id)
        except KeyError:
            return None
        return Case.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def list(self) -> list[CaseSummary]:
        out = []
        for path in self.dir.glob("*.json"):
            try:
                c = Case.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue  # 旧格式或损坏的文件跳过
            v = c.versions[-1]
            out.append(CaseSummary(id=c.id, created_at=c.created_at, company_name=c.case.company_name, need=c.case.need,
                                   scenario_label=v.scenario_label, versions=len(c.versions)))
        return sorted(out, key=lambda s: s.created_at, reverse=True)
