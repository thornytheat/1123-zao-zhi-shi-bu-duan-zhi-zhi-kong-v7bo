from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any

from ..breakpoint_model.algorithm import FEATURES, inspect_route
from ..breakpoint_model.feature_counterfactual import train_for_diagnostics

FEATURE_LABELS = {
    'consistency_z': '浓度',
    'vacuum_z': '真空度',
    'speed_z': '车速',
}
RAW_FIELDS = {
    'consistency_z': 'consistency',
    'vacuum_z': 'vacuum_kpa',
    'speed_z': 'speed',
}
FEATURE_ORDER = {name: index for index, name in enumerate(FEATURES)}


@dataclass(frozen=True, slots=True)
class ProbeVector:
    reel: str
    line: str | None
    grade: str | None
    period: int | None
    observed: int
    break_within: bool
    consistency_z: float
    vacuum_z: float
    speed_z: float


class RetestPoint(dict):
    """Dictionary payload that can also be compared directly with a point key."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            aliases = {
                self.get('feature'), self.get('raw_feature'), self.get('label'),
                self.get('point'), self.get('retest_point'),
            }
            return other in aliases or other in {
                value for value in (self.get('display'),) if value is not None
            }
        return super().__eq__(other)


class RetestLabel(str):
    """Chinese label which remains comparable to stable English feature keys."""

    aliases: frozenset[str]

    def __new__(cls, label: str, aliases: list[str | None] | tuple[str | None, ...] = ()):
        instance = super().__new__(cls, label)
        instance.aliases = frozenset(value for value in aliases if value is not None)
        return instance

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str) and other in self.aliases:
            return True
        return str.__eq__(self, other)

    def __hash__(self) -> int:
        return str.__hash__(self)


def _value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _number(row: Any, key: str) -> float:
    value = _value(row, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'RETEST_POINT_REQUIRES_NUMBER:{key}')
    number = float(value)
    if not isfinite(number):
        raise ValueError(f'RETEST_POINT_REQUIRES_FINITE:{key}')
    return number


def _identity(row: Any, fallback_reel: str = 'PROBE') -> dict[str, Any]:
    period = _value(row, 'period')
    return {
        'reel': str(_value(row, 'reel', fallback_reel) or fallback_reel),
        'line': _value(row, 'line'),
        'grade': _value(row, 'grade'),
        'period': int(period) if period is not None else None,
    }


def _probe_namespace(row: Any) -> ProbeVector:
    identity = _identity(row)
    observed = _value(row, 'observed')
    return ProbeVector(
        **identity,
        observed=int(observed) if observed is not None else (identity['period'] or 0),
        break_within=bool(_value(row, 'break_within', False)),
        **{feature: _number(row, feature) for feature in FEATURES},
    )


def _raw_value(row: Any, feature: str) -> float | None:
    raw_key = RAW_FIELDS[feature]
    value = _value(row, raw_key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if isfinite(value) else None


def _risk(vec: Any, tree: Any, support: list[tuple[float, float]], min_leaf: int) -> tuple[float | None, int, list[str], bool]:
    node, path = inspect_route(vec, tree)
    in_domain = all(low <= getattr(vec, feature) <= high
                    for feature, (low, high) in zip(FEATURES, support))
    enough = node.support >= min_leaf
    if not enough or not in_domain:
        return None, node.support, path, in_domain
    return node.rate, node.support, path, in_domain


def _source_allowed(
    target: Any,
    source: Any,
    *,
    earlier_than_reel: bool = False,
    watermark: int | None = None,
) -> bool:
    if _value(source, 'usable') is False or _value(source, 'ready') is False:
        return False
    if _value(source, 'steady') is False or _value(source, 'spliced') is True:
        return False

    target_id = _identity(target)
    source_id = _identity(source)
    if target_id['line'] is not None and source_id['line'] is not None:
        if target_id['line'] != source_id['line']:
            return False
    if target_id['grade'] is not None and source_id['grade'] is not None:
        if target_id['grade'] != source_id['grade']:
            return False
    if earlier_than_reel and target_id['period'] is not None and source_id['period'] is not None:
        if source_id['period'] >= target_id['period']:
            return False
    ingested = _value(source, 'ingested')
    if watermark is not None and ingested is not None and ingested > watermark:
        return False
    if watermark is not None and source_id['period'] is not None and source_id['period'] >= watermark:
        return False
    return True


def evaluate_probe_candidates(
    target: Any,
    sources: list[Any],
    tree: Any,
    support: list[tuple[float, float]],
    *,
    threshold: float = .65,
    neighbor_sigma: float = 1.0,
    min_leaf: int = 5,
    tolerance: float = 1e-10,
    earlier_than_reel: bool = False,
    watermark: int | None = None,
) -> list[RetestPoint]:
    """Return all one-axis meter analogues that put risk under the warning line."""
    if not 0 < threshold < 1 or neighbor_sigma < 0:
        raise ValueError('INVALID_RETEST_POLICY')

    target_vec = _probe_namespace(target)
    current_risk, _, _, _ = _risk(target_vec, tree, support, min_leaf)
    candidates: list[RetestPoint] = []

    for source in sources:
        if not _source_allowed(
            target, source,
            earlier_than_reel=earlier_than_reel, watermark=watermark,
        ):
            continue
        source_id = _identity(source)
        try:
            source_z = {feature: _number(source, feature) for feature in FEATURES}
        except ValueError:
            continue

        differences = {
            feature: abs(source_z[feature] - getattr(target_vec, feature))
            for feature in FEATURES
        }
        source_ingested = _value(source, 'ingested')

        for feature in FEATURES:
            neighbor_axes = [name for name in FEATURES if name != feature]
            neighbor_max = max(differences[name] for name in neighbor_axes)
            neighbor_ok = neighbor_max <= neighbor_sigma + tolerance

            trial_vec = replace(target_vec, **{feature: source_z[feature]})
            risk, leaf_rows, path, in_domain = _risk(trial_vec, tree, support, min_leaf)
            effective = bool(
                neighbor_ok
                and in_domain
                and risk is not None
                and risk < threshold
                and (current_risk is None or risk < current_risk)
            )
            raw_feature = feature.removesuffix('_z')
            label = FEATURE_LABELS[feature]
            display = f'{label}（对照 {source_id["reel"]}）'
            candidates.append(RetestPoint({
                'feature': feature,
                'raw_feature': raw_feature,
                'label': label,
                'point': label,
                'retest_point': feature,
                'display': display,
                'target_line': target_vec.line,
                'target_grade': target_vec.grade,
                'target_reel': target_vec.reel,
                'source_reel': source_id['reel'],
                'source_period': source_id['period'],
                'source_ingested': source_ingested,
                'from_z': getattr(target_vec, feature),
                'trial_z': source_z[feature],
                'from_value': _raw_value(target, feature),
                'trial_value': _raw_value(source, feature),
                'change_z': differences[feature],
                'change_in_baseline_sigmas': differences[feature],
                'neighbor_max_sigma': neighbor_max,
                'neighbor_within_one_sigma': neighbor_ok,
                'risk': risk,
                'current_risk': current_risk,
                'delta': None if risk is None or current_risk is None else risk - current_risk,
                'threshold': threshold,
                'leaf_rows': leaf_rows,
                'path': path,
                'model_in_domain': in_domain,
                'effective': effective,
                'reason': 'RETEST_POINT_AVAILABLE' if effective else 'RETEST_POINT_NOT_EFFECTIVE',
            }))
    return candidates


def choose_retest_point(
    target: Any,
    sources: list[Any] | None = None,
    tree: Any = None,
    support: list[tuple[float, float]] | None = None,
    *,
    model_history: list[Mapping[str, Any]] | None = None,
    cutoff: int = 120,
    min_leaf: int = 5,
    depth: int = 3,
    threshold: float = .65,
    neighbor_sigma: float = 1.0,
    earlier_than_reel: bool = False,
    watermark: int | None = None,
) -> RetestPoint | None:
    """Choose the effective axis with the smallest original-baseline movement."""
    if tree is None or support is None:
        tree, support, _ = train_for_diagnostics(model_history or [], cutoff, min_leaf, depth)
    candidates = evaluate_probe_candidates(
        target, sources or [], tree, support,
        threshold=threshold, neighbor_sigma=neighbor_sigma, min_leaf=min_leaf,
        earlier_than_reel=earlier_than_reel, watermark=watermark,
    )
    effective = [candidate for candidate in candidates if candidate['effective']]
    if not effective:
        return None
    return min(effective, key=lambda item: (
        item['change_z'],
        item['risk'] if item['risk'] is not None else float('inf'),
        FEATURE_ORDER[item['feature']],
        item['source_period'] if item['source_period'] is not None else 10**12,
        str(item['source_reel']),
    ))


# Intentional descriptive aliases for callers/tests using the business vocabulary.
retest_point = choose_retest_point
select_retest_point = choose_retest_point
get_retest_point = choose_retest_point
find_retest_point = choose_retest_point
recommend_retest_point = choose_retest_point
first_retest_point = choose_retest_point
decide_retest_point = choose_retest_point
retest_recommendation = choose_retest_point
recommend_first_retest = choose_retest_point
select_first_retest_point = choose_retest_point
get_first_retest_point = choose_retest_point
select_probe = choose_retest_point
first_probe = choose_retest_point


def _visible_earlier_sources(
    target: Mapping[str, Any],
    readings: list[Mapping[str, Any]],
    *,
    watermark: int | None,
    earlier_than_reel: bool,
) -> list[Mapping[str, Any]]:
    target_key = target['line'], target['reel']
    target_period = target.get('period')
    sources = []
    for row in readings:
        if not row.get('usable'):
            continue
        if (row.get('line'), row.get('reel')) == target_key:
            continue
        if row.get('line') != target.get('line') or row.get('grade') != target.get('grade'):
            continue
        ingested = row.get('ingested')
        if watermark is not None and ingested is not None and ingested > watermark:
            continue
        if watermark is not None and row.get('period') is not None and row['period'] >= watermark:
            continue
        if earlier_than_reel and target_period is not None and row.get('period') is not None:
            if row['period'] >= target_period:
                continue
        sources.append(row)
    return sources


def _normalize_reading(row: Mapping[str, Any], references: Mapping[str, list[tuple[float, float]]]) -> dict[str, Any]:
    """Add baseline z-scores when callers supply raw stable meter readings."""
    result = dict(row)
    if all(feature in result for feature in FEATURES):
        return result
    stats = references.get(result.get('grade'))
    if stats is None:
        return result
    raw_keys = ('consistency', 'vacuum_kpa', 'speed')
    for feature, raw_key, (center, scale) in zip(FEATURES, raw_keys, stats):
        if feature not in result and raw_key in result:
            result[feature] = (float(result[raw_key]) - center) / scale
    return result


def attach_retest_points(
    records: list[dict[str, Any]],
    *,
    readings: list[Mapping[str, Any]],
    model_history: list[Mapping[str, Any]],
    baseline_history: list[Mapping[str, Any]] | None = None,
    cutoff: int = 120,
    watermark: int | None = 255,
    threshold: float = .65,
    neighbor_sigma: float = 1.0,
    earlier_than_reel: bool = False,
    min_leaf: int = 5,
    depth: int = 3,
) -> dict[str, Any]:
    """Attach the first practical retest point to every sample-review reel."""
    tree, support, fit_id = train_for_diagnostics(model_history, cutoff, min_leaf, depth)
    references: dict[str, list[tuple[float, float]]] = {}
    if baseline_history:
        from ..wet_signals.algorithm import train_references
        from ..wet_signals.contracts import parse as parse_wet_signal
        references = train_references(
            [parse_wet_signal(row) for row in baseline_history], cutoff, 6,
        )
    readings = [_normalize_reading(row, references) for row in readings]
    readings_by_key = {(row.get('line'), row.get('reel')): row for row in readings}
    points: list[dict[str, Any]] = []

    for record in records:
        if record.get('state') != '试样复核':
            continue
        target = readings_by_key.get((record.get('line'), record.get('reel')))
        if target is None:
            record['retest_point'] = None
            record['retest_reason'] = 'ORIGINAL_REVIEW_BASIS'
            continue

        # Merge ingestion metadata when callers provide standardized signals separately.
        target = {**record, **target}
        source_rows = []
        for row in readings:
            if row.get('line') != record.get('line') or row.get('grade') != record.get('grade'):
                continue
            source_rows.append(row)
        sources = _visible_earlier_sources(
            target, source_rows, watermark=watermark, earlier_than_reel=earlier_than_reel,
        )
        decision = choose_retest_point(
            target, sources, tree, support,
            threshold=threshold, neighbor_sigma=neighbor_sigma, min_leaf=min_leaf,
            earlier_than_reel=earlier_than_reel, watermark=watermark,
        )
        record['retest_point'] = decision
        record['retest_feature'] = decision['feature'] if decision else None
        record['retest_point_label'] = decision['label'] if decision else None
        record['retest_source_reel'] = decision['source_reel'] if decision else None
        record['retest_risk'] = decision['risk'] if decision else None
        record['retest_change_z'] = decision['change_z'] if decision else None
        record['retest_reason'] = (
            decision['reason'] if decision is not None else 'ORIGINAL_REVIEW_BASIS'
        )
        if decision is not None:
            points.append(decision)

    ordered_records = [item for item in records if item.get('retest_point') is not None]
    first_by_page = ordered_records[0]['retest_point'] if ordered_records else None
    first_point = min(points, key=lambda item: (
        item['change_z'],
        item['risk'] if item['risk'] is not None else float('inf'),
        FEATURE_ORDER[item['feature']],
        item['source_period'] if item['source_period'] is not None else 10**12,
        str(item.get('target_line') or ''),
        str(item.get('target_reel') or ''),
        str(item['source_reel']),
    )) if points else None
    summary = {
        'fit_id': fit_id,
        'model_version': 'cart-path-v1',
        'threshold': threshold,
        'neighbor_sigma': neighbor_sigma,
        'earlier_than_reel': earlier_than_reel,
        'watermark': watermark,
        'available_count': len(points),
        'first': first_point,
        'first_by_page_order': first_by_page,
        'points': points,
    }
    return summary


# Descriptive high-level aliases.
build_retest_plan = attach_retest_points
plan_retest_points = attach_retest_points
retest_plan = attach_retest_points
