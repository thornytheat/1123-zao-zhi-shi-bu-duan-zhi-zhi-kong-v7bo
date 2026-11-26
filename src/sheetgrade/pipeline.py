from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import breakpoint_model, grade_change, machine_reel, release_order, spool_audit, wet_signals
from .grade_change.service import grade_at


SHIFT_END = 255
TRAINING_END = 120
DEFAULT_CAPACITY = 5


def load_shift():
    path = Path(__file__).resolve().parents[2] / 'sample_data' / 'west_mill_morning_shift.json'
    return json.loads(path.read_text(encoding='utf-8'))


def classify_reel_readings(meters, order_windows):
    mapped = []
    for row in meters:
        if not row['ready']:
            continue
        interval = grade_at(order_windows, row['line'], row['period'])
        mapped.append(row | interval | {'grade': interval['grade'] or '未映射'})
    return mapped


def merge_for_release(snapshots, signals, predictions):
    behavior = {(row['line'], row['reel']): row for row in signals}
    fit = {(row['line'], row['reel']): row for row in predictions}
    orders = []
    for sample in snapshots:
        key = sample['line'], sample['reel']
        feature = behavior.get(key, {})
        estimate = fit.get(key, {})
        model_value = estimate.get('probability')
        action_reason = estimate.get('reason') or feature.get('reason') or sample.get('reason')
        critical = sample['consistency'] >= 1.1 or (sample['vacuum_kpa'] is not None and sample['vacuum_kpa'] >= 49)
        orders.append(sample | {
            'grade': sample.get('grade', '未映射'),
            'mass_kg': round(sample['speed'] * .9, 1),
            'critical': critical,
            'critical_evidence': sample['ready'],
            'probability': model_value or 0,
            'model_ready': model_value is not None,
            'feature_reason': action_reason or 'MEASUREMENT_UNAVAILABLE',
        })
    return orders


def presentation(release):
    rows = []
    for row in release:
        point = row.get('retest_point')
        if point:
            retest = release_order.RetestLabel(point['label'], [
                point.get('feature'), point.get('raw_feature'), point.get('display'),
            ])
            retest_detail = point['display']
        elif row['state'] == '试样复核':
            retest = None
            retest_detail = '沿用原复核依据'
        else:
            retest = None
            retest_detail = None
        rows.append({
            'reel': row['reel'], 'machine': row['line'], 'grade': row['grade'],
            'break_probability': round(row['probability'], 3) if row['model_ready'] else None,
            'mass': row['mass_kg'], 'lab': row['review_slot'],
            'retest_point': retest,
            'first_retest_point': retest,
            'retest_feature': point['feature'] if point else None,
            'retest_source_reel': point['source_reel'] if point else None,
            'retest': retest,
            'retest_detail': retest_detail,
            'status': row['state'] + ('（待位）' if row.get('waiting_for_lab') else ''),
            'reason': row['reason'],
        })
    return rows


def run(capacity: int | None = None) -> dict:
    data = load_shift()
    meters = machine_reel.evaluate(data['meters'], watermark=SHIFT_END)
    plans = grade_change.evaluate(data['orders'], available_at=SHIFT_END)
    mapped = classify_reel_readings(meters['records'], plans['records'])
    signals = wet_signals.evaluate(mapped, history=data['history'], cutoff=TRAINING_END)
    judged = [row | {'observed': row['period'], 'break_within': False} for row in signals['records'] if row['usable']]
    fits = breakpoint_model.evaluate(judged, history=data['faults'], cutoff=TRAINING_END)
    work = merge_for_release(mapped + [row for row in meters['records'] if not row['ready']], signals['records'], fits['records'])
    orders = release_order.evaluate(work, capacity=capacity if capacity is not None else DEFAULT_CAPACITY)
    meter_arrival = {(row['line'], row['reel']): row.get('ingested') for row in mapped}
    retest_readings = [
        row | {'ingested': meter_arrival.get((row.get('line'), row.get('reel')))}
        for row in signals['records']
    ]
    retest_plan = release_order.attach_retest_points(
        orders['records'],
        readings=retest_readings,
        model_history=data['faults'],
        baseline_history=data['history'],
        cutoff=TRAINING_END,
        watermark=SHIFT_END,
    )
    audit = spool_audit.evaluate(data['verified'], as_of=SHIFT_END)
    ready = orders['records']
    placement = Counter(row['state'] for row in ready)
    return {
        'first_retest_point': retest_plan['first'],
        'first_retest_feature': retest_plan['first']['feature'] if retest_plan['first'] else None,
        'first_retest_label': retest_plan['first']['label'] if retest_plan['first'] else None,
        'reconciliation': {
            'counter_continuity': machine_reel.summarize_reels(meters),
            'shift_grade_minutes': grade_change.audit_grade_timeline(plans['records']),
            'press_control': wet_signals.track_press_change(signals['records']),
            'lab_options': release_order.stress_laboratory(work),
            'retest_points': retest_plan,
            'model_diagnostics': breakpoint_model.compare_supporting_cast(judged,history=data['faults'],cutoff=TRAINING_END),
            'grade_reliability': spool_audit.audit_grade_backtest(data['verified'],as_of=SHIFT_END),
        },
        'metrics': {'本班卷次': len(ready), '模型可判': sum(row['model_ready'] for row in ready),
                    '继续生产': placement['继续生产'], '实验室席位': sum(row['review_slot'] is not None for row in ready)},
        'columns': {'reel':'纸卷', 'machine':'机台', 'grade':'纸种', 'break_probability':'断纸风险',
                    'mass':'卷重 kg', 'lab':'化验位', 'retest_point':'首个复测点',
                    'retest_detail':'复测对照', 'status':'质检判断', 'reason':'依据'},
        'rows': presentation(ready),
        'series': [{'label': f"{round(item['threshold']*100)}%", 'value': item['missed_kg']}
                   for item in audit['records'] if item['audit']=='threshold'],
        'stages': [{'title': title, 'summary': summary, 'records': result['records'], 'errors': result['errors']}
                   for title, summary, result in [
                      ('机台抄表','保留真空量纲、计数冲突和点位采集水位',meters),
                      ('纸种换线','计划重叠和纸种稳定期都进入审查',plans),
                      ('湿部特征','按纸种拟合湿部基线并分机台计算短间隔斜率',signals),
                      ('断纸拟合','CART 分裂路径可核对，训练域外转测点复核',fits),
                      ('质检处置','封卷和测点复核优先，实验室分机台设配额',orders),
                      ('班组对账','仅核对已有化验完结凭证的纸卷',audit),
                   ]],
    }
