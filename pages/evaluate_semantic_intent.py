"""Frozen-prompt semantic probes; synthetic context, never player records."""
import argparse,asyncio,copy,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.control import token
from rococoach.match import new_match,advance
from rococoach.semantic_control import plan_intent,SYSTEM,IntentPlan
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
raw=(ROOT/'data/agent_intent_eval.json').read_text();cases=json.loads(raw)['cases']
base=new_match('electric',42)
while not base['battle']['ended']:base=advance(base,'move 1',expected_round=len(base['frames']))
contexts={'ended':base,'playing':new_match('practice',42)}
pending=copy.deepcopy(base);pending['pending_action']={'id':'probe-proposal','arguments':{'scenario':'practice','difficulty':'challenge'},'source_token':token(pending),'expires_at':time.time()+600,'origin':'semantic_planner'}
pending['messages'].extend([{'speaker':'user','kind':'chat','text':'先给个进阶方案'},
 {'speaker':'assistant','kind':'chat','text':'可以安排均衡进阶对练，现在开始吗？','proposal_id':'probe-proposal'}]);contexts['pending']=pending
casual=copy.deepcopy(base);casual['messages'].extend([{'speaker':'user','kind':'chat','text':'今天有点累'},
 {'speaker':'assistant','kind':'chat','text':'那就慢慢来，休息一下也很好。'}]);contexts['casual']=casual
legacy=copy.deepcopy(base);legacy['messages'].extend([{'speaker':'user','kind':'chat','text':'想练得有挑战些'},
 {'speaker':'assistant','kind':'chat','text':'可以换成均衡进阶对练，我现在给你开局吗？'}]);contexts['legacy']=legacy
report={'scope':'独立合成上下文，真实模型；探索集非独立盲测，不据结果补短语规则',
 'prompt_hash':hashlib.sha256((SYSTEM+json.dumps(IntentPlan.model_json_schema(),sort_keys=True)).encode()).hexdigest(),
 'dataset_hash':hashlib.sha256(raw.encode()).hexdigest(),'results':[]}
with args.output.open('x') as f:json.dump(report,f)
async def main():
 gate=asyncio.Semaphore(3)
 async def one(case):
  async with gate:
   t=time.monotonic()
   try:
    plan,meta,_=await asyncio.to_thread(plan_intent,case['query'],copy.deepcopy(contexts[case['context']]),{'profile':{'preference':'简洁'}})
    result={'id':case['id'],'plan':plan.model_dump(),'metadata':meta,'seconds':round(time.monotonic()-t,3)}
    result['passed']=plan.operation in case['operations'] and all(getattr(plan,k)==case[k] for k in ['difficulty','style','reference'] if k in case)
   except Exception as e:result={'id':case['id'],'passed':False,'error':str(e)}
   return result
 report['results']=await asyncio.gather(*(one(c) for c in cases))
asyncio.run(main())
report['passed']=sum(r['passed'] for r in report['results']);report['total']=len(cases)
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':report['passed'],'total':report['total'],'failed':[r['id'] for r in report['results'] if not r['passed']]}))
