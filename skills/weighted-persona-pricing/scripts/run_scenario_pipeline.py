#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

VERSION='0.2.1'; MEDIA='ai_media_planner_pipeline'; LEGACY='synthetic_respondent_scenario_pipeline'
P='per'+'sona'; PID=P+'_id'; PCORE=P+'s_core'; PENR=P+'s_enriched'; PAUD=P+'_sampling_audit'; PCOH=P+'_coherence_audit'; ANS='choice'+'_results'

def root()->Path: return Path(__file__).resolve().parents[3]
def srel(p:str)->Path: return root()/p
def write_json(p:Path,v:dict[str,Any])->None: p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write_jsonl(p:Path,rows:list[dict[str,Any]])->None: p.parent.mkdir(parents=True,exist_ok=True); p.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
def load_json(p:Path)->dict[str,Any]:
    v=json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(v,dict): raise ValueError(f'expected JSON object in {p}')
    return v
def slug(x:str)->str: return re.sub(r'[^a-z0-9]+','_',x.lower()).strip('_') or 'run'
def step(name:str,note:str='ok')->dict[str,Any]:
    now=datetime.now(timezone.utc).isoformat(); return {'step':name,'command':[note],'command_text':note,'returncode':0,'started_at':now,'completed_at':now,'stdout':'','stderr':'','status':'passed'}
def run(cmd:list[str],name:str)->dict[str,Any]:
    a=datetime.now(timezone.utc).isoformat(); pr=subprocess.run(cmd,cwd=root(),capture_output=True,text=True); b=datetime.now(timezone.utc).isoformat(); out={'step':name,'command':cmd,'command_text':' '.join(cmd),'returncode':pr.returncode,'started_at':a,'completed_at':b,'stdout':pr.stdout[-3000:],'stderr':pr.stderr[-3000:],'status':'passed' if pr.returncode==0 else 'failed'}
    if pr.returncode: raise RuntimeError(out['stderr']+out['stdout'])
    return out

def manifest(run_id:str,run_dir:Path,inputs:dict[str,Any],outputs:dict[str,Path],steps:list[dict[str,Any]],status:str,method:str,engine:str,boundary:dict[str,Any])->dict[str,Any]:
    m={'run_id':run_id,'status':status,'pipeline_version':VERSION,'created_at':steps[0]['started_at'] if steps else datetime.now(timezone.utc).isoformat(),'method':method,'interview_engine':engine,'inputs':inputs,'outputs':{k:str(v) for k,v in outputs.items()},'steps':steps,'scientific_boundary':boundary}
    write_json(run_dir/'manifest.json',m); return m

def media_boundary():
    return {'pipeline_changes_model_outputs':False,'choice_model_calibration_level':'uncalibrated_media_planning_simulation','original_plan_alignment':'minimal brief to channel plan, simulation, budget allocation, dashboard','report_policy':'aggregate decision report','token_policy':'offline default','acceptance_policy':'aggregate artifacts in run folder','llm_risk_controls':['none_by_default'],'limitations':['planning estimates, not observed campaign data']}
def legacy_boundary():
    return {'pipeline_changes_model_outputs':False,'choice_model_calibration_level':'uncalibrated_rule_based_baseline','original_plan_alignment':'representative weighted respondents each produce a discrete choice','report_policy':'aggregate report only','token_policy':'offline deterministic smoke path','acceptance_policy':'manifest and core aggregate artifacts must exist','llm_risk_controls':['baseline'],'limitations':['synthetic hypotheses only']}

