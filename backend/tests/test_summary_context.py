from app.analysis.overview import build_overview
from app.models import RawRecord
from tests.test_company_summary import record, report


def labor_case(dates):
    item = record('labor', f'劳动仲裁 {len(dates)} 条，当被告的劳动官司 0 条', label='劳动仲裁和劳动纠纷', source='qcc_labor')
    item.detail = '近两年 0 条'
    v = report('job', '应聘电商运营，关注经营稳定性', ('credit', [item]),
               ('finance', [record('revenue', '101.16 亿元，同比 -9.78%', label='营业收入（2025年年报）')]))
    v.created_at = '2026-10-04T00:00:00+08:00'
    v.raw_ids = ['R1']
    raw = RawRecord(id='R1', source_id='qcc_labor', title='劳动仲裁', kind='commercial',
                    retrieved_at='2026-10-04', content={'平台记录总数': len(dates),
                    '返回的明细': [{'日期': d} for d in dates]})
    return v, raw


def test_old_records_have_dates_and_one_relevant_business_fact_without_reclassifying():
    v, raw = labor_case(['2016-10-12', '2019-01-21'])
    before = v.model_dump()
    o = build_overview(v, raw_records=[raw])
    assert '历史劳动争议' in o.headline
    assert '入职需重点了解' not in o.headline
    assert '2016' in o.summary.explanation and '2019' in o.summary.explanation
    assert '近两年 0 条' in o.summary.explanation
    assert '2025年年报' in o.summary.explanation and '-9.78%' in o.summary.explanation
    assert 'finance.revenue' in o.summary.basis_ids
    assert v.model_dump() == before


def test_missing_event_dates_do_not_use_retrieval_date_or_claim_all_records_historical():
    v, raw = labor_case(['2016-10-12', ''])
    o = build_overview(v, raw_records=[raw])
    assert '历史劳动争议' not in o.headline
    assert '日期未明' in o.summary.explanation
    assert '2026-10-04' not in o.summary.explanation


def test_recent_records_and_incomplete_rows_are_not_labelled_historical():
    v, raw = labor_case(['2016-10-12', '2026-09-01'])
    assert '历史劳动争议' not in build_overview(v, raw_records=[raw]).headline
    raw.content['返回的明细'] = [{'日期': '2016-10-12'}]
    assert '历史劳动争议' not in build_overview(v, raw_records=[raw]).headline


def test_other_version_evidence_is_not_used():
    v, raw = labor_case(['2016-10-12', '2019-01-21'])
    v.raw_ids = []
    assert '历史劳动争议' not in build_overview(v, raw_records=[raw]).headline


def test_cooperation_explains_actual_execution_count_and_one_related_record():
    v = report('contract', '准备合作，关注履约',
               ('finance', [record('executions', '5 条', 'bad', '被执行')]),
               ('credit', [record('lawsuits', '近两年当被告 2 条', 'warn', '开庭和立案')]))
    o = build_overview(v)
    assert '被执行：5 条' in o.summary.explanation
    assert '近两年当被告 2 条' in o.summary.explanation
    assert o.summary.basis_ids == ['finance.executions', 'credit.lawsuits']


def test_prepaid_summary_includes_specific_complaint_and_related_execution_fact():
    v = report('prepaid', '想充值',
               ('reputation', [record('top_topic', '退款困难', 'warn', '投诉主题', source='complaints')]),
               ('finance', [record('executions', '3 条', 'bad', '被执行')]))
    o = build_overview(v)
    assert '投诉主题：退款困难' in o.summary.explanation
    assert '被执行：3 条' in o.summary.explanation
    assert '不等于企业违规已被认定' in o.summary.explanation


def test_missing_secondary_fact_is_not_invented_and_critical_record_stays_first():
    v = report('general', '', penalties='bad')
    o = build_overview(v)
    assert '营业收入' not in o.summary.explanation
    v.signals[0].items[0].value = '吊销'
    v.signals[0].items[0].status = 'bad'
    assert build_overview(v).headline == '登记状态：吊销'


def test_general_penalty_keeps_event_dates_and_unknown_dates_explicit():
    v = report('general', '', penalties='bad')
    penalty = next(i for s in v.signals for i in s.items if i.key == 'penalties')
    penalty.value = '2 条'
    penalty.detail = '2022-09-06 罚款；日期未公示 另一处罚'
    o = build_overview(v)
    assert '2022-09-06' in o.summary.explanation
    assert '日期未明' in o.summary.explanation
    assert '已解决' not in o.summary.explanation


def test_supporting_fact_is_limited_to_one_and_must_be_covered():
    v = report('contract', '准备合作', ('finance', [record('executions', '5 条', 'bad', '被执行'),
                 record('revenue', '100 亿元', label='营收')]),
               ('credit', [record('lawsuits', '2 条', 'warn', '开庭和立案')]))
    o = build_overview(v)
    assert len(o.summary.basis_ids) == 2 and '100 亿元' not in o.summary.explanation
    for s in v.signals:
        for i in s.items:
            if i.key in {'lawsuits', 'revenue'}:
                i.gap, i.status = 'failed', 'none'
    o = build_overview(v)
    assert o.summary.basis_ids == ['finance.executions']
