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
class SpoolInspection:
    reel: str
    grade: str
    break_probability: float
    mass_kg: float
    observed_break: bool
    captured: int
    finalized: int
    confirmed: bool


def parse(values: Mapping[str, Any]) -> SpoolInspection:
    if not isinstance(values, Mapping):
        raise InvalidRow('spool_audit', 'EXPECTED_OBJECT')
    reel = text(values, 'reel', 'spool_audit.reel')
    grade = text(values, 'grade', 'spool_audit.grade')
    break_probability = number(values, 'break_probability', 0, 1, 'spool_audit.break_probability')
    mass_kg = number(values, 'mass_kg', 1, 100000, 'spool_audit.mass_kg')
    observed_break = flag(values, 'observed_break', 'spool_audit.observed_break')
    captured = integer(values, 'captured', 0, 10000000, 'spool_audit.captured')
    finalized = integer(values, 'finalized', 0, 10000000, 'spool_audit.finalized')
    confirmed = flag(values, 'confirmed', 'spool_audit.confirmed')
    return SpoolInspection(
        reel=reel,
        grade=grade,
        break_probability=break_probability,
        mass_kg=mass_kg,
        observed_break=observed_break,
        captured=captured,
        finalized=finalized,
        confirmed=confirmed,
    )
