"""Small, factual context for a saved finding; never infer resolution or safety."""
from datetime import date, timedelta
import re


def record_context(version, item, raw_records):
    signal = next((i for s in version.signals for i in s.items
                   if f'{s.key}.{i.key}' == item.id and i.ref == item.ref
                   and i.status == item.status and i.value == item.text), None)
    detail = (signal.detail or '') if signal else ''
    # Dates in source metadata describe collection, not the event. Only read
    # the known event rows, and only within this version's evidence references.
    raw = next((r for r in raw_records if r.id == item.ref and r.id in version.raw_ids
                and r.source_id == item.source and r.coverage == 'found'), None)
    if item.id == 'credit.labor' and raw and isinstance(raw.content, dict):
        rows = raw.content.get('返回的明细')
        total = raw.content.get('平台记录总数')
        if isinstance(rows, list) and rows:
            dates = []
            for row in rows:
                try:
                    dates.append(date.fromisoformat(str(row.get('日期', ''))[:10]))
                except (ValueError, AttributeError):
                    pass
            years = sorted({str(d.year) for d in dates})
            note = ('已返回明细的事件年份为' + '、'.join(years) + '年。') if years else ''
            if len(dates) < len(rows):
                note += '部分记录日期未明，不能据此判断发生时间。'
            if total != len(rows):
                note += '明细未覆盖平台全部记录。'
            try:
                cutoff = date.fromisoformat(version.created_at[:10]) - timedelta(days=730)
                historical = (total == len(rows) == len(dates) and all(d < cutoff for d in dates)
                              and re.fullmatch(r'劳动仲裁 \d+ 条，当被告的劳动官司 0 条', item.text) is not None)
            except ValueError:
                historical = False
            recent = re.search(r'近两年\s*\d+\s*条', detail)
            if recent:
                note += '本版所查明细：' + recent.group() + '。'
            return historical, note
    # Preserve explicit scope in the signal, without treating an undated
    # record or a zero recent count as proof that all events are historical.
    recent = re.search(r'近[一二两三\d]+年[^。；]*?\d+\s*条', detail)
    if recent:
        return False, '本版所查明细：' + recent.group() + '。'
    dates = list(dict.fromkeys(re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', detail)))
    if dates:
        note = '列示记录日期包括' + '、'.join(dates[:3]) + '。'
        if re.search(r'日期未|时间未', detail):
            note += '另有记录日期未明。'
        return False, note
    return False, ''


def supporting_keys(purpose, need):
    """Select one complement, not another full summary or an inferred score."""
    business = bool(re.search(r'经营|稳定|营收|盈利|财务|业务', need))
    mapping = {
        'job': ('finance.jobs', 'finance.insured', 'finance.revenue'),
        'contract': ('finance.executions', 'credit.lawsuits', 'finance.revenue'),
        'prepaid': ('reputation.top_topic', 'finance.executions', 'reputation.web_complaint'),
        'rental': ('reputation.top_topic', 'finance.executions', 'credit.lawsuits'),
        'takeover': ('finance.executions', 'finance.tax_arrears', 'finance.revenue'),
        'investment': ('finance.revenue', 'finance.latest_period', 'finance.net_profit'),
        'savings': ('risk.bank_list', 'risk.amac'),
        'general': ('finance.revenue', 'finance.latest_period', 'finance.executions'),
    }
    keys = mapping[purpose]
    return ('finance.revenue', *keys) if business else keys
