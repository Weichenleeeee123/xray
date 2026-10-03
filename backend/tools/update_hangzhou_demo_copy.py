"""Update only the evidence-bound introduction in an existing Hangzhou bundle.

Usage: python tools/update_hangzhou_demo_copy.py INPUT.json OUTPUT.json
The output must be new; retain the input as a backup before activation.
"""
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.demo_presentation import refresh_presentations
from app.models import Case

TITLE = '存在监管处罚，求职需结合具体岗位判断'
NOTE = '重点核实用工主体、岗位职责、考核要求与合同条款。'
BODY = (
    '已保存资料收录了杭州银行因贷款管理相关问题被罚975万元的记录，'
    '提示相关业务存在合规管理问题；现有资料尚不能确认整改情况。'
    '该事项本身不足以判断具体岗位的劳动条件或录用可靠性。'
    '涉及信贷、营销或风控岗位时，还应重点了解合规责任。'
)


def update(bundle: dict) -> dict:
    result = copy.deepcopy(bundle)
    assert result['demo_id'] == 'B' and result['stages']
    for stage in result['stages']:
        case = Case.model_validate(stage['case'])
        assert case.case.company_name == '杭州银行股份有限公司'
        refresh_presentations(case)
        for version, data in zip(case.versions, stage['case']['versions'], strict=True):
            assert version.scenario == 'job' and version.report_presentation
            penalty = next(i for s in version.signals for i in s.items if i.key == 'penalties')
            assert '975万元' in penalty.detail
            assert penalty.ref in version.report_presentation.refs
            record = next(r for r in case.raw if r.id == penalty.ref)
            evidence = json.dumps(record.model_dump(mode='json'), ensure_ascii=False)
            assert '975' in evidence and '贷款' in evidence
            data['report_presentation'].update(title=TITLE, note=NOTE, body=BODY)
        checked = refresh_presentations(Case.model_validate(stage['case']))
        assert all(v.report_presentation and v.report_presentation.title == TITLE for v in checked.versions)
    # Prove that only the three presentation text fields changed.
    restored = copy.deepcopy(result)
    for old_stage, new_stage in zip(bundle['stages'], restored['stages'], strict=True):
        for old, new in zip(old_stage['case']['versions'], new_stage['case']['versions'], strict=True):
            for field in ('title', 'note', 'body'):
                new['report_presentation'][field] = old['report_presentation'][field]
    assert restored == bundle
    return result


if __name__ == '__main__':
    source, destination = map(Path, sys.argv[1:])
    bundle = update(json.loads(source.read_text(encoding='utf-8')))
    with destination.open('x', encoding='utf-8') as handle:
        json.dump(bundle, handle, ensure_ascii=False)
    print(json.dumps({'stages': len(bundle['stages']), 'title': TITLE,
                      'evidence_unchanged': True}, ensure_ascii=False))
