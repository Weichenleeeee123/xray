"""Identify document findings and reuse saved official-list evidence without queries."""
import re

from app.models import LicenseHit, RawRecord, RegistryHit, Version
from app.sources.licenses import normalize
from app.sources.registries import LICENSE_LISTS


class SavedLicenses:
    """Only the saved entity-specific lookup is evidence in a supplement."""
    def __init__(self, hit: LicenseHit):
        self.hit = hit

    def lookup(self, name: str) -> LicenseHit | None:
        names = [self.hit.query] + ([self.hit.record.name] if self.hit.record else [])
        return self.hit if normalize(name) in {normalize(n) for n in names} else None


def saved_registry_hits(raw: list[RawRecord], version: Version) -> list[RegistryHit]:
    out = []
    for record in raw:
        if record.id not in version.raw_ids or record.source_id not in LICENSE_LISTS:
            continue
        content = record.content
        if not isinstance(content, dict) or "是否收录" not in content:
            continue
        source = version.sources.get(record.source_id)
        count = re.search(r"共\s*([\d,]+)\s*家", record.note or "")
        out.append(RegistryHit(registry=record.source_id, title=source.name if source else record.title,
                               query=content.get("查询名称", ""), found=content["是否收录"],
                               record=content.get("记录"), suggestions=content.get("名称相近的机构", []),
                               as_of=record.as_of, count=int(count[1].replace(",", "")) if count else 0))
    return out
