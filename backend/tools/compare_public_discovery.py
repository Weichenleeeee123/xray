"""Opt-in public-search comparison. No QCC, cases, chats or uploads are accessed.

Run from backend: python tools/compare_public_discovery.py --live [--env-file PATH]
Only sanitized result metadata is reported; raw provider cache lives in a new temp
directory, never in committed fixtures. Reference URLs are evaluation inputs only.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
REFERENCES = [
    'https://www.knonii.com/about/',
    'https://www.36kr.com/newsflashes/3889585234213639',
    'https://m.nbd.com.cn/articles/2026-09-02/4570006.html',
    'https://www.shanghai.gov.cn/nw15343/20260114/a911f54941bc475d84527b97f423f02e.html',
    'https://play.google.com/store/apps/details?id=com.bwtt.magicscope',
    'https://www.cs.com.cn/xwzx/01/2026/09/19/detail_2026091910040281.html',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly opt into gateway search/model usage')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--company', action='append')
    parser.add_argument('--out', type=Path, help='Optional sanitized metadata-only JSON results')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required; may consume the configured gateway balance')
    if args.env_file:
        for line in args.env_file.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            key, value = line.split('=', 1)
            if key.strip().startswith('TOKENDANCE_'):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    from app import config
    from app.sources.discovery import discover, model_planner
    from app.sources.page_reader import canonical_url
    from app.sources.web import WebClient
    if not config.LLM_BASE_URL or not config.LLM_API_KEY:
        raise SystemExit('Configured gateway is required; no credentials printed.')
    cache = Path(tempfile.mkdtemp(prefix='qier-public-comparison-'))
    client = WebClient(mode='live', cache_dir=cache, timeout=10)
    def url_key(url):
        return canonical_url(url).rstrip('/')
    reports = []
    for name in args.company or ['上海绒音科技有限公司', '杭州银行股份有限公司', '长沙茶悦文化产业有限公司']:
        started = datetime.now(timezone.utc).isoformat()
        t = time.monotonic()
        old = client._find(name, ('official', 'news', 'media'))
        old_seconds = round(time.monotonic() - t, 3)
        old_urls = {url_key(h.url) for h in [*old.official, *old.news, *old.media]}
        new = discover(client, name, planner=model_planner(client))
        new_urls = old_urls | {url_key(c.url) for c in new.candidates}
        report = {'company': name, 'started_at': started, 'old_seconds': old_seconds,
            'additional_seconds': new.elapsed, 'old_urls': len(old_urls), 'combined_urls': len(new_urls),
            'new_candidates': len(new.candidates), 'new_relations': dict(Counter(c.metadata.relation for c in new.candidates)),
            'new_read_states': dict(Counter(c.metadata.read_state for c in new.candidates)),
            'new_natures': dict(Counter(c.metadata.nature for c in new.candidates)),
            'topics': sorted({t for c in new.candidates for t in c.metadata.topics}),
            'old_errors': old.errors, 'new_errors': new.errors, 'queries': new.queries,
            'discarded': new.discarded,
            'aliases': [{'term': a['term'], 'state': a['state'], 'source_url': a['source_url']} for a in new.aliases],
            'new_pages': [{'url': c.url, 'title': c.title, 'relation': c.metadata.relation,
                           'nature': c.metadata.nature, 'state': c.metadata.read_state, 'read_reason': c.read_reason}
                          for c in new.candidates],
            'notice': 'URL counts include possible matches, not verified facts or accuracy scores.'}
        if name == '上海绒音科技有限公司':
            report['reference_links'] = [{'url': url, 'old_found': url_key(url) in old_urls,
                                           'combined_found': url_key(url) in new_urls} for url in REFERENCES]
        reports.append(report)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k not in ('new_pages', 'queries')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
