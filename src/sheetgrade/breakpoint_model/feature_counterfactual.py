from dataclasses import replace
from hashlib import sha256
from math import isfinite

from .algorithm import FEATURES, build_tree, inspect_route, local_support
from .contracts import parse


def train_for_diagnostics(dataset, cutoff, min_leaf, depth):
    eligible = {parse(row) for row in dataset if row['period']<=row['observed']<cutoff}
    ordered = sorted(eligible,key=lambda row:(row.period,row.line,row.reel,row.grade,row.observed,
                 row.consistency_z,row.vacuum_z,row.speed_z,row.break_within))
    tree = build_tree(ordered,depth,min_leaf)
    support = local_support(ordered)
    return tree,support,sha256(repr((ordered,cutoff,min_leaf,depth,'reel-path-probe-v1')).encode()).hexdigest()[:16]


def build_step_plan(vec, targets, support, max_step):
    for index, feature in enumerate(FEATURES):
        before = getattr(vec,feature)
        goal = targets[feature]
        lower,upper = support[index]
        if goal < lower or goal > upper:
            yield feature,before,goal,None,'REFERENCE_TARGET_OUT_OF_RANGE'
            continue
        shift = max(-max_step,min(max_step,goal-before))
        updated = before+shift
        if not lower<=updated<=upper:
            yield feature,before,goal,None,'PERTURBATION_EXCEEDS_MODEL_DOMAIN'
            continue
        yield feature,before,goal,updated,'PERTURBED'


def capture_reel_impact(vec, tree, min_leaf, support, targets, max_step, decision_threshold):
    original,path = inspect_route(vec,tree)
    valid = original.support>=min_leaf and all(lo<=getattr(vec,key)<=hi for key,(lo,hi) in zip(FEATURES,support))
    result = {'reel':vec.reel,'line':vec.line,'grade':vec.grade,'current_path':path,
              'current_leaf_rows':original.support,'current_risk':original.rate if valid else None,
              'threshold':decision_threshold,'alternatives':[],'best_feature':None}
    if not valid:
        return result|{'diagnosis':'BASELINE_OUTSIDE_MODEL_SUPPORT'}
    for feature,before,goal,updated,status in build_step_plan(vec,targets,support,max_step):
        option = {'feature':feature,'from':before,'target':goal,'confirmed_coordinate':updated,'reason':status}
        if updated is None:
            result['alternatives'].append(option|{'risk':None,'delta':None,'lineage':[],'crosses_cutoff':None,'leaf_rows':0})
            continue
        node,steps = inspect_route(replace(vec,**{feature:updated}),tree)
        enough = node.support>=min_leaf
        threshold_change = (node.rate>=decision_threshold)!=(original.rate>=decision_threshold) if enough else None
        result['alternatives'].append(option|{'risk':node.rate if enough else None,'delta':node.rate-original.rate if enough else None,
                                              'lineage':steps,'crosses_cutoff':threshold_change,'leaf_rows':node.support})
    beneficial = [option for option in result['alternatives'] if option['delta'] is not None and option['delta']<0]
    if beneficial:
        leading = min(beneficial,key=lambda option:(option['delta'],abs(option['confirmed_coordinate']-option['from']),option['feature']))
        result['best_feature'] = leading['feature']
    return result|{'diagnosis':'LOWER_RISK_PATH_FOUND' if beneficial else 'NO_LOWER_SINGLE_CHANNEL_PATH'}


def compare_supporting_cast(rows, *, history, cutoff, targets=None, max_step=2.0, threshold=.65, min_leaf=5, depth=3):
    if targets is None:
        goals={name:0.0 for name in FEATURES}
    else:
        if set(targets)!=set(FEATURES):
            raise ValueError('TARGETS_MUST_MATCH_FEATURES')
        goals=dict(targets)
    if not all(isfinite(value) for value in goals.values()) or not isfinite(max_step) or max_step<=0 or not 0<threshold<1:
        raise ValueError('INVALID_MODEL_PERTURBATION')
    if not 2<=min_leaf<=80 or not 1<=depth<=6:
        raise ValueError('INVALID_DIAGNOSTIC_TREE')
    tree,limits,version=train_for_diagnostics(history,cutoff,min_leaf,depth)
    diagnostics=[]
    for raw in rows:
        input_row=parse(raw)
        diagnostics.append(capture_reel_impact(input_row,tree,min_leaf,limits,goals,max_step,threshold))
    return {'fit_id':version,'training_count':tree.support,'reference_feature_ranges':dict(zip(FEATURES,limits)),
            'reference_targets':goals,'reels':diagnostics,'model_version':'cart-path-v1'}
