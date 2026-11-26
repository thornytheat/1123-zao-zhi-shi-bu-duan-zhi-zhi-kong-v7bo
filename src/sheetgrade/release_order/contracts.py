from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


def number(row: Mapping, key: str, low: float, high: float, field: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise InvalidRow(field, 'EXPECTED_NUMBER')
    if not low <= value <= high or not math.isfinite(value):
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return float(value)


def integer(row: Mapping, key: str, low: int, high: int, field: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise InvalidRow(field, 'EXPECTED_INTEGER')
    if not low <= value <= high:
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return value


def text(row: Mapping, key: str, field: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRow(field, 'EXPECTED_NONEMPTY_TEXT')
    if len(value.strip()) > 80:
        raise InvalidRow(field, 'TEXT_TOO_LONG')
    return value.strip()


def flag(row: Mapping, key: str, field: str) -> bool:
    value = row.get(key)
    if type(value) is not bool:
        raise InvalidRow(field, 'EXPECTED_FLAG')
    return value


@dataclass(frozen=True, slots=True)
class ReleaseCandidate:
    reel: str
    line: str
    grade: str
    probability: float
    model_ready: bool
    feature_reason: str
    mass_kg: float
    critical: bool
    critical_evidence: bool
    period: int


def parse(values: Mapping[str, Any]) -> ReleaseCandidate:
    if not isinstance(values, Mapping):
        raise InvalidRow('release_order', 'EXPECTED_OBJECT')
    reel = text(values, 'reel', 'release_order.reel')
    line = text(values, 'line', 'release_order.line')
    grade = text(values, 'grade', 'release_order.grade')
    probability = number(values, 'probability', 0, 1, 'release_order.probability')
    model_ready = flag(values, 'model_ready', 'release_order.model_ready')
    feature_reason = text(values, 'feature_reason', 'release_order.feature_reason')
    mass_kg = number(values, 'mass_kg', 1, 100000, 'release_order.mass_kg')
    critical = flag(values, 'critical', 'release_order.critical')
    critical_evidence = flag(values, 'critical_evidence', 'release_order.critical_evidence')
    period = integer(values, 'period', 0, 10000000, 'release_order.period')
    return ReleaseCandidate(
        reel=reel,
        line=line,
        grade=grade,
        probability=probability,
        model_ready=model_ready,
        feature_reason=feature_reason,
        mass_kg=mass_kg,
        critical=critical,
        critical_evidence=critical_evidence,
        period=period,
    )
