"""Synthetic real-provider background review; no private player records."""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.match import new_match,advance
from rococoach.match_coach import review_match
from rococoach.review_jobs import review_job
from rococoach.zh import dialogue

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
report={'scope':'独立合成局、真实后台流式调用，非普遍性能或语义准确率评估。','progress':[]}
with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False)
m=new_match('practice',47)
while not m['battle']['ended']:m=advance(m,'move 3',expected_round=len(m['frames']))
t0=time.monotonic();job=review_job(m,{'profile':{'nickname':'Mira','preference':'简洁'},'recent':[]},'live',review_match)
report['dispatch_seconds']=round(time.monotonic()-t0,4);previous=None
while not job.future.done():
 state=job.snapshot();key=(state['status'],len(state['draft']))
 if key!=previous:
  report['progress'].append({'seconds':state['seconds'],'status':state['status'],'visible_characters':len(state['draft'])});previous=key
 time.sleep(.1)
try:
 report['result']=job.future.result()
 raw=report['result']['answer']['reply'];report['displayed']=dialogue(raw)
 report['display_preserved']=report['displayed']==raw
 print(json.dumps({'dispatch_seconds':report['dispatch_seconds'],'stream':report['result']['metadata']['stream'],
  'final_characters':len(report['displayed']),'not_replaced_by_placeholder':'未转换' not in report['displayed']},ensure_ascii=False))
except Exception as exc:
 report['error']=str(exc);report['metadata']=getattr(exc,'metadata',{});print(str(exc))
a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
