from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from rococoach.agent import AgentFailure,Environment,run_agent
from rococoach.battle import simulate
from rococoach.companion import Reply
from rococoach.llm import ModelConfig,tool_step
from rococoach.memory import Memory
from rococoach.tutor import make_context,TutorAnswer,mock_answer


@pytest.fixture
def env(tmp_path):
    return Environment(simulate(),Memory(tmp_path/'agent.db').summary())


def call(name,args,id='c1'):
    c={'id':id,'name':name,'arguments':json.dumps(args)}
    return {'content':'','calls':[c], 'wire':{'role':'assistant','tool_calls':[
        {'id':id,'type':'function','function':{'name':name,'arguments':c['arguments']}}]},
        'provider':'fake','model':'test-double','usage':{'total_tokens':5}}


def final(reply,refs,choice=None):
    return {'content':json.dumps({'reply':reply,'evidence_ids':refs,'suggested_choice':choice}),
        'calls':[],'wire':{},'provider':'fake','model':'test-double','usage':{'total_tokens':7}}


def test_native_tool_step_preserves_wire_and_bounds_timeout(monkeypatch):
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    captured={}
    msg=ChatCompletionMessage(role='assistant',tool_calls=[{'id':'one','type':'function','function':{'name':'inspect_battle','arguments':'{}'}}])
    class Client:
        def __init__(self,**kwargs):
            captured.update(kwargs)
            def create(**kw):
                captured.update(kw)
                return SimpleNamespace(choices=[SimpleNamespace(message=msg,finish_reason='tool_calls')],usage=None)
            self.chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        def close(self):captured['closed']=True
    monkeypatch.setattr('rococoach.llm.OpenAI',Client)
    r=tool_step([],[],remaining_seconds=3)
    assert r['calls'][0]['name']=='inspect_battle'
    assert r['wire']['tool_calls'][0]['id']=='one'
    assert captured['timeout']==3 and captured['max_retries']==0
    assert captured['extra_body']=={'enable_thinking':False} and captured['closed']


def test_model_observes_tool_output_before_answer(env,monkeypatch):
    requests=[]
    def step(messages,*args,**kwargs):
        requests.append(deepcopy(messages))
        if len(requests)==1:return call('inspect_battle',{})
        if len(requests)==2:
            assert json.loads(messages[-1]['content'])['evidence'][0]['id']=='state'
            return call('compare_moves',{'choices':['move 1','move 4']},'c2')
        return final('先比较十万伏特。',['move 1'],'move 1')
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    answer,meta=run_agent('测试','怎么选',Reply,env)
    assert answer.suggested_choice=='move 1'
    assert meta['agent']['model_calls']==3 and meta['agent']['tool_calls']==2
    assert meta['usage']['total_tokens']==17
    assert meta['agent']['stop_reason']=='validated_final'


@pytest.mark.parametrize('tool,args',[
    ('execute_shell',{}),('compare_moves',{'choices':['switch 6']}),
    ('inspect_battle',{'extra':'bad'}),('simulate_alternative',{'choice':'move 99'}),
    ('plan_practice',{'focus':'综合比较','evidence_ids':['imaginary']}),
])
def test_unknown_tools_and_bad_arguments_do_not_change_scene(env,tool,args):
    original=deepcopy(env.battle)
    with pytest.raises(ValueError):env.execute(tool,json.dumps(args))
    assert env.battle==original and env.plan is None


def test_empty_retrieval_does_not_invent_evidence(env):
    r=env.execute('search_rules',json.dumps({'query':'完全未知的兑换码机制'}))
    assert r['found'] is False and r['evidence']==[] and set(env.seen)=={'retrieval:coverage'}
    matched=env.execute('search_rules',json.dumps({'query':'命中概率与落空风险'}))
    assert matched['found'] and matched['evidence'][0]['id']=='kb:accuracy'


def test_counterfactual_replay_does_not_execute_in_current_game(env):
    original=deepcopy(env.battle)
    out=env.execute('simulate_alternative',json.dumps({'choice':'move 4'}))
    assert env.battle==original
    assert out['evidence'][0]['data']['对方生命后']==0
    assert out['evidence'][0]['id']=='branch:move_4'


def test_tool_failure_is_observed_and_can_be_repaired(env,monkeypatch):
    outputs=[call('compare_moves',{'choices':['illegal']},'bad'),
             call('inspect_battle',{},'good'),final('先看看当前局面。',['state'])]
    n=0
    def step(messages,*args,**kw):
        nonlocal n
        if n==1:assert 'error' in json.loads(messages[-1]['content'])
        r=outputs[n];n+=1;return r
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    _,meta=run_agent('测试','看看',Reply,env)
    assert 'error' in meta['agent']['trace'][0]['observation']
    assert meta['agent']['trace'][1]['tool']=='inspect_battle'


