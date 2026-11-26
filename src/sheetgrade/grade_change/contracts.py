from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


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




@dataclass(frozen=True, slots=True)
class GradeWindow:
    line: str
    grade: str
    order: str
    effective: int
    until: int
    stabilize: int
    recorded: int
    revision: int


def parse(values: Mapping[str, Any]) -> GradeWindow:
    if not isinstance(values, Mapping):
        raise InvalidRow('grade_change', 'EXPECTED_OBJECT')
    line = text(values, 'line', 'grade_change.line')
    grade = text(values, 'grade', 'grade_change.grade')
    order = text(values, 'order', 'grade_change.order')
    effective = integer(values, 'effective', 0, 10000000, 'grade_change.effective')
    until = integer(values, 'until', 0, 10000000, 'grade_change.until')
    stabilize = integer(values, 'stabilize', 0, 180, 'grade_change.stabilize')
    recorded = integer(values, 'recorded', 0, 10000000, 'grade_change.recorded')
    revision = integer(values, 'revision', 1, 50, 'grade_change.revision')
    return GradeWindow(
        line=line,
        grade=grade,
        order=order,
        effective=effective,
        until=until,
        stabilize=stabilize,
        recorded=recorded,
        revision=revision,
    )
