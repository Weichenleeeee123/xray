"""案卷文件存储：原子写入、跨进程锁和乐观并发检查。"""
import json
from pathlib import Path

from app.models import Case, CaseSummary
from app.persistence import locked, atomic_text, atomic_json


class ConflictError(Exception):
    pass


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
        with locked(path):
            current = self.get(case.id)
            if current and current.revision != case.revision:
                raise ConflictError("案卷已被更新，请刷新后重试")
            self._write(case, path)
        return case

    def _write(self, case: Case, path: Path):
        if len(case.versions) > 100 or len(case.chat) > 1000:
            raise ConflictError("案卷已达到 100 个版本或 1000 条对话的上限，请新建案卷")
        checked = Case.model_validate(case.model_dump())
        if not checked.versions or checked.current != checked.versions[-1].no:
            raise ValueError("案卷当前版本与版本历史不一致")
        if [v.no for v in checked.versions] != list(range(1, checked.current + 1)):
            raise ValueError("案卷版本号不连续")
        checked.revision += 1
        atomic_text(path, checked.model_dump_json())
        case.revision = checked.revision
        self._summary(path, checked)

    def _summary(self, path: Path, case: Case):
        v = case.versions[-1]
        summary = CaseSummary(id=case.id, created_at=case.created_at, company_name=case.case.company_name,
                              need=case.case.need, scenario_label=v.scenario_label, versions=len(case.versions))
        stat = path.stat()
        try:
            atomic_json(self.dir / "summaries" / path.name,
                        {"mtime": stat.st_mtime_ns, "size": stat.st_size, "summary": summary.model_dump()})
        except OSError:
            pass
        return summary

    def append_chat(self, case_id: str, messages):
        path = self._path(case_id)
        with locked(path):
            case = self.get(case_id)
            if case is None:
                raise KeyError(case_id)
            case.chat.extend(messages)
            self._write(case, path)

    def get(self, case_id: str) -> Case | None:
        try:
            path = self._path(case_id)
        except KeyError:
            return None
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        # Compatibility with the historical resolve action accidentally persisted as a state.
        for version in data.get("versions", []):
            for judgment in version.get("judgments", []):
                if judgment.get("state") == "recheck":
                    judgment["state"] = "needs_check"
        return Case.model_validate(data)

    def list(self, limit: int | None = None, offset: int = 0) -> list[CaseSummary]:
        out = []
        for path in self.dir.glob("*.json"):
            try:
                stat = path.stat()
                try:
                    entry = json.loads((self.dir / "summaries" / path.name).read_text(encoding="utf-8"))
                    if entry["mtime"] == stat.st_mtime_ns and entry["size"] == stat.st_size:
                        out.append(CaseSummary.model_validate(entry["summary"]))
                        continue
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                with locked(path):
                    c = self.get(path.stem)
                    if c:
                        out.append(self._summary(path, c))
            except (ValueError, OSError):
                continue  # 旧格式或损坏的文件跳过
        ordered = sorted(out, key=lambda s: (s.created_at, s.id), reverse=True)
        return ordered[offset:offset + limit] if limit is not None else ordered[offset:]