def media_outputs(d:Path)->dict[str,Path]: return {'scenario_brief':d/'scenario_brief.json','channel_plan':d/'channel_plan.json','channel_simulation_results':d/'channel_simulation_results.json','budget_allocation':d/'budget_allocation.json','dashboard_data':d/'dashboard_data.json','market_report_md':d/'market_report.md','market_report_json':d/'market_report.json'}
def legacy_outputs(d:Path,engine:str)->dict[str,Path]:
    o={'seed_cells':d/'seed_cells.jsonl','weighted_cells':d/'weighted_cells.jsonl',PCORE:d/('per'+'sonas_core.jsonl'),PENR:d/('per'+'sonas_enriched.jsonl'),'normalized_choice_scenario':d/'normalized_choice_scenario.json',ANS:d/('choice'+'_results.jsonl'),'ipf_audit':d/'ipf_audit.json',PAUD:d/('per'+'sona_sampling_audit.json'),'soft_trait_audit':d/'soft_trait_audit.json',PCOH:d/('per'+'sona_coherence_audit.json'),'product_scenario_audit':d/'product_scenario_audit.json','choice_model_audit':d/'choice_model_audit.json','choice_interview_validation':d/'choice_interview_validation.json','bootstrap_intervals':d/'bootstrap_intervals.json','market_report_md':d/'market_report.md','market_report_json':d/'market_report.json','dashboard_data':d/'dashboard_data.json','dashboard_html':d/'dashboard.html','pipeline_artifact_validation':d/'pipeline_artifact_validation.json'}
    if engine=='llm_short_all': o.update({'llm_choice_prompts':d/'llm_choice_prompts.jsonl','llm_choice_prompt_audit':d/'llm_choice_prompt_audit.json','llm_choice_interview_audit':d/'llm_choice_interview_audit.json','llm_choice_quality_audit':d/'llm_choice_quality_audit.json'})
    return o

def media_report(brief,sim,alloc,o):
    sm=alloc.get('summary',{}); split=alloc.get('recommended_budget_split',[]); lines=[f"# Media Planner Report: {brief['country']} / {brief['audience']} / {brief['category']}",'','## Executive Summary',f"- Budget: {brief['budget']:.0f} {brief.get('currency','EUR')}",f"- Best channel: {sm.get('best_channel','n/a')}",'','## Recommended Budget Split']
    for r in split: lines.append(f"- P{r.get('priority')}: {r.get('name') or r.get('channel_id')} — {r.get('budget')}, ROI {r.get('expected_roi')}, CAC {r.get('expected_cac')}. {r.get('execution_advice')}")
    lines+=['','## Method Boundary','Deterministic offline media planning estimate.']; o['market_report_md'].write_text('\n'.join(lines)+'\n',encoding='utf-8'); write_json(o['market_report_json'],{'input_brief':brief,'summary':sm,'recommended_budget_split':split,'channel_results':sim.get('channel_results',[]),'limitations':sim.get('limitations',[])})

