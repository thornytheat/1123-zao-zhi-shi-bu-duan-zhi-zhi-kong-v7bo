from collections import Counter
import pytest

from sheetgrade.spool_audit import audit_grade_backtest
from sheetgrade.pipeline import run


def closed(reel,grade='箱板',**changes):
    return {'reel':reel,'grade':grade,'break_probability':.65,'mass_kg':800,'observed_break':True,
            'captured':30,'finalized':40,'confirmed':True}|changes


def test_last_calibration_bucket_is_closed_on_exact_one():
    points=[closed('A',break_probability=0),closed('B',break_probability=.2),closed('C',break_probability=.4),
            closed('D',break_probability=.6),closed('E',break_probability=.8),closed('F',break_probability=1)]
    report=audit_grade_backtest(points,as_of=50)
    [grade]=report['grades']
    assert [row['n'] for row in grade['histogram']]==[1,1,1,1,2]
    assert report['observed']==6 and grade['verified_bins']
    assert report['unflagged_kg']==3200
    assert grade['break_mass_recall']==pytest.approx(1/3)
    assert report['risk_vs_volume']['estimated_review_kg']==1600


def test_bias_uses_only_one_grade_and_finite_sample_uncertainty():
    points=[closed('A',break_probability=.65),closed('B',break_probability=.9,observed_break=False),
            closed('C','牛皮',break_probability=.4,observed_break=False)]
    report=audit_grade_backtest(points,as_of=50)
    by_name={row['grade']:row for row in report['grades']}
    a=by_name['箱板']['calibration']
    b=by_name['牛皮']['calibration']
    assert a['bias']==pytest.approx(.275)
    assert a['bias_standard_error']==pytest.approx(.625)
    assert a['brier']==pytest.approx((.35**2+.9**2)/2)
    assert b['bias']==pytest.approx(.4)
    assert b['bias_standard_error'] is None
    assert by_name['牛皮']['break_mass_recall'] is None
    assert by_name['箱板']['break_mass_recall']==1


def test_mass_replay_distinguishes_prediction_threshold_from_non_event():
    archive=[closed('A',break_probability=.69,mass_kg=1000),closed('B',break_probability=.7,mass_kg=500),
             closed('C','纸袋',break_probability=.76,mass_kg=2300,observed_break=False)]
    view=audit_grade_backtest(archive,as_of=50,threshold=.7)
    assert view['mass_reconciled']
    assert view['risk_vs_volume']['caught_kg']==500
    assert view['risk_vs_volume']['exposed_kg']==1000
    assert view['risk_vs_volume']['break_kg']==1500
    assert view['risk_vs_volume']['false_review_count']==1
    assert view['risk_vs_volume']['review_precision']==.5
    assert view['unflagged_kg']==view['risk_vs_volume']['exposed_kg']


def test_late_inspection_and_conflicting_versions_are_separately_preserved():
    rows=[closed('A'),closed('A',observed_break=False),closed('B',finalized=51),closed('C',confirmed=False),closed('D')]
    report=audit_grade_backtest(rows,as_of=50)
    assert report['rejected']=={'GRADE_SAMPLE_CONFLICT':1,'OUTSIDE_AUDIT_WINDOW':1,'NOT_CONFIRMED':1}
    assert report['observed']==1
    assert report['grades'][0]['closed_reels']==1
    assert report['risk_vs_volume']['break_kg']==800


def test_all_inspections_absent_result_shows_empty_records_not_fake_zero_bias():
    report=audit_grade_backtest([closed('A',confirmed=False)],as_of=50)
    assert report['grades']==[]
    assert report['observed']==0
    assert report['unflagged_kg']==0
    assert report['risk_vs_volume']['review_precision'] is None
    assert report['mass_reconciled']


@pytest.mark.parametrize('bin_edges', [(),(.2,.6,1),(0,.4,.2,1),(0,.2,.2,1),(0,.2,.5)])
def test_reliability_bands_must_partition_probability_mass(bin_edges):
    with pytest.raises(ValueError,match='INVALID_RELIABILITY_BUCKETS'):
        audit_grade_backtest([],as_of=50,bins=bin_edges)


def test_run_uses_the_same_spool_documents_for_audit_and_workbench():
    data=run()
    evidence=data['reconciliation']['grade_reliability']
    audit=data['stages'][5]['records']
    assert evidence['observed']==audit[0]['final_rows']
    assert evidence['rejected']==audit[0]['excluded']
    assert evidence['mass_reconciled']
    grades={row['grade']:row for row in audit if row['audit']=='grade'}
    for row in evidence['grades']:
        assert row['closed_reels']==grades[row['grade']]['count']
        assert row['calibration']['brier']==grades[row['grade']]['brier']
        assert row['verified_bins']
    baseline=next(row for row in audit if row['audit']=='threshold' and row['threshold']==.65)
    assert baseline['missed_kg']==evidence['unflagged_kg']
