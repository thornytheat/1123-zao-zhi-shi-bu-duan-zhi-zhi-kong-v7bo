import pytest

from sheetgrade.release_order import stress_laboratory
from sheetgrade.pipeline import run


def order(reel,**changes):
    return dict(reel=reel,line='PM1',grade='白板',probability=.87,model_ready=True,feature_reason='ESTIMATED',
                mass_kg=600,critical=False,critical_evidence=True,period=400)|changes


def test_simulator_preserves_lab_priority_and_handles_slack():
    cases=[order('R1',critical=True),order('R2',critical=True,mass_kg=1200),order('R3',line='PM2',model_ready=False,mass_kg=333)]
    options=stress_laboratory(cases,capacity_choices=[1,4],quotas=[1,2],thresholds=[.7])
    assert options['lowest_risk_scenario']==[4,2,.7]
    first,_,underfilled,complete=options['scenarios']
    assert first['confirmed_breach_pending_kg']==600
    assert first['unverified_pending_kg']==333
    assert first['by_line']=={'PM1':1}
    assert underfilled['unassigned_capacity']==2
    assert underfilled['pending_by_line']=={'PM1':{'count':1,'over_limit_mass':600,'needs_confirmation_mass':0}}
    assert not complete['pending_by_line']
    assert complete['unassigned_capacity']==1


def test_review_prediction_uncertainty_can_be_redeployed_after_threshold_increase():
    cases=[order('R1',probability=.7),order('R2',probability=.72)]
    table=stress_laboratory(cases,capacity_choices=[1],quotas=[2],thresholds=[.65,.9])['scenarios']
    assert table[0]['reserved']==1 and table[1]['reserved']==0
    assert table[0]['estimated_pending_kg']==pytest.approx(420)
    assert table[1]['mass_by_state']=={'继续生产':1200}


def test_exceeding_model_support_is_counted_as_uncertainty_not_a_grade_breach():
    rows=[order('R1',model_ready=False,critical=True,critical_evidence=False),order('R2',model_ready=False)]
    table=stress_laboratory(rows,capacity_choices=[1],quotas=[2],thresholds=[.65])['scenarios'][0]
    assert table['confirmed_breach_pending_kg']==0
    assert table['unverified_pending_kg']==600
    assert table['pending_by_line']=={'PM1':{'count':1,'over_limit_mass':0,'needs_confirmation_mass':600}}


def test_weighing_correction_islands_do_not_erase_production_mass():
    rows=[order('R1',probability=.7,period=200),order('R1',probability=.8,period=201),
          order('R2',mass_kg=800),order('R3',probability=.2,mass_kg=500)]
    for point in stress_laboratory(rows)['scenarios']:
        assert point['total_reels']==3
        assert sum(point['mass_by_state'].values())==1900
        assert len(point['allocations'])==point['reserved']
        assert sum(point['by_line'].values())==point['reserved']


@pytest.mark.parametrize('modifiers',[{'capacity_choices':[]},{'capacity_choices':[101]},{'quotas':[0]},
                                      {'thresholds':[0]}, {'capacity_choices':range(60),'quotas':[1,2]}])
def test_troubleshooting_configuration_refuses_sparse_or_oversized_grid(modifiers):
    with pytest.raises(ValueError,match='INVALID_LAB_SCENARIO'):
        stress_laboratory([],**modifiers)


def test_main_quality_sheet_and_existing_option_agree_on_actual_slots():
    workbench=run()
    baseline=next(point for point in workbench['reconciliation']['lab_options']['scenarios']
                  if (point['capacity'],point['per_line'],point['threshold'])==(5,3,.65))
    assert workbench['metrics']['实验室席位']==baseline['reserved']
    current={row['reel']:row['lab'] for row in workbench['rows'] if row['lab'] is not None}
    assert current=={row['reel']:row['slot'] for row in baseline['allocations']}
    assert workbench['metrics']['本班卷次']==baseline['total_reels']
