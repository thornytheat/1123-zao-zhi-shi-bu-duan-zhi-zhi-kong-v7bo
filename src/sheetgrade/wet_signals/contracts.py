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
class WetSignal:
    reel: str
    line: str
    grade: str
    period: int
    vacuum_kpa: float
    consistency: float
    speed: float
    steady: bool
    spliced: bool


def parse(values: Mapping[str, Any]) -> WetSignal:
    if not isinstance(values, Mapping):
        raise InvalidRow('wet_signals', 'EXPECTED_OBJECT')
    reel = text(values, 'reel', 'wet_signals.reel')
    line = text(values, 'line', 'wet_signals.line')
    grade = text(values, 'grade', 'wet_signals.grade')
    period = integer(values, 'period', 0, 10000000, 'wet_signals.period')
    vacuum_kpa = number(values, 'vacuum_kpa', 0, 90, 'wet_signals.vacuum_kpa')
    consistency = number(values, 'consistency', 0, 10, 'wet_signals.consistency')
    speed = number(values, 'speed', 0, 2200, 'wet_signals.speed')
    steady = flag(values, 'steady', 'wet_signals.steady')
    spliced = flag(values, 'spliced', 'wet_signals.spliced')
    return WetSignal(
        reel=reel,
        line=line,
        grade=grade,
        period=period,
        vacuum_kpa=vacuum_kpa,
        consistency=consistency,
        speed=speed,
        steady=steady,
        spliced=spliced,
    )
