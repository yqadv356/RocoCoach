import json
from copy import deepcopy

import pytest

from rococoach.agent import Environment,run_agent
from rococoach.battle import simulate
from rococoach.companion import Reply
from rococoach.memory import Memory
from rococoach.retrieval import retrieve,digest
from scripts.build_knowledge import build


@pytest.mark.parametrize('query,expected',[
    ('抓','dex:move:scratch'),('这个招式老是打不准','kb:accuracy'),('STAB是啥','kb:damage'),
    ('Thunderbolt的威力','dex:move:thunderbolt'),
    ('电光一闪为什么先出手','dex:move:quickattack'),
    ('为什么不能只看面板威力','kb:ranking'),
])
def test_retrieval_supports_aliases_and_entities(query,expected):
    r=retrieve(query)
    assert expected in [d['id'] for d in r['hits']]
    assert r['corpus_hash'] and r['candidate_scores']
    assert all(d['content_hash'] and d['source_locator'] for d in r['hits'])


@pytest.mark.parametrize('query,reason',[
    ('洛克王国打雷命中率多少','out_of_scope'),
    ('地震的威力是多少','entity_not_indexed'),
    ('完全未知的兑换码机制','unsupported_topic'),
    ('明天限时活动送什么','unsupported_topic'),
])
def test_unsupported_topics_cannot_retrieve_other_moves(query,reason):
    r=retrieve(query)
    assert not r['found'] and not r['hits'] and r['reason']==reason


def test_corpus_rebuild_is_deterministic_and_from_pinned_dex():
    corpus=build()
    assert len(corpus['documents'])==26
    assert corpus['corpus_hash']==build()['corpus_hash']
    quick=next(d for d in corpus['documents'] if d['id']=='dex:move:quickattack')
    assert quick['facts']['priority']==1 and quick['facts']['power']==40
    assert quick['source_version']=='0.11.11'


@pytest.mark.parametrize('change',['body','version','duplicate','scope'])
def test_bad_corpus_is_rejected_not_silently_used(tmp_path,change):
    from rococoach.config import ROOT
    corpus=json.loads((ROOT/'data/rag_corpus.json').read_text())
    if change=='body':corpus['documents'][0]['content']='tampered'
    if change=='version':corpus['source_versions']['pokemon-showdown']='unreviewed'
    if change=='duplicate':corpus['documents'].append(deepcopy(corpus['documents'][0]))
    if change=='scope':corpus['scope']='roco-live'
    path=tmp_path/'bad.json';path.write_text(json.dumps(corpus))
    with pytest.raises(ValueError):retrieve('命中规则',path=path)


def test_explicit_knowledge_boundary_stops_generation(tmp_path,monkeypatch):
    env=Environment(simulate(),Memory(tmp_path/'scope.db').summary())
    calls=[]
    def step(*args,**kwargs):
        calls.append(1)
        return {'content':'','calls':[{'id':'one','name':'search_rules','arguments':json.dumps({'query':'地震的威力是多少'})}],
            'wire':{'role':'assistant','tool_calls':[{'id':'one','type':'function','function':{'name':'search_rules','arguments':json.dumps({'query':'地震的威力是多少'})}}]},
            'provider':'fake','model':'test-double','usage':{'total_tokens':12}}
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    answer,meta=run_agent('测试','地震的威力是多少',Reply,env)
    assert '未收录' in answer.reply and answer.suggested_choice is None
    assert meta['agent']['stop_reason']=='coverage_abstention'
    assert meta['answer_source']=='coverage_policy'
    assert len(calls)==1
    assert set(env.seen)=={'retrieval:coverage'}


def test_failed_agent_preserves_returned_usage(tmp_path,monkeypatch):
    from rococoach.agent import AgentFailure
    env=Environment(simulate(),Memory(tmp_path/'budget.db').summary())
    def step(*a,**k):return {'content':'{}','calls':[],'wire':{},'usage':{'total_tokens':17},'provider':'fake','model':'test-double'}
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    with pytest.raises(AgentFailure) as e:run_agent('测试','解释',Reply,env,max_rounds=2)
    assert e.value.metadata['usage']['total_tokens']==34
    assert e.value.metadata['agent']['model_calls']==2
    assert e.value.metadata['agent']['stop_reason']=='failed'
