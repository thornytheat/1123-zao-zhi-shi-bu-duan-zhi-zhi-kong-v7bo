from dataclasses import replace
import math

import pytest

from sheetgrade.grade_change.contracts import GradeWindow, InvalidRow, parse
from sheetgrade.grade_change.service import evaluate, validate
from sheetgrade.grade_change import algorithm

def order(name='ERP-8', **changes):
    return dict(line='PM-2', grade='灰底白板', order=name, effective=20, until=50, stabilize=3, recorded=10, revision=1) | changes


def test_exact_window_end_belongs_to_next_grade():  # TRAP-23
    newer = order('ERP-12', effective=50, until=65, grade='箱板')
    rows = evaluate([order(), newer], available_at=18)['records']
    assert algorithm.match_shift(rows, 'PM-2', 50)['grade'] == '箱板'
    assert algorithm.match_shift(rows, 'PM-2', 49)['grade'] == '灰底白板'


def test_overlapping_effective_windows_are_flagged_on_both_sides():  # TRAP-25
    newer = order('ERP-12', effective=46, until=65)
    rows = evaluate([order(), newer], available_at=20)['records']
    assert [row['conflicts'] for row in rows] == [['ERP-8'], ['ERP-12']]
    assert algorithm.match_shift(rows, 'PM-2', 47)['grade_reason'] == 'GRADE_AMBIGUOUS'


def test_stabilization_boundary_is_inclusive():
    rows = evaluate([order()], available_at=16)['records']
    assert algorithm.match_shift(rows, 'PM-2', 22)['steady'] is False
    assert algorithm.match_shift(rows, 'PM-2', 23)['steady'] is True


def test_grade_update_recorded_later_does_not_change_decision():
    updated = order(revision=3, grade='牛皮', recorded=17)
    rows = evaluate([order(), updated], available_at=16)['records']
    assert rows[0]['grade'] == '灰底白板'


def test_distinct_machines_can_run_same_cutoff_times():
    rows = evaluate([order(), order(line='PM-1')], available_at=16)['records']
    assert all(row['conflicts'] == [] for row in rows)


def test_stabilization_cannot_outlive_the_run():
    rows = evaluate([order(stabilize=31)], available_at=16)['records']
    assert rows[0]['reason'] == 'INVALID_GRADE_INTERVAL'


def test_revision_collision_is_ambiguous():
    rows = evaluate([order(), order(grade='无涂布')], available_at=16)['records']
    assert rows[0]['reason'] == 'GRADE_REVISION_CONFLICT'
    assert algorithm.match_shift(rows, 'PM-2', 39)['steady'] is False


def test_unmapped_roll_is_held():
    rows = evaluate([order()], available_at=16)['records']
    assert algorithm.match_shift(rows, 'PM-4', 30)['grade_reason'] == 'GRADE_MISSING'
