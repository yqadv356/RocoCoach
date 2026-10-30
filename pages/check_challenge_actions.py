"""Semantic planning + typed local execution, including persisted confirmation."""
import argparse,json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.control import control_reply,apply_command
from rococoach.match import new_match,advance
from rococoach.memory import Memory
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
with args.output.open('x') as f:f.write('{}')
report={'scope':'独立合成局/临时SQLite；真实模型语义规划与类型化能力执行；确认语义由模型理解、宿主承接，不读取玩家历史','cases':[]}
try:
 with tempfile.TemporaryDirectory() as folder:
  for number,query in enumerate(['再来一局难一点的','换个场景，先推荐一个进阶对练方案']):
   store=Memory(Path(folder)/f'{number}.db');m=new_match('fire',42)
   while not m['battle']['ended']:m=advance(m,'move 1',expected_round=len(m['frames']))
   store.save_match(m);started=time.monotonic()
   result=control_reply(query,m,store.summary(),'live')
   case={'query':query,'prepared':result}
   if number==1:
    assert result.get('proposal'),'The proposal must be structured, not a verbal promise'
    m['pending_action']=result['proposal']
    m['messages'].extend([{'speaker':'user','kind':'chat','text':query},
        {'speaker':'assistant','kind':'chat','text':result['reply'],'proposal_id':result['proposal']['id']}])
    store.save_match(m)
    result=control_reply('好的',store.latest_match(),store.summary(),'live')
    case['confirmation']=result;execution_query='好的'
   else:execution_query=query
   assert result.get('command')
   current,actual=apply_command(store,m,result,execution_query,f'case-{number}')
   case.update({'seconds':round(time.monotonic()-started,3),'execution':actual['execution'],
    'checks':{'new_id':current['id']!=m['id'],'zero_turns':current['battle']['history']==[],
     'challenge':current['battle']['difficulty']=='challenge','policy':current['battle']['opponentPolicy']=='public-damage-v1',
     'saved':store.latest_match()['id']==current['id']}})
   assert all(case['checks'].values());report['cases'].append(case)
 report['status']='passed'
except Exception as e:
 report['status']='failed';report['error']=str(e);report['metadata']=getattr(e,'metadata',{})
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'status':report['status'],'cases':len(report['cases']),'error':report.get('error')},ensure_ascii=False))
