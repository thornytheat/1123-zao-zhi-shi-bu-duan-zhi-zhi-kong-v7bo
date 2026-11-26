from __future__ import annotations

from .contracts import ReelTick

from collections import defaultdict
from dataclasses import asdict


def vacuum_kpa(reading):
    if reading.vacuum_unit == 'kPa':
        return reading.vacuum
    if reading.vacuum_unit == 'mbar':
        return reading.vacuum * .1
    if reading.vacuum_unit == 'mmHg':
        return reading.vacuum / 7.50062
    raise ValueError('UNSUPPORTED_VACUUM_UNIT')


def scan_key(row):
    return row.line, row.reel, row.period, row.counter


def normalize_packet(row, watermark):
    reasons = []
    if row.period >= watermark or row.ingested > watermark:
        reasons.append('NOT_YET_VISIBLE')
    if row.ingested < row.period:
        reasons.append('CLOCK_INVERSION')
    if not 100 <= row.speed <= 1850:
        reasons.append('REEL_IDLE_OR_OVERSPEED')
    try:
        vacuum = vacuum_kpa(row)
    except ValueError as error:
        reasons.append(str(error))
        vacuum = None
    if vacuum is not None and not 8 <= vacuum <= 80:
        reasons.append('VACUUM_TRANSDUCER_RANGE')
    if not .2 <= row.consistency <= 3.5:
        reasons.append('FIBER_SAMPLE_RANGE')
    return asdict(row) | {'vacuum_kpa': vacuum, 'ready': not reasons,
                           'reason': reasons[0] if reasons else 'ACCEPTED', 'diagnostics': reasons}


def reconcile_slot(group):
    content = {(item['vacuum_kpa'], item['speed'], item['consistency'], item['spliced']) for item in group}
    selected = min(group, key=lambda item: (item['ingested'], item['vacuum_unit'], item['vacuum'], item['speed'], item['consistency']))
    if len(content) > 1:
        return selected | {'ready': False, 'reason': 'COUNTER_PACKET_CONFLICT', 'diagnostics': ['COUNTER_PACKET_CONFLICT'], 'dropped_packet_count': len(group)-1}
    return selected | {'duplicates': len(group) - 1}


def calculate(records, *, watermark):
    groups = defaultdict(list)
    output = []
    for reading in records:
        entry = normalize_packet(reading, watermark)
        if entry['ready']:
            groups[scan_key(reading)].append(entry)
        else:
            output.append(entry)
    output.extend(reconcile_slot(group) for group in groups.values())
    return sorted(output, key=lambda row: (row['line'], row['period'], row['reel'], row['counter'], row['reason']))
