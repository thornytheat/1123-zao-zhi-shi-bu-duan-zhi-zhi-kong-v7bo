from __future__ import annotations

from .contracts import BreakFeature

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite

FEATURES = ('consistency_z','vacuum_z','speed_z')


@dataclass(frozen=True, slots=True)
class Branch:
    support: int
    defects: int
    feature: str | None = None
    midpoint: float | None = None
    left: Branch | None = None
    right: Branch | None = None

    @property
    def rate(self):
        return (self.defects + 1) / (self.support + 2)


def impurity(positive, total):
    if not total:
        return 0
    p = positive / total
    return 2*p*(1-p)


def best_separator(records, minimum_leaf):
    answer = (0, None, None)
    total = len(records)
    positives = sum(row.break_within for row in records)
    prior = impurity(positives, total)
    for key in FEATURES:
        ordered = sorted(records, key=lambda row: getattr(row, key))
        so_far = 0
        for at in range(1, total):
            before, after = ordered[at-1:at+1]
            so_far += before.break_within
            if min(at, total-at) < minimum_leaf or getattr(before, key) == getattr(after, key):
                continue
            weighted = (at*impurity(so_far, at) + (total-at)*impurity(positives-so_far, total-at))/total
            if prior-weighted > answer[0] + 1e-12:
                answer = (prior-weighted, key, (getattr(before, key)+getattr(after,key))/2)
    return answer


def build_tree(rows, remaining_depth, minimum_leaf):
    positives = sum(row.break_within for row in rows)
    fallback = Branch(len(rows), positives)
    if not remaining_depth or not 0 < positives < len(rows):
        return fallback
    gain, key, cut = best_separator(rows, minimum_leaf)
    if gain < .012 or key is None:
        return fallback
    left = [row for row in rows if getattr(row, key) <= cut]
    right = [row for row in rows if getattr(row, key) > cut]
    return Branch(len(rows), positives, key, cut, build_tree(left, remaining_depth-1, minimum_leaf),
                  build_tree(right, remaining_depth-1, minimum_leaf))


def inspect_route(row, root):
    directions = []
    while root.feature is not None:
        go_left = getattr(row, root.feature) <= root.midpoint
        directions.append(f'{root.feature}{"≤" if go_left else ">"}{root.midpoint:.3f}')
        root = root.left if go_left else root.right
    return root, directions


def local_support(training):
    return [(min(getattr(row, name) for row in training) - 1, max(getattr(row, name) for row in training) + 1)
            for name in FEATURES] if training else []


def calculate(records, *, history, cutoff, minimum_leaf=5, depth=3):
    from .contracts import parse
    if not 1 <= depth <= 6 or minimum_leaf < 2:
        raise ValueError('INVALID_BREAK_MODEL_LIMITS')
    source = [parse(record) for record in history]
    history = sorted({row for row in source if row.period <= row.observed < cutoff},
                     key=lambda row: (row.period, row.line, row.reel, row.observed, row.break_within,
                                      row.consistency_z, row.vacuum_z, row.speed_z))
    root = build_tree(history, depth, minimum_leaf)
    scope = local_support(history)
    fingerprint = sha256(repr((history, cutoff, minimum_leaf, depth, FEATURES)).encode()).hexdigest()[:16]
    results = []
    for row in records:
        leaf, decisions = inspect_route(row, root)
        allowed = leaf.support >= minimum_leaf and all(lo <= getattr(row, key) <= hi
                                                        for key, (lo, hi) in zip(FEATURES, scope))
        results.append(asdict(row) | {'probability': leaf.rate if allowed else None, 'support': leaf.support,
                                      'training_count': root.support, 'branch': decisions, 'fit_id': fingerprint,
                                      'reason': 'ESTIMATED' if allowed else 'OUTSIDE_TRAINING_PROFILE'})
    return results
