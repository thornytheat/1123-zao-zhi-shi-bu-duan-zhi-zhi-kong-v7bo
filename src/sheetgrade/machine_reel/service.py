from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .algorithm import calculate
from .contracts import ReelTick, InvalidRow, parse


@dataclass(frozen=True, slots=True)
class ReelTickRejection:
    line: int
    field: str
    code: str


def validate(rows: Iterable[Mapping[str, Any]]) -> tuple[list[ReelTick], list[ReelTickRejection]]:
    accepted = []
    rejected = []
    for line, raw in enumerate(rows, 1):
        try:
            accepted.append(parse(raw))
        except InvalidRow as issue:
            rejected.append(ReelTickRejection(line, issue.field, issue.code))
    return accepted, rejected


def evaluate(rows: Iterable[Mapping[str, Any]], **options) -> dict:
    """计算机台抄表，逐行隔离字段错误，保留原因码和行号。"""
    accepted, rejected = validate(rows)
    outcome = calculate(accepted, **options)
    return {
        'records': outcome,
        'accepted_count': len(accepted),
        'rejected_count': len(rejected),
        'errors': [asdict(error) for error in rejected],
    }
from .continuity_proof import summarize_reels
