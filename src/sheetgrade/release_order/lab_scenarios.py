from collections import Counter, defaultdict
from math import fsum

from .algorithm import calculate
from .contracts import parse


def mass_report(report):
    by_state = defaultdict(list)
    block = defaultdict(list)
    for row in report:
        by_state[row['state']].append(row['mass_kg'])
        if row.get('waiting_for_lab'):
            block[row['line']].append(row)
    consumption = {state:fsum(weights) for state,weights in sorted(by_state.items())}
    waiting = {line:{'count':len(cases),'over_limit_mass':fsum(row['mass_kg'] for row in cases if row['priority']==4),
                     'needs_confirmation_mass':fsum(row['mass_kg'] for row in cases if row['priority'] in (2,3))}
               for line,cases in sorted(block.items())}
    return consumption,waiting


def line_usage(report):
    lines = Counter()
    total = 0
    for row in report:
        if row['review_slot'] is None:
            continue
        lines[row['line']] += 1
        total += 1
    return dict(lines),total


def scenario_evidence(rows, capacity, line_limit, threshold):
    decisions = calculate(rows,capacity=capacity,per_line=line_limit,threshold=threshold)
    mass_by_state,waiting = mass_report(decisions)
    reserved_by_line,reserved_count = line_usage(decisions)
    critical = fsum(values['over_limit_mass'] for values in waiting.values())
    uncertain = fsum(values['needs_confirmation_mass'] for values in waiting.values())
    finite = fsum(row['mass_kg']*row['probability'] for row in decisions if row['priority']==1 and row.get('waiting_for_lab'))
    return {'total_reels':len(decisions),'capacity':capacity,'per_line':line_limit,'threshold':threshold,
            'reserved':reserved_count,'unassigned_capacity':capacity-reserved_count,'by_line':reserved_by_line,
            'pending_by_line':waiting,'mass_by_state':mass_by_state,'confirmed_breach_pending_kg':critical,
            'unverified_pending_kg':uncertain,'estimated_pending_kg':finite,
            'allocations':[{'line':row['line'],'reel':row['reel'],'slot':row['review_slot'],'priority':row['priority']}
                           for row in decisions if row['review_slot'] is not None]}


def stress_laboratory(records, *, capacity_choices=(2,5,8), quotas=(2,3), thresholds=(.65,.8)):
    ceilings=sorted(set(capacity_choices))
    reserved=sorted(set(quotas))
    cutoffs=sorted(set(thresholds))
    if not ceilings or not reserved or not cutoffs or len(ceilings)*len(reserved)*len(cutoffs)>60:
        raise ValueError('INVALID_LAB_SCENARIO_GRID')
    if any(type(value) is not int or not 1<=value<=100 for value in ceilings+reserved) or not all(0<value<1 for value in cutoffs):
        raise ValueError('INVALID_LAB_SCENARIO_BOUNDARY')
    input_rows=[parse(row) for row in records]
    options=[]
    for capacity in ceilings:
        for quota in reserved:
            for threshold in cutoffs:
                options.append(scenario_evidence(input_rows,capacity,quota,threshold))
    best=min(options,key=lambda row:(row['confirmed_breach_pending_kg'],row['unverified_pending_kg'],
                          row['estimated_pending_kg'],row['capacity'],row['per_line'],row['threshold']))
    return {'scenarios':options,'lowest_risk_scenario':[best['capacity'],best['per_line'],best['threshold']]}
