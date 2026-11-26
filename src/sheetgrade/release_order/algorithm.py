from __future__ import annotations

from .contracts import ReleaseCandidate

from collections import Counter, defaultdict
from dataclasses import asdict


def work_order(row):
    return row.line, row.reel


def stable_reel(records):
    groups = defaultdict(list)
    for row in records:
        groups[work_order(row)].append(row)
    output = []
    for identity, candidates in groups.items():
        top = max(item.period for item in candidates)
        last = {item for item in candidates if item.period == top}
        representative = min(last, key=lambda item: (item.grade, item.feature_reason, item.mass_kg, item.probability,
                                                       item.model_ready, item.critical, item.critical_evidence))
        output.append((representative, len(last) > 1, len(candidates) - 1))
    return output


def classify(row, contradiction, threshold):
    if contradiction:
        return '计量隔离', 'REEL_DATA_DISAGREEMENT', 0
    if row.critical and row.critical_evidence:
        return '封卷复查', 'QUALITY_SPEC_BREACH', 4
    if row.critical and not row.critical_evidence:
        return '测点复核', 'CRITICAL_MEASUREMENT_UNVERIFIED', 3
    if not row.model_ready:
        return '测点复核', row.feature_reason, 2
    if row.probability >= threshold:
        return '试样复核', 'ESTIMATED_BREAK_PROBABILITY', 1
    return '继续生产', 'IN_CONTROL', 0


def calculate(records, *, capacity=5, threshold=.65, per_line=3):
    if capacity < 1 or per_line < 1 or not 0 < threshold < 1:
        raise ValueError('INVALID_RELEASE_SHIFT_POLICY')
    cases = []
    for row, contradicted, replaced in stable_reel(records):
        state, reason, priority = classify(row, contradicted, threshold)
        cases.append(asdict(row) | {'state': state, 'reason': reason, 'priority': priority,
                                    'replaced_samples': replaced, 'review_slot': None})
    cases.sort(key=lambda item: (-item['priority'], -item['probability']*item['mass_kg'],
                                 item['period'], item['line'], item['reel']))
    reviewed = 0
    by_line = Counter()
    for item in cases:
        if item['priority'] == 0:
            continue
        if by_line[item['line']] == per_line or reviewed == capacity:
            item['waiting_for_lab'] = True
        else:
            reviewed += 1
            item['review_slot'] = reviewed
            by_line[item['line']] += 1
            item['waiting_for_lab'] = False
    return cases
