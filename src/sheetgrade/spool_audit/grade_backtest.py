from collections import defaultdict
from math import fsum, isfinite, sqrt

from .algorithm import brier_score, final_spools
from .contracts import parse


def number_of_true_breaks(samples):
    return sum(row.observed_break for row in samples)


def reduce_production(classes, threshold):
    caught = [row for row in classes if row.observed_break and row.break_probability>=threshold]
    missed = [row for row in classes if row.observed_break and row.break_probability<threshold]
    reviewed = [row for row in classes if row.break_probability>=threshold]
    salvage = fsum(row.mass_kg for row in caught)
    exposed = fsum(row.mass_kg for row in missed)
    precision = len(caught)/len(reviewed) if reviewed else None
    return {'caught_count':len(caught),'false_review_count':len(reviewed)-len(caught),'missed_count':len(missed),
            'estimated_review_kg':fsum(row.mass_kg for row in reviewed),'caught_kg':salvage,'exposed_kg':exposed,
            'break_kg':salvage+exposed,'review_precision':precision}


def deviation_stats(samples):
    n=len(samples)
    if not n:
        return {'n':0,'mean_probability':None,'break_rate':None,'bias':None,'brier':None,'bias_standard_error':None}
    average=fsum(row.break_probability for row in samples)/n
    actual=number_of_true_breaks(samples)/n
    residuals=[row.break_probability-float(row.observed_break) for row in samples]
    bias=fsum(residuals)/n
    stderr=sqrt(fsum((value-bias)**2 for value in residuals)/(n*(n-1))) if n>1 else None
    return {'n':n,'mean_probability':average,'break_rate':actual,'bias':bias,'brier':brier_score(samples),'bias_standard_error':stderr}


def grade_bins(samples, grid):
    rows=[]
    for index,(start,end) in enumerate(zip(grid,grid[1:])):
        members=[row for row in samples if start<=row.break_probability<end or (index==len(grid)-2 and row.break_probability==1)]
        summary=deviation_stats(members)
        rows.append({'from':start,'until':end,**summary})
    return rows


def report_by_grade(batches, threshold, bins):
    output=[]
    completed=0
    exposed=[]
    for grade,samples in sorted(batches.items()):
        physics=reduce_production(samples,threshold)
        calibration=deviation_stats(samples)
        evidence=grade_bins(samples,bins)
        t=number_of_true_breaks(samples)
        mass=physics['break_kg']
        output.append({'grade':grade,'passing_mass':fsum(row.mass_kg for row in samples if not row.observed_break),
                       'closed_reels':len(samples),'positive_count':t,'break_mass_recall':physics['caught_kg']/mass if mass else None,
                       'operating_point':physics,'calibration':calibration,'histogram':evidence,
                       'verified_bins':sum(row['n'] for row in evidence)==len(samples)})
        completed += len(samples)
        exposed.append(physics['exposed_kg'])
    return output,completed,fsum(exposed)


def audit_grade_backtest(rows, *, as_of, threshold=.65, bins=(0,.2,.4,.6,.8,1)):
    fractions=tuple(bins)
    if len(fractions)<2 or fractions[0]!=0 or fractions[-1]!=1 or tuple(sorted(set(fractions)))!=fractions:
        raise ValueError('INVALID_RELIABILITY_BUCKETS')
    if not isfinite(threshold) or not 0<threshold<1:
        raise ValueError('INVALID_GRADE_THRESHOLD')
    settled,rejected=final_spools([parse(record) for record in rows],as_of)
    grouping=defaultdict(list)
    for row in settled:
        grouping[row.grade].append(row)
    evidence,count,remaining=report_by_grade(grouping,threshold,fractions)
    report=reduce_production(settled,threshold)
    return {'as_of':as_of,'threshold':threshold,'observed':count,'rejected':rejected,'grades':evidence,
            'risk_vs_volume':report,'unflagged_kg':remaining,'mass_reconciled':remaining==report['exposed_kg']}
