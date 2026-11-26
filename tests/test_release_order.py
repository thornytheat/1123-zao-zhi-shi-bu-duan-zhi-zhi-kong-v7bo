from dataclasses import replace
import math

import pytest

from sheetgrade.release_order.contracts import ReleaseCandidate, InvalidRow, parse
from sheetgrade.release_order.service import evaluate, validate
from sheetgrade.release_order import algorithm

def reel(reel='R1', **options):
    return dict(reel=reel, line='PM-2', grade='纸袋纸', probability=.81, model_ready=True,
                feature_reason='ESTIMATED', mass_kg=1250, critical=False, critical_evidence=True, period=102) | options


def test_confirmed_quality_breach_precedes_larger_expected_loss():  # TRAP-19
    contrast = reel('R2', critical=True, probability=.3, mass_kg=300)
    rows = evaluate([reel(), contrast], capacity=1)['records']
    assert rows[0]['reel'] == 'R2' and rows[0]['review_slot'] == 1
    assert rows[1]['waiting_for_lab'] is True
    assert evaluate([contrast,reel()], capacity=1)['records'] == rows


def test_unverified_telemetry_does_not_become_hard_spec_breach():
    row = evaluate([reel(critical=True, critical_evidence=False)])['records'][0]
    assert row['state'] == '测点复核'
    assert row['reason'] == 'CRITICAL_MEASUREMENT_UNVERIFIED'


def test_larger_reel_ranks_higher_within_policy():
    rows = evaluate([reel('R2', mass_kg=1850), reel()], capacity=1)['records']
    assert rows[0]['reel'] == 'R2'


def test_capacity_waiting_preserves_prior_release_state():
    rows = evaluate([reel('R1'),reel('R2',critical=True),reel('R3',critical=True)], capacity=1)['records']
    assert rows[1]['state'] == '封卷复查'
    assert rows[1]['waiting_for_lab'] is True


def test_low_risk_reel_does_not_use_review_slot():
    row = evaluate([reel(probability=.3)], capacity=1)['records'][0]
    assert row['state'] == '继续生产' and row['review_slot'] is None


def test_per_line_quota_leaves_room_for_other_machine():
    rows = evaluate([reel('R1'), reel('R2'), reel('R3',line='PM-3')], per_line=1)['records']
    assert [item['review_slot'] for item in rows] == [1, None, 2]


def test_latest_sample_supersedes_incomplete_earlier_model():
    rows = evaluate([reel(model_ready=False,period=100),reel(probability=.1,period=111)])['records']
    assert rows[0]['state'] == '继续生产'
    assert rows[0]['replaced_samples'] == 1


def test_equal_period_disagreement_never_allocates_a_slot():
    row = evaluate([reel(), reel(probability=.3)])['records'][0]
    assert row['state'] == '计量隔离' and row['review_slot'] is None
