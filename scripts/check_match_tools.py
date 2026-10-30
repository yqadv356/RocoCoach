"""Synthetic real-model tool acceptance run; never reads private player records."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.match import new_match,advance
from rococoach.match_coach import match_chat
from rococoach.match_tools import digest

parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
report={'scope':'合成整局、真实原生工具调用；不是独立玩家效果评估。','runs':[]}
# Reserve path before any paid request; preserve all failures rather than overwrite.
with args.output.open('x') as f:json.dump(report,f,ensure_ascii=False)
game=new_match()
while not(game['battle']['ended'] or game['battle']['capped']):
    game=advance(game,'move 1','合成演示，赛后核对',expected_round=len(game['frames']))
original=digest(game)
for question in ['这局哪些回合值得回看？请查关键回合再结合具体记录解释。',
                 '如果第2回合把水枪换成撞击会怎样？请实际独立重放那个回合，比较双方剩余生命，说明局限。']:
    entry={'question':question};report['runs'].append(entry)
    try:
        entry['result']=match_chat(question,game,{'profile':{},'recent':[]},'live',on_event=lambda e:None)
        entry['tools']=[t['tool'] for t in entry['result']['metadata']['agent']['trace'] if 'tool' in t]
        print(json.dumps({'tools':entry['tools'],'reply':entry['result']['reply']},ensure_ascii=False),flush=True)
    except (ValueError,RuntimeError) as exc:
        entry['error']=str(exc);entry['metadata']=getattr(exc,'metadata',{})
        print(json.dumps({'error':str(exc)},ensure_ascii=False),flush=True)
    entry['match_unchanged']=digest(game)==original
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
