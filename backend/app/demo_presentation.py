"""Bind prebuilt wording to an exact evidence snapshot; never change ratings.

Only server-owned bundles can introduce this field. Public intake models have
no presentation field. A changed source, scope or live version drops the copy.
"""
import hashlib
import json

from app.models import Case, ReportPresentation, Version


def evidence_fingerprint(case: Case, version: Version) -> str:
    records = {record.id: record for record in case.raw}
    if len(records) != len(case.raw) or not set(version.raw_ids) <= records.keys():
        raise ValueError('Incomplete or duplicate evidence references')
    payload = {
        'company_name': case.case.company_name,
        'version': version.model_dump(mode='json', exclude={
            'overview', 'report_presentation', 'prebuilt', 'company_keywords'}),
        'raw': [records[key].model_dump(mode='json') for key in sorted(set(version.raw_ids))],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _valid_refs(case: Case, version: Version, refs: list[str]) -> bool:
    found = {record.id for record in case.raw if record.coverage == 'found'}
    return bool(refs) and set(refs) <= found & set(version.raw_ids)


def bind_presentation(case: Case, version: Version, *, title: str, note: str,
                      body: str, refs: list[str]) -> None:
    """Offline bundle preparation, after all evidence and notes are finalized."""
    if not version.prebuilt or not _valid_refs(case, version, refs):
        raise ValueError('Presentation requires a prebuilt version and valid evidence')
    version.report_presentation = ReportPresentation(title=title, note=note, body=body,
        refs=refs, evidence_sha256=evidence_fingerprint(case, version))


def refresh_presentations(case: Case) -> Case:
    for version in case.versions:
        presentation = version.report_presentation
        if presentation is None:
            continue
        try:
            valid = (version.prebuilt is not None
                     and _valid_refs(case, version, presentation.refs)
                     and presentation.evidence_sha256 == evidence_fingerprint(case, version))
        except ValueError:
            valid = False
        if not valid:
            version.report_presentation = None
    return case
