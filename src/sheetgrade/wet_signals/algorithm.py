from __future__ import annotations

from .contracts import WetSignal

from collections import defaultdict
from dataclasses import asdict
from math import fsum, sqrt


def stable_scale(values, minimum):
    center = 0.0
    moment = 0.0
    count = 0
    for value in values:
        count += 1
        delta = value - center
        center += delta / count
        moment += delta * (value - center)
    return center, max(minimum, sqrt(max(0, moment) / count)) if count else minimum


def train_references(history, cutoff, minimum):
    candidates = defaultdict(list)
    for row in sorted(history, key=lambda item: (item.grade, item.line, item.period, item.reel)):
        if row.steady and not row.spliced and row.period < cutoff:
            candidates[row.grade].append(row)
    return {
        grade: [stable_scale([getattr(row, material) for row in group], least)
                for material, least in [('consistency', .01), ('vacuum_kpa', .5), ('speed', 8)]]
        for grade, group in candidates.items() if len(group) >= minimum
    }


def process_signals(records, references, max_previous_gap):
    previous = {}
    for row in sorted(records, key=lambda item: (item.line, item.period, item.reel, item.grade)):
        calibration = references.get(row.grade)
        aside = previous.get((row.line, row.grade))
        if not row.steady or row.spliced:
            previous.pop((row.line, row.grade), None)
            reason = 'GRADE_TRANSITION' if not row.steady else 'SPLICE_MASKED'
        elif calibration is None:
            reason = 'MISSING_GRADE_REFERENCE'
        else:
            reason = 'FEATURE_READY'
        current = asdict(row) | {'reason': reason, 'usable': reason == 'FEATURE_READY'}
        if reason == 'FEATURE_READY':
            previous[row.line, row.grade] = row
            valid_prior = aside and 0 < row.period - aside.period <= max_previous_gap
            delta = (row.vacuum_kpa - aside.vacuum_kpa) / (row.period - aside.period) if valid_prior else None
            axes = [row.consistency, row.vacuum_kpa, row.speed]
            scaled = [(value - center) / scale for value, (center, scale) in zip(axes, calibration)]
            current |= {'consistency_z': scaled[0], 'vacuum_z': scaled[1], 'speed_z': scaled[2],
                        'vacuum_slope': delta, 'max_abs_z': max(map(abs, scaled))}
        yield current


def calculate(records, *, history, cutoff, minimum=6, max_previous_gap=20):
    from .contracts import parse
    if minimum < 2 or max_previous_gap < 1:
        raise ValueError('INVALID_GRADE_FEATURE_PARAMS')
    stats = train_references([parse(row) for row in history], cutoff, minimum)
    return list(process_signals(records, stats, max_previous_gap))
