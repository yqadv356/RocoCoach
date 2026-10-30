"""Offline retrieval-only comparison; no LLM calls or private player data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rococoach.retrieval import retrieve


def legacy(query,docs):
    ranked=sorted(((sum(t in query for t in d['terms']),d) for d in docs),key=lambda x:x[0],reverse=True)
    return [d['id'] for score,d in ranked if score>0][:2]


def evaluate(split='all'):
    dataset=json.loads((ROOT/'data/rag_eval.json').read_text())
    corpus=json.loads((ROOT/'data/rag_corpus.json').read_text())
    old=json.loads((ROOT/'data/coach_knowledge.json').read_text())
    cases=[c for c in dataset['cases'] if split=='all' or c['split']==split]
    rows=[]
    for c in cases:
        result=retrieve(c['query'])
        rows.append(dict(c,results={
            'old_4_keyword':legacy(c['query'],old),
            'new_26_keyword':legacy(c['query'],corpus['documents']),
            'new_26_bm25_alias':[d['id'] for d in result['hits']]},new_reason=result['reason']))
    metrics={}
    for group in sorted({c['split'] for c in rows}):
        metrics[group]={}
        for method in ['old_4_keyword','new_26_keyword','new_26_bm25_alias']:
            pos=[r for r in rows if r['split']==group and r['expected']]
            neg=[r for r in rows if r['split']==group and not r['expected']]
            ranks=[next((i+1 for i,id in enumerate(r['results'][method]) if id in r['expected']),0) for r in pos]
            metrics[group][method]={'answerable_cases':len(pos),'hit_at_2':sum(bool(r) for r in ranks)/max(len(pos),1),
                'mrr_at_2':sum(1/r if r else 0 for r in ranks)/max(len(pos),1),
                'unanswerable_cases':len(neg),'correct_empty':sum(not r['results'][method] for r in neg)}
    return {'scope':dataset['note'],'split':split,'metrics':metrics,'cases':rows,
            'dataset_hash':hashlib.sha256((ROOT/'data/rag_eval.json').read_bytes()).hexdigest(),
            'corpus_hash':corpus['corpus_hash'],
            'retriever_source_hash':hashlib.sha256((ROOT/'rococoach/retrieval.py').read_bytes()).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--split',choices=['all','dev','holdout'],default='all');parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.output and args.output.exists():raise SystemExit('拒绝覆盖旧评测。')
    result=evaluate(args.split)
    if args.output:
        with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result['metrics'],ensure_ascii=False,indent=2))
    for c in result['cases']:
        hits=c['results']['new_26_bm25_alias']
        if (bool(c['expected']) and not set(c['expected'])&set(hits)) or (not c['expected'] and hits):
            print('未通过:',c['id'],c['query'],hits)
