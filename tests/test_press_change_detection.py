from copy import deepcopy
import pytest

from sheetgrade.wet_signals import track_press_change
from sheetgrade.pipeline import run


def observation(minute,z=1,**changes):
    return dict(line='PMX',reel=f'P{minute}',grade='箱板',usable=True,vacuum_z=z,period=minute)|changes


def test_persistent_small_bias_raises_cusum_after_support_accumulates():
    rows=[observation(minute) for minute in range(3,10)]
    check=track_press_change(rows,allowance=.25,control=2.8)
    assert [row['state'] for row in check]==['WITHIN_CONTROL']*3+['VACUUM_UPSHIFT']*4
    assert [row['up'] for row in check]==[.75,1.5,2.25,3,3.75,4.5,5.25]
    assert not any(row['down'] for row in check)
    assert [row['run_length'] for row in check]==list(range(1,8))


def test_negative_values_do_not_look_like_higher_vacuum():
    rows=[observation(2,-1.5),observation(3,-3),observation(4,4)]
    points=track_press_change(rows,allowance=.5,control=3)
    assert [row['state'] for row in points]==['WITHIN_CONTROL','VACUUM_DOWNSHIFT','VACUUM_UPSHIFT']
    assert [row['down'] for row in points]==[1,3.5,0]
    assert [row['up'] for row in points]==[0,0,3.5]


def test_grade_change_and_telemetry_gap_reinitiate_control_limits():
    inputs=[observation(2,3),observation(3,3,grade='牛皮'),observation(40,3,grade='牛皮')]
    reports=track_press_change(inputs)
    assert [row['reset'] for row in reports]==['FIRST_READING','GRADE_CHANGE','OBSERVATION_GAP']
    assert all(row['up']==2.6 and row['run_length']==1 for row in reports)


def test_nonfinite_reference_and_splice_never_produce_fabricated_variance():
    broken=[observation(2,4),observation(3,float('nan')),observation(4,4),observation(5,12,usable=False),observation(6,1)]
    evidence=track_press_change(broken)
    assert [row['reset'] for row in evidence]==['FIRST_READING','NON_FINITE_CONTROL_READING','RESUMED_AFTER_HOLD',
                                               'OUTSIDE_STEADY_MACHINE_SCENE','RESUMED_AFTER_HOLD']
    assert [row['z'] for row in evidence]==[4,None,4,None,1]
    assert [row['run_length'] for row in evidence]==[1,0,1,0,1]


def test_two_paper_machines_do_not_share_smoothing_state():
    first=[observation(1,2,line='A'),observation(3,2,line='A')]
    extra=[observation(2,8,line='B'),observation(4,8,line='B')]
    combined=track_press_change(extra+first)
    assert [row for row in combined if row['line']=='A']==track_press_change(first)
    assert [row for row in combined if row['line']=='B']==track_press_change(extra)
    assert deepcopy(combined)==combined


def test_duplicate_tick_on_one_machine_is_ambiguous_but_other_machines_can_coexist():
    with pytest.raises(ValueError,match='DUPLICATE_CONTROL_TICK:PMX:2'):
        track_press_change([observation(2),observation(2,reel='TRANSFER')])
    assert len(track_press_change([observation(2),observation(2,line='PMY')]))==2


@pytest.mark.parametrize('options',[{'allowance':-1},{'control':.4},{'max_gap':0},{'control':float('inf')}])
def test_unspecified_control_band_rejected_even_if_no_rows(options):
    with pytest.raises(ValueError,match='INVALID_CUSUM_WINDOW'):
        track_press_change([],**options)


def test_workbench_control_evidence_reconciles_to_feature_records():
    report=run()
    features=report['stages'][2]['records']
    bands=report['reconciliation']['press_control']
    assert len(features)==len(bands)
    index={(row['line'],row['reel']):row for row in features}
    for row in bands:
        sample=index[row['line'],row['reel']]
        assert row['period']==sample['period']
        assert row['grade']==sample['grade']
        if sample['usable']:
            assert row['z']==sample['vacuum_z']
            assert row['run_length']>=1
        else:
            assert row['state']=='UNSCORED'
            assert row['run_length']==0