def test_fabricated_citation_is_not_a_completed_answer(env,monkeypatch):
    outputs=[call('inspect_battle',{}),final('知道了',['invented'])]
    monkeypatch.setattr('rococoach.agent.tool_step',lambda *a,**k:outputs.pop(0))
    with pytest.raises(AgentFailure) as e:run_agent('测试','解释',Reply,env,max_rounds=2)
    assert any('validation_error' in t for t in e.value.trace)


def test_loop_budget_stops_repeated_calls(env,monkeypatch):
    counter=0
    def step(*a,**k):
        nonlocal counter
        counter+=1;return call('inspect_battle',{},str(counter))
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    with pytest.raises(AgentFailure):run_agent('测试','查证',Reply,env,max_rounds=3,max_tools=1)
    assert counter==2


def test_zero_time_budget_never_contacts_model(env,monkeypatch):
    def unexpected(*a,**kw):raise AssertionError('must not run')
    monkeypatch.setattr('rococoach.agent.tool_step',unexpected)
    with pytest.raises(AgentFailure,match='时间'):run_agent('测试','查证',Reply,env,budget_seconds=0)


def test_review_requires_observed_facts_and_proposed_practice(env,monkeypatch):
    b=env.battle;ctx=make_context(b,simulate(history=['move 4']),'move 4','威力高',env.memory)
    env.review_context=ctx
    answer=mock_answer(ctx)
    outputs=[call('inspect_review',{}),call('plan_practice',{'focus':'命中与风险','evidence_ids':['turn:1']},'plan'),
        {'content':answer.model_dump_json(),'calls':[],'wire':{},'provider':'fake','model':'test-double','usage':{}}]
    monkeypatch.setattr('rococoach.agent.tool_step',lambda *a,**kw:outputs.pop(0))
    _,meta=run_agent('测试','复盘',TutorAnswer,env)
    assert meta['agent']['practice_plan']['focus']=='命中与风险'
    assert env.memory['recent']==[]  # A proposal does not write a permanent player trait.


def test_final_business_validation_can_trigger_repair(env,monkeypatch):
    responses=[call('inspect_battle',{}),final('必中',['state']),final('这里是标称概率。',['state'])]
    def step(messages,*a,**kw):
        if len(responses)==1:assert '绝对' in messages[-1]['content']
        return responses.pop(0)
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    def check(a,e):
        from rococoach.zh import validate_claim_language
        validate_claim_language(a.reply)
    a,meta=run_agent('测试','解释',Reply,env,validator=check)
    assert a.reply=='这里是标称概率。'
    assert meta['agent']['trace'][1]['rejected_output']


def test_repeated_tool_request_reuses_observation(env,monkeypatch):
    outputs=[call('inspect_battle',{},'first'),call('inspect_battle',{},'second'),final('已核对。',['state'])]
    monkeypatch.setattr('rococoach.agent.tool_step',lambda *a,**k:outputs.pop(0))
    _,meta=run_agent('测试','核对',Reply,env)
    assert meta['agent']['trace'][1]['cached'] is True


@pytest.mark.parametrize('query',['如果当时用打雷会怎样？','帮我查一下命中规则','对比一下这两招'])
def test_investigation_queries_reach_tool_capable_style(query):
    from rococoach.routing import route_query
    assert route_query(query).role=='老师'


@pytest.mark.parametrize('text',['不保证实战胜率或必中效果。','标称命中率不等于必中。','这不是绝对最优。'])
def test_negated_limits_are_not_false_positive(text):
    from rococoach.zh import validate_claim_language
    validate_claim_language(text)


@pytest.mark.parametrize('text',['这招必中。','虽然不是最强，但我保证获胜。','我不太确定，不过这招必胜。'])
def test_positive_guarantees_remain_rejected(text):
    from rococoach.zh import validate_claim_language
    from rococoach.llm import ModelUnavailable
    with pytest.raises(ModelUnavailable):validate_claim_language(text)


def test_exact_branch_outcome_has_independent_display(env):
    from rococoach.agent import branch_summary
    env.execute('simulate_alternative',json.dumps({'choice':'move 4'}))
    shown=branch_summary({'agent':{'observed_evidence':list(env.seen.values())}})
    assert '119 → 0' in shown and '实际对局未改变' in shown
    assert branch_summary({})==''
