import pytest

from sheetgrade.grade_change import audit_grade_timeline, evaluate
from sheetgrade.grade_change.service import grade_at
from sheetgrade.pipeline import load_shift, run


def plan(code, start, stop, **changes):
    return dict(line='PM-A',grade='箱板',order=code,effective=start,until=stop,stabilize=4,recorded=2,revision=1)|changes


def entries(rows, as_of=10):
    return evaluate(rows,available_at=as_of)['records']


def test_colliding_production_plans_are_measured_as_distinct_spans():
    rows=entries([plan('PA',5,18),plan('PB',14,26,grade='牛皮')])
    timeline=audit_grade_timeline(rows,start=3,end=31)[0]
    assert timeline['phase_minutes']=={'无计划':7,'换线':4,'稳定':13,'重叠计划':4}
    assert timeline['stable_minutes_by_grade']=={'箱板':5,'牛皮':8}
    assert timeline['conflict_share']==pytest.approx(4/28)
    assert timeline['minutes_reconciled']
    assert timeline['evidence'][3]=={'start':14,'end':18,'state':'重叠计划','grade':None,'orders':['PA','PB'],'minutes':4}


def test_unmatched_machine_is_neutral_without_erasing_elapsed_coverage():
    rows=audit_grade_timeline([],start=3,end=31,require_lines=['PM-Z','PM-Y'])
    assert [row['line'] for row in rows]==['PM-Y','PM-Z']
    assert all(row['phase_minutes']=={'无计划':28} for row in rows)
    assert all(row['evidence'][0]['orders']==[] for row in rows)
    assert all(row['conflict_share']==0 for row in rows)


def test_version_conflict_is_distinct_from_idle_line():
    problem=entries([plan('PA',5,18),plan('PA',5,18,grade='牛皮')])
    timeline=audit_grade_timeline(problem,start=3,end=21)[0]
    assert timeline['phase_minutes']=={'无计划':5,'待审核':13}
    assert timeline['stable_minutes_by_grade']=={}
    assert timeline['evidence'][1]['orders']==['PA']


def test_zero_changeover_is_stable_from_start_and_end_is_adjoining():
    rows=entries([plan('PA',5,18,stabilize=0),plan('PB',18,22,stabilize=0)])
    timeline=audit_grade_timeline(rows,start=5,end=24)[0]
    short=timeline['evidence']
    assert [row['minutes'] for row in short]==[13,4,2]
    assert timeline['stable_minutes_by_grade']=={'箱板':17}
    assert grade_at(rows,'PM-A',18)['order']=='PB'
    assert short[1]['orders']==['PB']


@pytest.mark.parametrize('start,end', [(130,160),(155,192),(170,255),(220,255),(215,221)])
def test_interval_evidence_reconciles_each_minute_to_production_semantics(start,end):
    plans=entries(load_shift()['orders'],as_of=255)
    report=audit_grade_timeline(plans,start=start,end=end)
    for machine in report:
        observed=[(minute,span) for span in machine['evidence'] for minute in range(span['start'],span['end'])]
        assert [minute for minute,_ in observed]==list(range(start,end))
        for minute,span in observed:
            reference=grade_at(plans,machine['line'],minute)
            if span['state']=='稳定':
                assert reference['steady'] and reference['grade']==span['grade']
            elif span['state']=='换线':
                assert reference['grade_reason']=='TRANSITION_HOLD'
            elif span['state']=='重叠计划':
                assert reference['grade_reason']=='GRADE_AMBIGUOUS'
            else:
                assert reference['grade_reason']=='GRADE_MISSING'


def test_primary_report_contains_the_expected_grade_schedule_conflict():
    plans=run()['reconciliation']['shift_grade_minutes']
    disputed=next(row for row in plans if row['line']=='PM-1')
    assert disputed['phase_minutes']['重叠计划']==10
    assert disputed['conflict_share']==pytest.approx(10/125)
    for line in plans:
        assert line['minutes_reconciled']
        assert line['window']==[130,255]
        assert sum(line['stable_minutes_by_grade'].values())==line['phase_minutes']['稳定']


def test_nonpositive_window_has_no_available_denominator():
    with pytest.raises(ValueError,match='INVALID_AUDIT_INTERVAL'):
        audit_grade_timeline([],start=5,end=5)
