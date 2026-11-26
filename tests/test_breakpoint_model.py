from dataclasses import replace
import math

import pytest

from sheetgrade.breakpoint_model.contracts import BreakFeature, InvalidRow, parse
from sheetgrade.breakpoint_model.service import evaluate, validate
from sheetgrade.breakpoint_model import algorithm

def vector(n=4, **changes):
    return dict(reel=f'R{n}', line='PM-1', grade='箱板', period=n, consistency_z=(n%10-5)/2,
                vacuum_z=.03*n, speed_z=0, break_within=n%10>=5, observed=n+2) | changes


def history(n=50):
    return [vector(i) for i in range(n)]


def test_cart_probabilities_match_leaf_counts():
    rows = [vector(2), vector(8)]
    safe, danger = evaluate(rows, history=history(), cutoff=60)['records']
    assert safe['probability'] == pytest.approx(1/27)
    assert danger['probability'] == pytest.approx(26/27)
    assert safe['branch'] == ['consistency_z≤-0.250']


def test_single_inference_and_mixed_batch_have_identical_scores():  # TRAP-53
    one = evaluate([vector()], history=history(), cutoff=60)['records'][0]
    both = evaluate([vector(), vector(35, consistency_z=4000)], history=history(), cutoff=60)['records']
    assert one == both[0]
    assert both[1]['probability'] is None


def test_outside_training_range_is_not_a_high_probability():  # TRAP-44
    row = evaluate([vector(vacuum_z=200)], history=history(), cutoff=60)['records'][0]
    assert row['reason'] == 'OUTSIDE_TRAINING_PROFILE'
    assert row['probability'] is None


def test_labels_reported_at_cutoff_are_unavailable():
    rows = history() + [vector(34, reel='LATE', observed=60, break_within=False)]
    assert evaluate([vector()], history=rows, cutoff=60) == evaluate([vector()], history=history(), cutoff=60)


def test_reconfiguration_changes_model_fingerprint():  # TRAP-54
    one = evaluate([vector()], history=history(), cutoff=60, depth=2)['records'][0]
    both = evaluate([vector()], history=history(), cutoff=60, depth=4)['records'][0]
    assert one['fit_id'] != both['fit_id']


def test_tree_uses_partial_order_independent_of_training_permutation():
    rows = history()
    assert evaluate([vector()], history=rows, cutoff=60) == evaluate([vector()], history=list(reversed(rows)), cutoff=60)


def test_minimum_leaf_prevents_split_when_sample_small():
    root = algorithm.build_tree([parse(vector(n)) for n in range(8)], 4, 5)
    assert root.feature is None
    assert root.rate == .4


def test_zero_rows_leave_a_reviewable_reason():
    row = evaluate([vector()], history=[], cutoff=60)['records'][0]
    assert row['support'] == 0 and row['probability'] is None
