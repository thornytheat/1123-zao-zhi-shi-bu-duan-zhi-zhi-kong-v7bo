from collections import Counter

import pytest

from sheetgrade.machine_reel import evaluate, summarize_reels
from sheetgrade.pipeline import load_shift, run


def tick(reel, minute, count, **extra):
    return {'line':'PM-1','reel':reel,'period':minute,'ingested':minute+3,'speed':1040,'vacuum':42,
            'vacuum_unit':'kPa','consistency':.83,'spliced':False,'counter':count}|extra


def proof(rows, **kwargs):
    return summarize_reels(evaluate(rows,watermark=200),**kwargs)


def test_continuity_counter_reset_requires_a_splice_or_review():
    rows=[tick('S1',3,112),tick('S2',7,120),tick('S3',11,3,spliced=True),tick('S4',15,2),tick('S5',19,3)]
    report=proof(rows)['machines'][0]
    assert [event['reason'] for event in report['events']]==['MISSING_COUNTER_TICKS','SPLICE_COUNTER_RESET','UNEXPLAINED_COUNTER_RESET']
    assert report['continuous_transitions']==1
    assert report['missing_ticks']==7
    assert report['events'][0]['period']==[3,7]
    assert report['mean_speed']==1040
    assert report['max_delay']==3


def test_gap_and_shared_timestamp_have_distinct_evidence():
    rows=[tick('S1',3,112),tick('S2',3,113),tick('S3',19,114),tick('S4',24,115)]
    report=proof(rows,max_gap=5)['machines'][0]
    assert [event['reason'] for event in report['events']]==['PARALLEL_REEL_RECORD','SAMPLING_GAP']
    assert report['missing_ticks']==0
    assert report['events'][0]['elapsed']==0
    assert report['events'][1]['elapsed']==16
    assert report['continuous_transitions']==1


def test_false_speed_can_never_enter_sample_statistics():
    rows=[tick('R1',3,1),tick('R2',13,2,speed=1300),tick('R3',23,3,speed=5),tick('R4',33,4,speed='空')]
    result=proof(rows)
    assert result['input_balance'] and result['raw_documents']==len(rows)
    assert result['schema_failures']==1
    one=result['machines'][0]
    assert one['mean_speed']==1170
    assert one['usable_packets']==2
    assert one['unusable_packets']==1
    assert one['rejected_by_reason']=={'REEL_IDLE_OR_OVERSPEED':1}


def test_repeated_conflict_does_not_break_raw_counts_and_never_yields_two_ticks():
    same=tick('S1',3,8)
    conflict=tick('S2',8,9)
    events=[same,same,conflict,conflict|{'speed':999},conflict|{'speed':888}]
    report=proof(events)
    assert report['input_balance']
    assert report['consumed_packets']==5
    [line]=report['machines']
    assert line['packet_groups']==2
    assert line['duplicates']==3
    assert line['usable_packets']==line['unusable_packets']==1
    assert line['rejected_by_reason']=={'COUNTER_PACKET_CONFLICT':1}
    assert not line['events']


def test_a_machine_without_readings_is_audited_without_synthetic_speed():
    report=proof([],expected_lines=['PM-1','PM-2'])
    assert report['input_balance']
    assert report['raw_documents']==0
    for entry in report['machines']:
        assert entry['mean_speed'] is None
        assert entry['max_delay'] is None
        assert entry['raw_packets']==entry['packet_groups']==0
        assert entry['events']==[]


def test_station_counter_does_not_compare_across_lines_even_when_roll_code_matches():
    rows=[tick('S1',12,112,line='PM-A'),tick('S2',14,2,line='PM-B')]
    report=proof(rows)
    assert report['input_balance']
    assert [entry['line'] for entry in report['machines']]==['PM-A','PM-B']
    assert all(entry['continuous_transitions']==0 and not entry['events'] for entry in report['machines'])


def test_with_real_fixture_raw_source_and_stage_rejections_balance():
    view=run()
    ingress=view['stages'][0]['records']
    note=view['reconciliation']['counter_continuity']
    assert note['input_balance']
    assert note['raw_documents']==len(load_shift()['meters'])
    assert note['schema_failures']==len(view['stages'][0]['errors'])
    counts=Counter(row['line'] for row in ingress if row['ready'])
    for row in note['machines']:
        assert row['usable_packets']==counts[row['line']]
        assert row['usable_packets']+sum(row['rejected_by_reason'].values())==row['packet_groups']
        assert row['raw_packets']-row['duplicates']==row['packet_groups']


@pytest.mark.parametrize('cadence',[0,1.5,-4,None])
def test_invalid_control_cadence_is_not_inferred_from_samples(cadence):
    with pytest.raises(ValueError,match='INVALID_REEL_CADENCE'):
        proof([],max_gap=cadence)


def test_ineligible_measurement_never_produces_a_risk_estimate_or_removes_the_reel():
    record=run()
    rejected={(row['line'],row['reel']) for row in record['stages'][0]['records'] if not row['ready']}
    incoming={(row['line'],row['reel']) for row in record['stages'][0]['records']}
    items={(row['machine'],row['reel']):row for row in record['rows']}
    scored={(row['line'],row['reel']) for row in record['stages'][3]['records']}
    assert incoming==set(items)
    assert rejected-scored
    for key in rejected-scored:
        assert items[key]['break_probability'] is None
        assert items[key]['status']!='继续生产'
    groups=record['reconciliation']['counter_continuity']['machines']
    assert sum(row['unusable_packets'] for row in groups)>=2
    for point in record['series']:
        assert isinstance(point['label'],str) and point['label'].endswith('%')
        assert point['value']>=0
    assert all(lhs['value']<=rhs['value'] for lhs,rhs in zip(record['series'],record['series'][1:]))
    assert sum(row['lab'] is not None for row in record['rows'])==record['metrics']['实验室席位']
