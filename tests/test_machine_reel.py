from dataclasses import replace
import math

import pytest

from sheetgrade.machine_reel.contracts import ReelTick, InvalidRow, parse
from sheetgrade.machine_reel.service import evaluate, validate
from sheetgrade.machine_reel import algorithm

def tick(**options):
    return dict(line='PM-1', reel='L39', period=125, ingested=126, speed=1100, vacuum=480,
                vacuum_unit='mbar', consistency=.8, spliced=False, counter=31) | options


def test_pressure_units_map_to_physical_kpa():
    assert algorithm.vacuum_kpa(parse(tick())) == 48
    assert algorithm.vacuum_kpa(parse(tick(vacuum_unit='mmHg', vacuum=360.02976))) == pytest.approx(48)


def test_reversed_clock_is_quarantined_separately():
    result = evaluate([tick(ingested=124)], watermark=154)['records'][0]
    assert result['reason'] == 'CLOCK_INVERSION'
    assert result['ready'] is False


def test_observed_at_watermark_is_available_before_prediction():
    result = evaluate([tick(ingested=126)], watermark=126)['records'][0]
    assert result['ready'] is True


def test_capture_at_watermark_is_a_later_decision():
    result = evaluate([tick()], watermark=125)['records'][0]
    assert result['reason'] == 'NOT_YET_VISIBLE'


def test_fiber_and_sensor_faults_remain_distinct():
    result = evaluate([tick(vacuum=0, consistency=7)], watermark=130)['records'][0]
    assert result['diagnostics'] == ['VACUUM_TRANSDUCER_RANGE', 'FIBER_SAMPLE_RANGE']


def test_equivalent_packet_units_do_not_make_conflict():
    same = tick(vacuum=48, vacuum_unit='kPa')
    row = evaluate([same, tick()], watermark=130)['records'][0]
    assert row['ready'] and row['duplicates'] == 1


def test_disagreeing_telemetry_packet_requires_review():
    row = evaluate([tick(speed=1050), tick()], watermark=130)['records'][0]
    assert row['ready'] is False and not row.get('duplicates')
    assert row['reason'] == 'COUNTER_PACKET_CONFLICT'


def test_unrecognized_vacuum_unit_does_not_enter_training():
    row = evaluate([tick(vacuum_unit='Pa')], watermark=130)['records'][0]
    assert row['vacuum_kpa'] is None and row['reason'] == 'UNSUPPORTED_VACUUM_UNIT'
