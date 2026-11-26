from __future__ import annotations

from .contracts import SpoolInspection

from collections import defaultdict
from math import fsum


def final_spools(records, as_of):
    groups = defaultdict(set)
    unavailable = defaultdict(int)
    for row in records:
        if not row.confirmed:
            unavailable['NOT_CONFIRMED'] += 1
        elif not row.captured <= row.finalized <= as_of:
            unavailable['OUTSIDE_AUDIT_WINDOW'] += 1
        else:
            groups[row.reel].add(row)
    retained = []
    for reel, matches in sorted(groups.items()):
        if len(matches) != 1:
            unavailable['GRADE_SAMPLE_CONFLICT'] += 1
        else:
            retained.extend(matches)
    return retained, dict(unavailable)


def brier_score(rows):
    return fsum((row.break_probability - row.observed_break)**2 for row in rows) / len(rows) if rows else None


def detect_losses(rows, threshold):
    lost = [row.mass_kg for row in rows if row.observed_break]
    unflagged = fsum(row.mass_kg for row in rows if row.observed_break and row.break_probability < threshold)
    reviews = sum(row.break_probability >= threshold for row in rows)
    avoided = fsum(lost) - unflagged
    return {'threshold': threshold, 'reviews': reviews, 'breaks': len(lost), 'lost_kg': fsum(lost),
            'missed_kg': unflagged, 'mass_recall': avoided/fsum(lost) if lost else None,
            'status': 'OBSERVED_BREAKS' if lost else 'NO_OBSERVED_BREAKS'}


def calculate(records, *, as_of, thresholds=(.2,.35,.5,.65,.8)):
    if not thresholds or not all(0 < item < 1 for item in thresholds):
        raise ValueError('INVALID_SPOOL_REVIEW_THRESHOLDS')
    rows, ignored = final_spools(records, as_of)
    groups = defaultdict(list)
    for record in rows:
        groups[record.grade].append(record)
    evidence = [{'audit': 'shift', 'final_rows': len(rows), 'brier': brier_score(rows), 'excluded': ignored}]
    evidence.extend({'audit': 'grade', 'grade': grade, 'count': len(values), 'brier': brier_score(values)}
                    for grade, values in sorted(groups.items()))
    evidence.extend({'audit': 'threshold'} | detect_losses(rows, threshold) for threshold in thresholds)
    return evidence