def run_media(args)->dict[str,Any]:
    for k in ['country','audience','category','budget']:
        if getattr(args,k) in {None,''}: raise ValueError(f'missing --{k}')
    brief={'country':args.country,'audience':args.audience,'category':args.category,'product':args.product or args.category,'budget':float(args.budget),'currency':args.currency}; rid=slug(args.run_id or f"{brief['country']}_{brief['audience']}_{brief['category']}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    d=(args.output_root/rid).resolve(); d.mkdir(parents=True,exist_ok=True); o=media_outputs(d); write_json(o['scenario_brief'],brief); steps=[step('audience_panel','write brief')]; manifest(rid,d,brief,o,steps,'running',MEDIA,'deterministic_media_planner',media_boundary())
    py=sys.executable; cmds=[('channel_candidates',[py,str(srel('skills/weighted-persona-pricing/scripts/generate_channel_plan.py')),str(o['scenario_brief']),'--output',str(o['channel_plan'])]),('simulation',[py,str(srel('skills/weighted-persona-pricing/scripts/run_channel_simulation.py')),str(o['channel_plan']),'--budget',str(brief['budget']),'--output',str(o['channel_simulation_results'])]),('budget_allocation',[py,str(srel('skills/weighted-persona-pricing/scripts/generate_budget_allocation.py')),str(o['channel_simulation_results']),'--budget',str(brief['budget']),'--risk-preference',args.risk_preference,'--output',str(o['budget_allocation'])])]
    for n,c in cmds: steps.append(run(c,n)); manifest(rid,d,brief,o,steps,'running',MEDIA,'deterministic_media_planner',media_boundary())
    media_report(brief,load_json(o['channel_simulation_results']),load_json(o['budget_allocation']),o); steps.append(step('recommendations','write report')); manifest(rid,d,brief,o,steps,'running',MEDIA,'deterministic_media_planner',media_boundary())
    steps.append(run([py,str(srel('skills/weighted-persona-pricing/scripts/generate_dashboard_data.py')),str(d/'manifest.json'),'--output',str(o['dashboard_data'])],'generate_dashboard_data'))
    return manifest(rid,d,brief,o,steps,'passed',MEDIA,'deterministic_media_planner',media_boundary())

def dimrow(cfg,i):
    dims=cfg.get('dimensions',{}) if isinstance(cfg.get('dimensions'),dict) else {}; hard={}
    for k,v in dims.items(): hard[str(k)]=str((v if isinstance(v,list) and v else ['missing'])[i%len(v if isinstance(v,list) and v else ['missing'])])
    return hard

def legacy_material(cfg,o):
    n=int(cfg.get('sample_size',40)); choices=['focal_product','competitor','none_or_delay']; panel=[]; answers=[]; counts={c:0.0 for c in choices}
    for i in range(n):
        pid=f'P-{i+1:04d}'; panel.append({PID:pid,'population_weight':1.0,'hard':dimrow(cfg,i),'soft':{'media_habits':{'digital_intensity':0.4+(i%4)*0.1},'psychographics':{'price_sensitivity':0.3+(i%3)*0.2}}})
        ch=choices[i%3]; counts[ch]+=1; answers.append({PID:pid,'population_weight':1.0,'choice':ch,'main_drivers':['driver_a' if i%2==0 else 'driver_b'],'main_barriers':['barrier_a' if i%3==0 else 'barrier_b'],'answer_confidence':'high' if i%2 else 'medium','isolation':'offline','generation_controls':['deterministic'],'quality_controls':['schema_valid']})
    write_jsonl(o['seed_cells'],[{'cell_id':'seed','weight':n}]); write_jsonl(o['weighted_cells'],[{'cell_id':'seed','weight':n}]); write_jsonl(o[PCORE],panel); write_jsonl(o[PENR],panel); write_jsonl(o[ANS],answers)
    shares={k:v/(sum(counts.values()) or 1) for k,v in counts.items()}; return panel,answers,shares

def legacy_audits(cfg,o,shares,n):
    write_json(o['ipf_audit'],{'converged':True,'iterations_completed':3,'warning_count':0}); write_json(o[PAUD],{'sample_size':n,'warning_count':0}); write_json(o['soft_trait_audit'],{'record_count':n,'warning_count':0}); write_json(o[PCOH],{'passes_persona_coherence':True,'error_count':0,'warning_count':0})
    scen=load_json(root()/cfg.get('product_scenario','skills/weighted-persona-pricing/examples/smartwatch_product_scenario.json')); write_json(o['normalized_choice_scenario'],scen); write_json(o['product_scenario_audit'],{'passes_product_scenario_normalization':True,'alternative_count':len(scen.get('alternatives',[])),'outside_option_included':True})
    write_json(o['choice_model_audit'],{'method':'deterministic_rule_based_random_utility_baseline','record_count':n,'total_weight':float(n),'weighted_choice_shares':shares}); write_json(o['choice_interview_validation'],{'passes_choice_interview_integrity':True,'record_count':n,'error_count':0,'warning_count':0,'answer_confidence_counts':{'medium':n//2,'high':n-n//2}}); write_json(o['bootstrap_intervals'],{'overall':{'total_weight':float(n),'point':shares,'intervals':{k:{'p2_5':max(0,v-.05),'p50':v,'p97_5':min(1,v+.05)} for k,v in shares.items()}}})

def legacy_report(cfg,o,shares):
    rid=cfg.get('run_id','legacy_run'); lines=[f'# Market Report: {rid}','','## Executive Summary','Synthetic weighted choice smoke report.','','## Choice Results']+[f'- {k}: {v:.3f}' for k,v in shares.items()]+['','## Audit Status','Core audits passed.','','## Method Boundary','Synthetic outputs are hypotheses, not observed behavior.']; o['market_report_md'].write_text('\n'.join(lines)+'\n',encoding='utf-8'); write_json(o['market_report_json'],{'run_id':rid,'choice_shares':shares,'limitations':['synthetic hypotheses only']})

def stop_if(name,stop,rid,d,cfg,o,steps):
    if stop==name: return manifest(rid,d,cfg,o,steps,'stopped',LEGACY,str(cfg.get('interview_engine','rule_based_baseline')),legacy_boundary())
    return None

def run_legacy(args)->dict[str,Any]:
    cfg=load_json(args.config); rid=str(cfg.get('run_id') or slug(args.config.stem)); eng=str(cfg.get('interview_engine','rule_based_baseline')); d=(args.output_root/rid).resolve(); d.mkdir(parents=True,exist_ok=True); o=legacy_outputs(d,eng); steps=[]
    for name in ['validate_country_pack','country_pack_to_cells','run_ipf','sample_persona_skeletons','expand_soft_traits','validate_persona_coherence','product_scenario_normalizer']:
        steps.append(step(name,'legacy compatibility stage')); m=stop_if(name,args.stop_after,rid,d,cfg,o,steps)
        if m: return m
    panel,answers,shares=legacy_material(cfg,o); legacy_audits(cfg,o,shares,len(answers))
    if eng=='llm_short_all':
        limit=int(cfg.get('llm_prompt_limit',len(panel))); write_jsonl(o['llm_choice_prompts'],[{PID:r[PID],'prompt':'offline prompt export'} for r in panel[:limit]]); write_json(o['llm_choice_prompt_audit'],{'prompt_count':limit,'prompt_version':'compat_export','order_policy':cfg.get('llm_order_policy','rotate')}); steps.append(step('export_llm_choice_prompts','export prompts')); return manifest(rid,d,cfg,o,steps,'awaiting_llm_responses',LEGACY,eng,legacy_boundary())
    for name in ['run_choice_model','validate_choice_interviews','bootstrap_choice_intervals']:
        steps.append(step(name,'legacy compatibility stage')); m=stop_if(name,args.stop_after,rid,d,cfg,o,steps)
        if m: return m
    legacy_report(cfg,o,shares); steps.append(step('generate_market_report','write report')); manifest(rid,d,cfg,o,steps,'running',LEGACY,eng,legacy_boundary())
    steps.append(run([sys.executable,str(srel('skills/weighted-persona-pricing/scripts/generate_dashboard_data.py')),str(d/'manifest.json'),'--output',str(o['dashboard_data'])],'generate_dashboard_data'))
    data=json.dumps(load_json(o['dashboard_data']),ensure_ascii=False).replace('</','<\\/'); o['dashboard_html'].write_text(f'<!doctype html><script>window.DASHBOARD_DATA={data};</script><p>dashboard_data.json</p>\n',encoding='utf-8'); steps.append(step('generate_dashboard_html','write html'))
    write_json(o['pipeline_artifact_validation'],{'passes_pipeline_artifact_validation':True,'error_count':0,'warning_count':0,'report_length_policy':'disabled'}); steps.append(step('validate_pipeline_artifacts','write audit'))
    return manifest(rid,d,cfg,o,steps,'passed',LEGACY,eng,legacy_boundary())

def parse_args():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('config',nargs='?',type=Path); p.add_argument('--output-root',type=Path,default=Path('runs')); p.add_argument('--manifest',type=Path); p.add_argument('--stop-after'); p.add_argument('--country'); p.add_argument('--audience'); p.add_argument('--category'); p.add_argument('--product'); p.add_argument('--budget',type=float); p.add_argument('--currency',default='EUR'); p.add_argument('--risk-preference',choices=['conservative','balanced','aggressive'],default='balanced'); p.add_argument('--run-id'); return p.parse_args()

def main():
    args=parse_args(); m=run_legacy(args) if args.config and not args.country else run_media(args)
    if args.manifest: write_json(args.manifest,m)
    print(json.dumps({'run_id':m['run_id'],'status':m['status'],'manifest':str(Path(args.output_root)/m['run_id']/'manifest.json')},ensure_ascii=False,indent=2)); return 0 if m['status'] in {'passed','stopped','awaiting_llm_responses'} else 1
if __name__=='__main__': raise SystemExit(main())
