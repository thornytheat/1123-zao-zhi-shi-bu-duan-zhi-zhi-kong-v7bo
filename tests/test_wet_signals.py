from dataclasses import replace
import math

import pytest

from sheetgrade.wet_signals.contracts import WetSignal, InvalidRow, parse
from sheetgrade.wet_signals.service import evaluate, validate
from sheetgrade.wet_signals import algorithm

def measurement(index=30, **changes):
    return dict(reel=f'R{index}', line='PM-1', grade='箱板', period=index, vacuum_kpa=38,
                consistency=.76, speed=1030, steady=True, spliced=False) | changes


def history():
    return [measurement(i) for i in range(1, 10)]


def test_welford_stable_for_constant_and_nearly_constant_offset():  # TRAP-32
    center, scale = algorithm.stable_scale([1e8-.1, 1e8, 1e8+.1], .01)
    assert center == pytest.approx(1e8)
    assert scale == pytest.approx(math.sqrt(.02/3))
    assert algorithm.stable_scale([46]*100, .5) == (46, .5)


def test_future_calibration_cannot_change_earlier_signal():  # TRAP-42
    data = history()
    affected = data+[measurement(10, vacuum_kpa=50)]
    one = evaluate([measurement(vacuum_kpa=42)], history=data, cutoff=10)
    two = evaluate([measurement(vacuum_kpa=42)], history=affected, cutoff=10)
    assert one == two
    assert one['records'][0]['vacuum_z'] == 8


def test_sample_splice_removes_short_lag_history():
    docs = [measurement(30), measurement(33, spliced=True), measurement(35, vacuum_kpa=43)]
    evidence = evaluate(docs, history=history(), cutoff=10)['records']
    assert evidence[1]['reason'] == 'SPLICE_MASKED'
    assert evidence[-1]['vacuum_slope'] is None


def test_vacuum_rate_is_normalized_by_minutes():
    docs = [measurement(30), measurement(34, vacuum_kpa=42)]
    assert evaluate(docs, history=history(), cutoff=10)['records'][-1]['vacuum_slope'] == 1


def test_gap_supplies_no_slope_rather_than_zero():
    docs = [measurement(30), measurement(51, vacuum_kpa=42)]
    assert evaluate(docs, history=history(), cutoff=10)['records'][-1]['vacuum_slope'] is None


def test_no_fallback_from_heterogeneous_paper_grade():
    row = evaluate([measurement(grade='无涂布')], history=history(), cutoff=10)['records'][0]
    assert row['reason'] == 'MISSING_GRADE_REFERENCE'
    assert row['usable'] is False


def test_pm2_previous_signal_does_not_leak_across_machine():
    docs = [measurement(30, line='PM-1'), measurement(31, line='PM-2')]
    result = evaluate(docs, history=history(), cutoff=10)['records'][-1]
    assert result['vacuum_slope'] is None


def test_transition_drives_rejection_before_missing_reference():
    row = evaluate([measurement(grade='?', steady=False)], history=history(), cutoff=10)['records'][0]
    assert row['reason'] == 'GRADE_TRANSITION'
