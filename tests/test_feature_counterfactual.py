import math

import pytest

from sheetgrade.breakpoint_model import compare_supporting_cast
from sheetgrade.pipeline import run, load_shift


def signal(idx, **changes):
    return dict(reel=f'R{idx}',line='PM-X',grade='牛皮',period=idx,consistency_z=(idx%10-5)/2,
                speed_z=0,vacuum_z=idx%6/4,break_within=idx%10>=5,observed=idx+2)|changes


def input_window():
    return [signal(index) for index in range(60)]


def test_perturbation_moves_only_intended_axis_across_tree_split():
    forecast=signal(80,consistency_z=1.0)
    targets={'consistency_z':-1.0,'speed_z':0,'vacuum_z':0}
    source=compare_supporting_cast([forecast],history=input_window(),cutoff=70,targets=targets)
    case,=source['reels']
    assert case['current_risk']==pytest.approx(31/32)
    assert case['best_feature']=='consistency_z'
    assert case['current_path']==['consistency_z>-0.250']
    first,second,third=case['alternatives']
    assert first['risk']==pytest.approx(1/32)
    assert first['crosses_cutoff'] and first['confirmed_coordinate']==-1
    assert first['delta']==pytest.approx(-30/32)
    assert first['lineage']==['consistency_z≤-0.250']
    assert second['delta']==third['delta']==0
    assert second['leaf_rows']==third['leaf_rows']==30


def test_reference_changes_bounded_by_operator_motion_limit():
    forecast=signal(80,consistency_z=1.0)
    targets={'consistency_z':-1.0,'speed_z':0,'vacuum_z':0}
    source=compare_supporting_cast([forecast],history=input_window(),cutoff=70,targets=targets,max_step=.5)
    case=source['reels'][0]
    first,second,third=case['alternatives']
    assert first['confirmed_coordinate']==.5
    assert first['target']==-1
    assert not first['crosses_cutoff']
    assert case['diagnosis']=='NO_LOWER_SINGLE_CHANNEL_PATH'
    assert case['best_feature'] is None


def test_unsupported_machine_observation_cannot_emit_an_advice_path():
    forecast=signal(81,consistency_z=70,vacuum_z=1)
    source=compare_supporting_cast([forecast],history=input_window(),cutoff=70)
    case,=source['reels']
    assert case['current_risk'] is None
    assert case['current_leaf_rows']==30
    assert case['diagnosis']=='BASELINE_OUTSIDE_MODEL_SUPPORT'
    assert case['alternatives']==[]
    assert case['best_feature'] is None


def test_out_of_domain_target_marks_axis_only_without_suppressing_others():
    target={'consistency_z':0,'speed_z':10,'vacuum_z':-12}
    view=compare_supporting_cast([signal(81)],history=input_window(),cutoff=70,targets=target)
    normal,*unavailable=view['reels'][0]['alternatives']
    assert normal['reason']=='PERTURBED'
    assert normal['delta']==pytest.approx(30/32)
    assert {row['feature'] for row in unavailable}=={'speed_z','vacuum_z'}
    for row in unavailable:
        assert row['risk'] is None and row['crosses_cutoff'] is None
        assert not row['lineage'] and row['leaf_rows']==0
        assert row['reason']=='REFERENCE_TARGET_OUT_OF_RANGE'


def test_holdout_inputs_do_not_change_model_identity_or_published_path():
    history=input_window()
    expected=compare_supporting_cast([signal(80)],history=history,cutoff=70)
    based_on_late_outcome=history+[signal(51,reel='LATE',observed=70,break_within=False),signal(82)]
    assert expected==compare_supporting_cast([signal(80)],history=based_on_late_outcome,cutoff=70)
    assert expected==compare_supporting_cast([signal(80)],history=history[::-1],cutoff=70)
    assert expected['training_count']==60
    assert expected['fit_id']!=compare_supporting_cast([signal(80)],history=history,cutoff=71)['fit_id']


@pytest.mark.parametrize('override,error', [({'depth':8},'INVALID_DIAGNOSTIC_TREE'),
        ({'min_leaf':1},'INVALID_DIAGNOSTIC_TREE'),({'max_step':float('inf')},'INVALID_MODEL_PERTURBATION'),
        ({'threshold':float('nan')},'INVALID_MODEL_PERTURBATION'),({'targets':{'speed_z':0}},'TARGETS_MUST_MATCH_FEATURES')])
def test_invalid_perturbation_inputs_do_not_count_as_healthily_in_scope(override,error):
    with pytest.raises(ValueError,match=error):
        compare_supporting_cast([],history=input_window(),cutoff=70,**override)


def test_missing_training_lists_reels_for_independent_manual_review():
    result=compare_supporting_cast([signal(75),signal(87)],history=[],cutoff=70)
    assert result['reference_feature_ranges']=={}
    assert result['training_count']==0
    assert [row['reel'] for row in result['reels']]==['R75','R87']
    assert {row['current_risk'] for row in result['reels']}=={None}


@pytest.mark.parametrize('capacity',[1,3,5,16])
def test_diagnostic_tree_matches_frozen_operating_model_for_all_samples(capacity):
    data=run(capacity)
    model={(row['line'],row['reel']):row for row in data['stages'][3]['records']}
    result=data['reconciliation']['model_diagnostics']
    assert result['training_count']>100
    assert len(model)==len(result['reels'])
    assert set(result['reference_targets'])=={'consistency_z','vacuum_z','speed_z'}
    for row in result['reels']:
        item=model[row['line'],row['reel']]
        assert row['current_risk']==item['probability']
        assert row['current_path']==item['branch']
        assert row['current_leaf_rows']==item['support']
        assert all(option['risk'] is None or math.isfinite(option['risk']) for option in row['alternatives'])
    assert len(load_shift()['meters'])>=len(model)
