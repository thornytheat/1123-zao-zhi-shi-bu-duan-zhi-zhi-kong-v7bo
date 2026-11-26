from dataclasses import replace
import math

import pytest

from sheetgrade.spool_audit.contracts import SpoolInspection, InvalidRow, parse
from sheetgrade.spool_audit.service import evaluate, validate
from sheetgrade.spool_audit import algorithm

def proof(reel='N3', **changes):
    return dict(reel=reel, grade='箱板', break_probability=.8, mass_kg=1200, observed_break=True,
                captured=29, finalized=44, confirmed=True) | changes


def test_no_observed_breaks_has_unavailable_mass_recall():  # TRAP-43
    result = evaluate([proof(observed_break=False)], as_of=50)['records']
    assert result[-1]['mass_recall'] is None
    assert result[-1]['status'] == 'NO_OBSERVED_BREAKS'


def test_brier_score_matches_squared_error_reference():
    cases = [proof(), proof('N9', observed_break=False, break_probability=.2)]
    assert evaluate(cases, as_of=50)['records'][0]['brier'] == pytest.approx(.04)


def test_total_and_missed_mass_reconcile():
    cases = [proof(),proof('N5', break_probability=.4, mass_kg=500)]
    result = evaluate(cases, as_of=50)['records'][-1]
    assert result['lost_kg'] == 1700
    assert result['missed_kg'] == 500
    assert result['mass_recall'] == pytest.approx(1200/1700)


def test_unknown_outcomes_do_not_become_nonbreaks():
    result = evaluate([proof(confirmed=False)], as_of=50)['records'][0]
    assert result['final_rows'] == 0
    assert result['excluded'] == {'NOT_CONFIRMED': 1}
    assert result['brier'] is None


def test_late_completion_excluded_before_scoring():
    result = evaluate([proof(finalized=50), proof('N9', finalized=51)], as_of=50)['records'][0]
    assert result['final_rows'] == 1
    assert result['excluded'] == {'OUTSIDE_AUDIT_WINDOW':1}


def test_conflicting_closures_are_not_two_faults():
    result = evaluate([proof(), proof(observed_break=False)], as_of=50)['records'][0]
    assert result['excluded'] == {'GRADE_SAMPLE_CONFLICT':1}


def test_each_grade_brier_uses_its_own_denominator():
    result = evaluate([proof(), proof('N2', grade='牛皮', observed_break=False)], as_of=50)['records']
    assert all(item['count'] == 1 for item in result if item['audit'] == 'grade')
    assert sorted(round(item['brier'],2) for item in result if item['audit'] == 'grade') == [.04,.64]


def test_threshold_requires_fraction():
    with pytest.raises(ValueError, match='INVALID_SPOOL_REVIEW_THRESHOLDS'):
        evaluate([proof()], as_of=50, thresholds=[90])
