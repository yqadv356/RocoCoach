"""Build small, versioned knowledge cards from pinned local Dex; no scraping."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.battle import node_path
from rococoach.zh import name


def canonical_hash(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def build():
    raw=subprocess.run([node_path(),str(ROOT/'engine/export_knowledge.cjs')],
        input=(ROOT/'data/zh_catalog.json').read_text(),capture_output=True,text=True,check=True,timeout=20,cwd=ROOT/'engine')
    source=json.loads(raw.stdout)
    docs=[]
    for row in json.loads((ROOT/'data/coach_knowledge.json').read_text()):
        docs.append(dict(row,kind='principle',aliases=[],scope='pokemon-gen9-teaching',
                         source_version='project-rules-v1',source_locator='data/coach_knowledge.json#'+row['id']))
    for m in source['moves']:
        accuracy='不进行常规命中检定' if m['accuracy'] is True else f"标称命中率{m['accuracy']}%"
        docs.append({'id':'dex:move:'+m['id'],'kind':'move','scope':'pokemon-gen9-teaching',
            'title':m['zh']+'的招式资料','aliases':[m['zh'],m['name'],m['id']],
            'terms':[m['zh'],'威力','命中率','优先度','属性','招式'],
            'content':f"{m['zh']}：{name(m['type'])}属性，{name(m['category'])}招式，威力{m['power']}，{accuracy}，优先度{m['priority']}，基础可用次数{m['pp']}。这些是第九世代招式资料，不是当前伤害值或洛克王国规则。原始机制说明：{m['description']}",
            'facts':m,'source':'pokemon-showdown@'+source['version']+' Dex',
            'source_version':source['version'],'source_locator':'pokemon-showdown/data/moves.ts#'+m['id']})
    for p in source['species']:
        docs.append({'id':'dex:species:'+p['id'],'kind':'species','scope':'pokemon-gen9-teaching',
            'title':p['zh']+'的属性与特性','aliases':[p['zh'],p['name'],p['id']],
            'terms':[p['zh'],'属性','特性'],
            'content':f"{p['zh']}：{' / '.join(name(t) for t in p['types'])}属性；本项目已收录中文名的可能特性包括{'、'.join(name(a) for a in p['abilities'] if name(a)!='未收录名称')}。这是物种资料，可具有的特性不等于当前对局已装备的特性；当前能力与状态应查询局面工具。",
            'facts':p,'source':'pokemon-showdown@'+source['version']+' Dex',
            'source_version':source['version'],'source_locator':'pokemon-showdown/data/pokedex.ts#'+p['id']})
    for d in docs:d['content_hash']=canonical_hash(d)
    return {'schema_version':1,'scope':'pokemon-gen9-teaching','source_versions':{'pokemon-showdown':source['version']},
            'corpus_hash':canonical_hash(docs),'documents':docs}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'data/rag_corpus.json');parser.add_argument('--replace',action='store_true');args=parser.parse_args()
    data=build()
    if args.output.exists():
        old=json.loads(args.output.read_text())
        if old.get('corpus_hash')==data['corpus_hash']:
            print('知识库已是同一内容版本，无需覆盖。');raise SystemExit(0)
        if not args.replace:raise SystemExit('新旧知识版本不同；请另存新文件，或显式使用--replace。')
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'documents':len(data['documents']),'corpus_hash':data['corpus_hash']},ensure_ascii=False))
