"""Small local lexical RAG: explicit aliases, BM25, provenance and abstention."""
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
import re

from rococoach.config import ROOT

VERSION='lexical-bm25-v1'
SCOPE='pokemon-gen9-teaching'
# Curated query expansions, not an embedding model or learned semantic rewriting.
ALIASES={'打不中':'命中','打不准':'命中','不准':'命中','空招':'命中 风险',
         '先出手':'优先度','先手':'优先度','下雨':'天气','雨天':'天气',
         'stab':'同属性加成','掉血':'生命变化','变强':'学习 进步','答对':'学习',
         '附加效果':'原始机制说明','面板威力':'威力','概率':'命中率'}


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def tokens(value):
    result=[]
    for part in re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]+',value.lower()):
        if re.match('[a-z0-9]',part):result.append(part)
        else:result.extend(part[i:i+2] for i in range(len(part)-1))
    return result


def expand(query):
    q=query.lower();added=[]
    for alias,replacement in ALIASES.items():
        if alias in q:added.append({'from':alias,'to':replacement})
    return q+' '+' '.join(a['to'] for a in added),added


def entity_present(alias,query):
    a=alias.lower();q=query.lower()
    if re.search('[a-z]',a):return bool(re.search(r'(?<![a-z])'+re.escape(a)+r'(?![a-z])',q))
    if len(a)==1:return q==a or q.startswith(a+'的')
    return a in q


@lru_cache(maxsize=4)
def _index(raw):
    corpus=json.loads(raw)
    if corpus.get('scope')!=SCOPE or corpus.get('schema_version')!=1:
        raise ValueError('知识库范围或格式不匹配。')
    if corpus.get('source_versions',{}).get('pokemon-showdown')!='0.11.11':
        raise ValueError('知识来源版本未审核。')
    docs=corpus['documents']
    if len({d['id'] for d in docs})!=len(docs):raise ValueError('知识证据ID重复。')
    if digest(docs)!=corpus['corpus_hash']:raise ValueError('知识库内容校验失败。')
    for d in docs:
        payload={k:v for k,v in d.items() if k!='content_hash'}
        if d['kind']!='principle' and d['source_version']!=corpus['source_versions']['pokemon-showdown']:
            raise ValueError('知识条目与来源版本不一致。')
        if d['scope']!=SCOPE or digest(payload)!=d['content_hash']:
            raise ValueError('知识条目内容或范围校验失败。')
    counters=[Counter(tokens(d['title']+' '+d['content']+' '+' '.join(d['terms']))) for d in docs]
    freq=Counter(t for c in counters for t in c)
    avg=sum(sum(c.values()) for c in counters)/max(len(docs),1)
    return corpus,counters,freq,avg


def retrieve(query,path=None,limit=2):
    if not isinstance(query,str) or not 1<=len(query.strip())<=100:raise ValueError('请使用1～100字检索。')
    if type(limit) is not int or not 1<=limit<=2:raise ValueError('最多检索两条。')
    raw=(path or ROOT/'data/rag_corpus.json').read_text()
    corpus,counters,freq,avg=_index(raw);docs=corpus['documents']
    expanded,aliases=expand(query);qt=set(tokens(expanded))
    meta={'retriever_version':VERSION,'alias_hash':digest(ALIASES),'corpus_hash':corpus['corpus_hash'],
          'query':query,'expanded_query':expanded.strip(),'expansions':aliases,'scope':SCOPE,
          'source_versions':corpus['source_versions'],'parameters':{'k1':1.2,'b':0.75,'top_k':limit},
          'candidate_scores':[]}
    if re.search(r'洛克|王者荣耀|和平精英',query):
        return dict(meta,found=False,reason='out_of_scope',hits=[])
    if re.search(r'兑换码|限时活动|充值|抽奖',query):
        return dict(meta,found=False,reason='unsupported_topic',hits=[])
    entities={d['id'] for d in docs if any(entity_present(a,query) for a in d.get('aliases',[]))}
    stripped=re.sub(r'^(?:请问|查一下|帮我查|查查|请帮我查)','',query).strip()
    named=re.match(r'^([\u4e00-\u9fffA-Za-z ]{1,12}?)(?:的)?(?:威力|命中率|优先度|属性)(?:是|多少|为|[？?]?$)',stripped)
    conceptual=bool(re.match(r'^(?:为什么|为何|如何|怎么|什么是)',stripped))
    if named and not conceptual and not entities and named[1] not in {'招式','技能','这个','标称','当前'}:
        return dict(meta,found=False,reason='entity_not_indexed',hits=[])
    anchors={t for d in docs for t in d['terms']}|{'同属性加成','生命变化','天气'}
    anchors-={'招式','技能','规则'}
    if not entities and not any(t in expanded for t in anchors):
        return dict(meta,found=False,reason='no_coverage_anchor',hits=[])
    ranked=[];n=len(docs)
    for d,counts in zip(docs,counters):
        dl=sum(counts.values());parts={}
        for term in qt & counts.keys():
            tf=counts[term];idf=math.log(1+(n-freq[term]+.5)/(freq[term]+.5))
            parts[term]=idf*tf*2.2/(tf+1.2*(.25+.75*dl/avg))
        bm25=sum(parts.values())
        entity_bonus=8.0 if d['id'] in entities else 0.0
        # Generic explanations prefer principle cards; exact entities prefer their own card.
        concept_bonus=(2.0*sum(t in expanded for t in d['terms']) if d['kind']=='principle' and not entities else 0.0)
        score=bm25+entity_bonus+concept_bonus
        eligible=(bool(parts) or d['id'] in entities) and (not entities or d['kind']=='principle' or d['id'] in entities)
        ranked.append((score,d,{'bm25':round(bm25,5),'entity_bonus':entity_bonus,'concept_bonus':concept_bonus,
            'matched_terms':sorted(parts),'eligible':eligible}))
    ranked.sort(key=lambda r:(-r[0],r[1]['id']))
    meta['candidate_scores']=[{'id':d['id'],'score':round(s,5),**detail} for s,d,detail in ranked[:5]]
    hits=[dict(d,retrieval_score=round(s,5),score_detail=detail) for s,d,detail in ranked if s>0 and detail['eligible']][:limit]
    return dict(meta,found=bool(hits),reason='matched' if hits else 'no_match',hits=hits)
