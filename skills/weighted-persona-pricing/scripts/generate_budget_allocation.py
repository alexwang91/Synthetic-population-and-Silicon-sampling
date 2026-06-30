#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICIES={'conservative':{'holdout_pct':0.15,'test_budget_pct':0.20,'risk_penalty':0.78},'balanced':{'holdout_pct':0.10,'test_budget_pct':0.15,'risk_penalty':0.9},'aggressive':{'holdout_pct':0.06,'test_budget_pct':0.10,'risk_penalty':1.0}}

def load_json(path: Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(v,dict): raise ValueError(f'expected JSON object in {path}')
    return v

def write_json(path: Path, value: dict[str,Any])->None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def num(v:Any,d:float=0.0)->float:
    try:
        return d if v is None or isinstance(v,bool) else float(v)
    except Exception:
        return d

def risk(row):
    low,high=row.get('confidence_interval',[row.get('roi',0),row.get('roi',0)])[:2]
    width=num(high)-num(low); roi=num(row.get('roi'))
    if width>.9 or roi<.2: return 'high'
    if width>.55 or roi<.75: return 'medium'
    return 'low'

def role(row):
    roi=num(row.get('roi')); reach=num(row.get('estimated_reach')); conv=num(row.get('weighted_conversions'))
    if roi>=1.2 and reach<50000: return 'high_roi_capped_scale'
    if roi>=.6 and reach>=50000: return 'scale_layer'
    if conv>0 and roi>=0: return 'test_layer'
    return 'watchlist'

def rationale(row, role_name):
    if role_name=='high_roi_capped_scale': return 'High ROI signal but finite reach. Give high priority with controlled budget.'
    if role_name=='scale_layer': return 'Broad reach with acceptable ROI. Use as the main scale layer while monitoring CAC.'
    if role_name=='test_layer': return 'Useful signal but uncertainty remains. Keep it in the test budget until calibrated.'
    return 'Low priority until observed data improves confidence.'

def advice(row, role_name):
    name=row.get('name') or row.get('channel_id')
    if role_name=='high_roi_capped_scale': return f'Fund {name} first, cap spend when CAC rises above the modeled range, and protect exact demand.'
    if role_name=='scale_layer': return f'Scale {name} with weekly creative rotation, frequency controls, and holdout measurement.'
    if role_name=='test_layer': return f'Run {name} as a structured test with one KPI, one creative thesis, and a stop-loss CAC.'
    return f'Keep {name} as a low-budget learning cell only.'

def score(row, policy):
    r=risk(row); penalty={'low':1.0,'medium':0.86,'high':policy['risk_penalty']}[r]
    return max(.01,(num(row.get('roi'))+1.0)*0.52 + num(row.get('roas'))*0.28 + min(num(row.get('estimated_reach'))/100000,1.4)*0.20)*penalty

def generate_budget_allocation(simulation: dict[str,Any], total_budget: float|None=None, risk_preference: str='balanced')->dict[str,Any]:
    if risk_preference not in POLICIES: raise ValueError('unsupported risk preference')
    policy=POLICIES[risk_preference]
    budget=total_budget if total_budget is not None else num((simulation.get('budget_assumptions') or {}).get('total_budget') or (simulation.get('input_brief') or {}).get('budget'))
    if budget<=0: raise ValueError('budget must be positive')
    rows=simulation.get('channel_results') or []
    if not rows: raise ValueError('channel_results must not be empty')
    holdout=budget*policy['holdout_pct']; deployable=budget-holdout
    weights=[(row,score(row,policy)) for row in rows]; total=sum(w for _,w in weights) or 1
    min_test=deployable*.015; rec=[]
    for row,w in weights:
        amount=max(min_test,deployable*w/total); r=risk(row)
        if r=='high': amount=min(amount,deployable*(.18 if risk_preference=='balanced' else .12 if risk_preference=='conservative' else .26))
        rc=role(row)
        rec.append({'channel_id':row.get('channel_id'),'name':row.get('name'),'priority':0,'budget':round(amount,2),'budget_pct':round(amount/budget,4),'rationale':rationale(row,rc),'execution_advice':advice(row,rc),'risk':r,'role_classification':rc,'expected_roi':row.get('roi'),'expected_roas':row.get('roas'),'expected_cac':row.get('cac')})
    total_alloc=sum(x['budget'] for x in rec) or 1
    for x in rec:
        x['budget']=round(deployable*x['budget']/total_alloc,2); x['budget_pct']=round(x['budget']/budget,4)
    rec.sort(key=lambda x:(-num(x.get('expected_roi')), x['risk']=='high', -num(x.get('budget')), str(x.get('channel_id'))))
    for i,x in enumerate(rec,1): x['priority']=i
    best=max(rows,key=lambda r:num(r.get('roi'),-999)); scale=max(rows,key=lambda r:num(r.get('estimated_reach'),0))
    return {'budget_allocation_version':'0.1.0','generated_at':datetime.now(timezone.utc).isoformat(),'input_brief':simulation.get('input_brief',{}),'risk_preference':risk_preference,'recommended_budget_split':rec,'summary':{'best_channel':best.get('channel_id'),'highest_scale_channel':scale.get('channel_id'),'test_budget_pct':policy['test_budget_pct'],'holdout_pct':policy['holdout_pct'],'holdout_budget':round(holdout,2),'deployable_budget':round(deployable,2),'currency':(simulation.get('budget_assumptions') or {}).get('currency') or (simulation.get('input_brief') or {}).get('currency') or 'EUR'},'allocation_rules':['High ROI with capped scale receives high priority but limited budget.','Medium ROI with broad reach can become a scale layer.','High uncertainty channels remain test channels until calibrated.','Holdout and test budgets are retained for real campaign calibration.']}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('channel_results',type=Path); p.add_argument('--budget',type=float); p.add_argument('--risk-preference',choices=sorted(POLICIES),default='balanced'); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    out=generate_budget_allocation(load_json(a.channel_results), total_budget=a.budget, risk_preference=a.risk_preference)
    write_json(a.output,out); print(json.dumps({'channel_count':len(out['recommended_budget_split']),'output':str(a.output)},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__':
    raise SystemExit(main())
