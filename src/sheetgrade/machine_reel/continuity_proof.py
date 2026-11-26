from collections import Counter, defaultdict
from math import fsum


def discontinuities(reels, max_gap):
    ordered=sorted(reels,key=lambda point:(point['period'],point['counter'],point['reel']))
    checks=[]
    good=0
    for prior,point in zip(ordered,ordered[1:]):
        elapsed=point['period']-prior['period']
        steps=point['counter']-prior['counter']
        if elapsed==0:
            reason='PARALLEL_REEL_RECORD'
        elif steps<=0 and point['spliced']:
            reason='SPLICE_COUNTER_RESET'
        elif steps<=0:
            reason='UNEXPLAINED_COUNTER_RESET'
        elif elapsed>max_gap:
            reason='SAMPLING_GAP'
        elif steps>1:
            reason='MISSING_COUNTER_TICKS'
        else:
            good += 1
            continue
        checks.append({'before':prior['reel'],'after':point['reel'],'period':[prior['period'],point['period']],
                       'elapsed':elapsed,'counter_from':prior['counter'],'counter_to':point['counter'],
                       'reason':reason,'missing_ticks':max(steps-1,0)})
    return good,checks


def summarize_reels(telemetry, *, max_gap=15, expected_lines=()):
    if type(max_gap) is not int or max_gap<1:
        raise ValueError('INVALID_REEL_CADENCE')
    signals=defaultdict(list)
    for row in telemetry['records']:
        signals[row['line']].append(row)
    summaries=[]
    scanned=0
    for machine in sorted(signals.keys()|set(expected_lines)):
        good=[]
        skipped=[]
        contributing_weights=[]
        repeats=0
        for row in signals[machine]:
            if row['ready']:
                good.append(row)
                contributing_weights.append(row['speed'])
                repeats+=row.get('duplicates',0)
            else:
                skipped.append(row['reason'])
                repeats+=row.get('dropped_packet_count',0)
        gaps=Counter(skipped)
        runs,edges=discontinuities(good,max_gap)
        total=len(good)+len(skipped)+repeats
        scanned+=total
        summaries.append({'line':machine,'usable_packets':len(good),'unusable_packets':len(skipped),'packet_groups':len(good)+len(skipped),
                          'raw_packets':total,'duplicates':repeats,'continuous_transitions':runs,
                          'max_delay':max((row['ingested']-row['period'] for row in good),default=None),
                          'mean_speed':fsum(contributing_weights)/len(good) if good else None,
                          'rejected_by_reason':dict(gaps),'events':edges,'missing_ticks':sum(row['missing_ticks'] for row in edges)})
    actual=telemetry['accepted_count']+telemetry['rejected_count']
    return {'machines':summaries,'consumed_packets':scanned,'raw_documents':actual,
            'schema_failures':telemetry['rejected_count'],'input_balance':scanned+telemetry['rejected_count']==actual}
