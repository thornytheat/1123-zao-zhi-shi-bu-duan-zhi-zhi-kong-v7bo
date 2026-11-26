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
class ReelTick:
    line: str
    reel: str
    period: int
    ingested: int
    speed: float
    vacuum: float
    vacuum_unit: str
    consistency: float
    spliced: bool
    counter: int


def parse(values: Mapping[str, Any]) -> ReelTick:
    if not isinstance(values, Mapping):
        raise InvalidRow('machine_reel', 'EXPECTED_OBJECT')
    line = text(values, 'line', 'machine_reel.line')
    reel = text(values, 'reel', 'machine_reel.reel')
    period = integer(values, 'period', 0, 10000000, 'machine_reel.period')
    ingested = integer(values, 'ingested', 0, 10000000, 'machine_reel.ingested')
    speed = number(values, 'speed', 0, 2200, 'machine_reel.speed')
    vacuum = number(values, 'vacuum', 0, 1000, 'machine_reel.vacuum')
    vacuum_unit = text(values, 'vacuum_unit', 'machine_reel.vacuum_unit')
    consistency = number(values, 'consistency', 0, 30, 'machine_reel.consistency')
    spliced = flag(values, 'spliced', 'machine_reel.spliced')
    counter = integer(values, 'counter', 0, 100000000, 'machine_reel.counter')
    return ReelTick(
        line=line,
        reel=reel,
        period=period,
        ingested=ingested,
        speed=speed,
        vacuum=vacuum,
        vacuum_unit=vacuum_unit,
        consistency=consistency,
        spliced=spliced,
        counter=counter,
    )
