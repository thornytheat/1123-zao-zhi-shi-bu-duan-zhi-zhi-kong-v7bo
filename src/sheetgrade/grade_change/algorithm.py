from __future__ import annotations

from .contracts import GradeWindow

from collections import defaultdict
from dataclasses import asdict


def revision_windows(records, available_at):
    active = defaultdict(list)
    for window in records:
        if window.recorded <= available_at:
            active[window.line, window.order].append(window)
    ledger = []
    for key, candidates in sorted(active.items()):
        revision = max(item.revision for item in candidates)
        eligible = [item for item in candidates if item.revision == revision]
        contents = {(item.grade, item.effective, item.until, item.stabilize) for item in eligible}
        row = min(eligible, key=lambda value: (value.recorded, value.effective, value.grade, value.until, value.stabilize))
        if len(contents) > 1:
            reason = 'GRADE_REVISION_CONFLICT'
        elif row.effective >= row.until or row.effective + row.stabilize > row.until:
            reason = 'INVALID_GRADE_INTERVAL'
        else:
            reason = 'ACTIVE_GRADE_WINDOW'
        ledger.append(asdict(row) | {'usable': reason == 'ACTIVE_GRADE_WINDOW', 'reason': reason,
                                     'superseded': len(candidates) - 1})
    return ledger


def key_overlaps(ledger):
    blocked = defaultdict(set)
    usable = [row for row in ledger if row['usable']]
    for index, row in enumerate(usable):
        for other in usable[index+1:]:
            if row['line'] != other['line']:
                continue
            if row['effective'] < other['until'] and other['effective'] < row['until']:
                blocked[row['line'], row['order']].add(other['order'])
                blocked[other['line'], other['order']].add(row['order'])
    return blocked


def match_shift(ledger, line, period):
    candidates = [row for row in ledger if row['line'] == line and row['effective'] <= period < row['until']]
    if not candidates:
        return {'grade': None, 'order': None, 'steady': False, 'grade_reason': 'GRADE_MISSING'}
    if len(candidates) != 1 or not candidates[0]['usable']:
        return {'grade': None, 'order': None, 'steady': False, 'grade_reason': 'GRADE_AMBIGUOUS'}
    plan = candidates[0]
    stable = period >= plan['effective'] + plan['stabilize']
    return {'grade': plan['grade'], 'order': plan['order'], 'steady': stable,
            'grade_reason': 'STABLE_GRADE' if stable else 'TRANSITION_HOLD'}


def calculate(records, *, available_at):
    ledger = revision_windows(records, available_at)
    clashes = key_overlaps(ledger)
    return [row | {'conflicts': sorted(clashes[row['line'], row['order']])} for row in ledger]
