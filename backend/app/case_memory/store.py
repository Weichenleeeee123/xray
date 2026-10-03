"""Atomic private derived files. Ownerless cases never get a memory."""
import hashlib
from pathlib import Path

from app import config
from app.models import Case
from app.persistence import atomic_json, locked
from . import builder
from .models import CaseMemory


class MemoryStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or config.CASE_MEMORY_DIR).resolve()
        public_roots = [config.WEB_DIR, config.DEMO_DIR, config.REPO_DIR / "research-room/public",
                        config.REPO_DIR / "research-room/home-dist"]
        if any(self.directory.is_relative_to(root.resolve()) for root in public_roots):
            raise ValueError("Case memory must not be stored under public assets")

    def _identity(self, case: Case, no: int, owner: str):
        builder.authorize(case, owner)
        source = builder.manifest(case, builder.version(case, no))
        rules = builder.ruleset()
        key = hashlib.sha256(builder.dump([owner, case.id, no, source, rules, builder.BUILDER_VERSION]).encode()).hexdigest()
        return self.directory / (key + ".json"), source, rules

    def get_or_build(self, case: Case, no: int, owner: str) -> CaseMemory:
        path, source, rules = self._identity(case, no, owner)
        with locked(path):
            if path.exists():
                try:
                    value = CaseMemory.model_validate_json(path.read_text(encoding="utf-8"))
                    if (value.state == "ready" and value.schema_version == 1 and value.owner_key == owner
                        and value.case_id == case.id and value.version_no == no and value.source_manifest_hash == source
                        and value.ruleset_version == rules and value.builder_version == builder.BUILDER_VERSION):
                        return value
                except (ValueError, OSError):
                    pass
            try:
                result = builder.build(case, no, owner)
                atomic_json(path, result.model_dump(mode="json"))
                return result
            except Exception:
                # Safe failure metadata only: no raw exception messages or material in logs.
                atomic_json(path, CaseMemory(case_id=case.id, version_no=no, owner_key=owner,
                    source_manifest_hash=source, ruleset_version=rules, builder_version=builder.BUILDER_VERSION,
                    state="failed", warnings=["deterministic_build_failed"]).model_dump(mode="json"))
                raise
