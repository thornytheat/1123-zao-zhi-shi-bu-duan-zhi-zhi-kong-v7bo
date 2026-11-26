from collections import defaultdict


def intersecting_boundaries(plans, begin, end):
    edges = {begin,end}
    for plan in plans:
        cut = plan['effective']
        for value in (cut,plan['until'],cut+plan['stabilize']):
            if begin < value < end:
                edges.add(value)
    return sorted(edges)


def state_at(orders, start):
    candidates = [row for row in orders if row['effective']<=start<row['until']]
    identities = sorted(row['order'] for row in candidates)
    if len(candidates)>1:
        return '重叠计划', None, identities
    if not candidates:
        return '无计划', None, []
    entry = candidates[0]
    if not entry['usable']:
        return '待审核', None, identities
    if start < entry['effective']+entry['stabilize']:
        return '换线', entry['grade'], identities
    return '稳定', entry['grade'], identities


def materialize_timeline(orders, start, end):
    boundaries = intersecting_boundaries(orders,start,end)
    intervals = []
    for left,right in zip(boundaries,boundaries[1:]):
        state,grade,keys = state_at(orders,left)
        if intervals and (prior:=intervals[-1])['state']==state and prior['grade']==grade and prior['orders']==keys:
            prior['end']=right
        else:
            intervals.append({'start':left,'end':right,'state':state,'grade':grade,'orders':keys})
    for span in intervals:
        span['minutes']=span['end']-span['start']
    return intervals


def audit_grade_timeline(plans, *, start=130, end=255, require_lines=()):
    if type(start) is not int or type(end) is not int or start>=end:
        raise ValueError('INVALID_AUDIT_INTERVAL')
    grouped = defaultdict(list)
    for entry in plans:
        grouped[entry['line']].append(entry)
    output = []
    for machine in sorted(grouped.keys() | set(require_lines)):
        spans = materialize_timeline(grouped[machine],start,end)
        phase = defaultdict(int)
        grades = defaultdict(int)
        for span in spans:
            phase[span['state']]+=span['minutes']
            if span['state']=='稳定':
                grades[span['grade']]+=span['minutes']
        output.append({'line':machine,'window':[start,end],'phase_minutes':dict(phase),'stable_minutes_by_grade':dict(grades),
                       'conflict_share':phase.get('重叠计划',0)/(end-start),'evidence':spans,
                       'minutes_reconciled':sum(phase.values())==end-start})
    return output
