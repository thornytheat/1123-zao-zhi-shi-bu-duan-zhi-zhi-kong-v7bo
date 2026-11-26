from collections import defaultdict
from dataclasses import dataclass
from math import isfinite


@dataclass(slots=True)
class RunChart:
    upward: float = 0
    downward: float = 0
    consecutive: int = 0
    last_time: int | None = None

    def update(self, z_value, allowance, control):
        self.upward = max(0.0,self.upward+z_value-allowance)
        self.downward = max(0.0,self.downward-z_value-allowance)
        self.consecutive += 1
        if self.upward >= control:
            return 'VACUUM_UPSHIFT'
        if self.downward >= control:
            return 'VACUUM_DOWNSHIFT'
        return 'WITHIN_CONTROL'


def compose_windows(records):
    groups = defaultdict(list)
    for row in records:
        groups[row['line']].append(row)
    for machine, observations in sorted(groups.items()):
        ordered = sorted(observations,key=lambda row:(row['period'],row['reel']))
        active = set()
        for row in ordered:
            ident = row['period']
            if ident in active:
                raise ValueError(f'DUPLICATE_CONTROL_TICK:{machine}:{ident}')
            active.add(ident)
        yield machine,ordered


def slot_phase(row, state, grade, max_gap):
    if not row['usable']:
        return 'OUTSIDE_STEADY_MACHINE_SCENE'
    if not isfinite(row['vacuum_z']):
        return 'NON_FINITE_CONTROL_READING'
    if state.last_time is None:
        return 'FIRST_READING'
    if row['grade']!=grade:
        return 'GRADE_CHANGE'
    if row['period']-state.last_time>max_gap:
        return 'OBSERVATION_GAP'
    return None


def track_press_change(records, *, allowance=.4, control=3.5, max_gap=18):
    if not isfinite(allowance) or not isfinite(control) or allowance<0 or control<=allowance or max_gap<1:
        raise ValueError('INVALID_CUSUM_WINDOW')
    report=[]
    for line,events in compose_windows(records):
        state=RunChart()
        last_grade=None
        held=False
        for point in events:
            marker=slot_phase(point,state,last_grade,max_gap)
            if marker:
                state=RunChart()
            grade=point['grade']
            if marker in ('OUTSIDE_STEADY_MACHINE_SCENE','NON_FINITE_CONTROL_READING'):
                result='UNSCORED'
                held=True
                source_z=None
            else:
                source_z=point['vacuum_z']
                result=state.update(source_z,allowance,control)
                state.last_time=point['period']
                last_grade=grade
                if held and marker=='FIRST_READING':
                    marker='RESUMED_AFTER_HOLD'
                held=False
            report.append({'line':line,'reel':point['reel'],'period':point['period'],'grade':grade,
                           'state':result,'reset':marker,'z':source_z,'up':state.upward,'down':state.downward,
                           'run_length':state.consecutive})
    return report
