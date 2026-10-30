from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from rococoach.battle import simulate
from rococoach.match import new_match,advance
from rococoach.match_coach import MatchEnvironment,guide_reply
from rococoach.match_tools import digest


@pytest.fixture(scope='module')
def finished():
    game=new_match()
    while not(game['battle']['ended'] or game['battle']['capped']):
        game=advance(game,'move 1',expected_round=len(game['frames']))
    return game


def test_phase_gate_is_enforced_at_execution_not_only_tool_listing():
    game=new_match();env=MatchEnvironment(game,{})
    assert env.available()==['observe_public_state']
    for tool,raw in [('simulate_round_alternative','{"turn":1,"choice":"move 2"}'),('inspect_round','{"turn":1}'),('find_key_turns','{}')]:
        with pytest.raises(ValueError):env.execute(tool,raw)
    result=env.execute('observe_public_state','{}')
    assert 'advice' not in json.dumps(result) and 'minDamage' not in json.dumps(result)
    assert result['receipt']['phase']=='live'
    assert result['receipt']['input_hash']==digest(game)
    assert guide_reply('开始',game,{})['metadata']['observation_tool']['match_unchanged']


def test_alternative_replays_exact_prefix_without_mutating_finished_game(finished):
    original=deepcopy(finished);env=MatchEnvironment(finished,{})
    for turn in [1,2,len(finished['frames'])]:
        result=env.execute('simulate_round_alternative',json.dumps({'turn':turn,'choice':'move 2'}))
        data=result['evidence'][0]['data'];frame=finished['frames'][turn-1]
        replay=simulate('practice',42,frame['before']['history']+['move 2'])
        assert data['分支回合结束']['己方剩余生命']==replay['player']['hp']
        assert data['分支回合结束']['对手剩余生命']==replay['opponent']['hp']
        assert data['相对实际的剩余生命差']['己方']==replay['player']['hp']-frame['after']['player']['hp']
        assert data['实际回合结束']['己方剩余生命']==frame['after']['player']['hp']
        assert result['receipt']['output_hash']==digest({'evidence':result['evidence']})
        assert result['receipt']['input_hash']==digest(original)
    assert finished==original


def test_tools_reject_invalid_and_same_action_without_engine_call(finished,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('invalid request reached engine')
    monkeypatch.setattr('rococoach.match_tools.simulate',forbidden)
    env=MatchEnvironment(finished,{})
    for args in [{'turn':1,'choice':'move 1'},{'turn':60,'choice':'move 2'},
                 {'turn':'1','choice':'move 2'},{'turn':1,'choice':'switch 1'},
                 {'turn':1,'choice':'move 2','seed':0}]:
        with pytest.raises((ValueError,ValidationError)):env.execute('simulate_round_alternative',json.dumps(args))
    assert env.seen=={}


def test_key_turn_candidates_are_real_repeatable_and_include_ending(finished):
    env=MatchEnvironment(finished,{})
    first=env.execute('find_key_turns','{}')['evidence'][0]
    assert first==env.execute('find_key_turns','{}')['evidence'][0]
    selected=first['data']['候选回合'];turns=[c['回合'] for c in selected]
    assert len(turns)<=3 and turns==sorted(set(turns))
    assert finished['frames'][-1]['turn'] in turns
    assert all(1<=n<=len(finished['frames']) for n in turns)


def test_postgame_ui_shows_real_replay_receipt_without_extra_action_buttons(finished,tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from rococoach.battle import ROOT
    from rococoach.llm import ModelUnavailable
    from rococoach.memory import Memory
    path=tmp_path/'receipts.db';Memory(path).save_match(finished)
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def unavailable():raise ModelUnavailable('离线测试')
    monkeypatch.setattr('rococoach.llm.configuration',unavailable)
    observation=MatchEnvironment(finished,{}).execute('simulate_round_alternative','{"turn":2,"choice":"move 2"}')
    def reply(*args,**kw):
        if args[0]=='先聊聊':return {'reply':'好，先歇会儿。','role':'陪聊','routing':{},'metadata':{'mode':'mock'}}
        return {'reply':'已独立重放第二回合，具体数字见下方。','role':'老师','routing':{},
                'metadata':{'agent':{'trace':[{'tool':'simulate_round_alternative','observation':observation,
                                                'elapsed_seconds':0.1,'cached':False}]}}}
    monkeypatch.setattr('rococoach.match_coach.match_chat',reply)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.chat_input[0].set_value('第二回合换招会怎样').run()
    assert not app.exception
    assert any(e.label=='这次回答核对了什么' for e in app.expander)
    assert any('假设换招' in t.value.to_string() for t in app.table)
    assert any('固定种子单样本' in c.value for c in app.caption)
    assert len([b for b in app.button if b.label=='再来一局'])==1
    assert not any(b.label=='出招' for b in app.button)
    assert app.session_state['match']['battle']==finished['battle']
    app.chat_input[0].set_value('先聊聊').run()
    assert not app.exception
    assert any('假设换招' in t.value.to_string() for t in app.table)
    assert not any(c.value=='此条回复未调用战斗工具。' for c in app.caption)
    messages=app.session_state['match']['messages']
    assert messages[-1]['tool_report']['metadata']['agent']['trace']==[]
    assert messages[-3]['tool_report']['metadata']['agent']['trace'][0]['tool']=='simulate_round_alternative'


def test_agent_reserves_engine_budget_before_starting_branch(finished,monkeypatch):
    from rococoach.agent import run_agent,AgentFailure
    from rococoach.companion import Reply
    env=MatchEnvironment(finished,{})
    def forbidden(*a,**kw):raise AssertionError('insufficient budget reached engine')
    monkeypatch.setattr('rococoach.match_tools.simulate',forbidden)
    count=0
    def step(*a,**kw):
        nonlocal count
        count+=1
        if count==1:
            calls=[{'id':'budget-check','name':'simulate_round_alternative','arguments':'{"turn":2,"choice":"move 2"}'}]
            return {'provider':'fake','model':'fake','calls':calls,'wire':{'role':'assistant','content':None},'usage':{}}
        return {'provider':'fake','model':'fake','calls':[],'content':'{"reply":"无法查证","evidence_ids":[],"suggested_choice":null}','usage':{}}
    monkeypatch.setattr('rococoach.agent.tool_step',step)
    with pytest.raises(AgentFailure) as exc:run_agent('test','test',Reply,env,budget_seconds=20,max_rounds=2)
    assert exc.value.trace[0]['observation']['type']=='ValueError'
    assert not env.seen


@pytest.mark.parametrize('message',['请重新实际重放第2回合，将水枪改成撞击。','接着看第二回合的另一个分支。','第二回合还可以怎样处理。'])
def test_postgame_ambiguous_requests_keep_completed_match_context(finished,monkeypatch,message,semantic_plan_stub):
    semantic_plan_stub(operation='chat',speech_act='request',role='老师')
    from rococoach.match_coach import match_chat
    from rococoach.companion import Reply
    captured=[]
    def agent(system,query,schema,env,**kw):
        captured.append(env)
        return Reply(reply='先核对该回合。',evidence_ids=['match:turn:2']),{'mode':'live','agent':{}}
    monkeypatch.setattr('rococoach.match_coach.run_agent',agent)
    result=match_chat(message,finished,{},'live')
    assert result['routing']['context_source']=='completed_match'
    assert captured[0].match is finished
    assert result['role']=='老师'


def test_postgame_explicit_companionship_still_stays_lightweight(finished,monkeypatch,semantic_plan_stub):
    semantic_plan_stub(operation='chat',speech_act='request',role='陪聊')
    from rococoach.match_coach import match_chat
    def companion(*a,**kw):return {'reply':'好，先聊聊。','role':'陪聊'}
    def forbidden(*a,**kw):raise AssertionError('casual chat entered tool loop')
    monkeypatch.setattr('rococoach.companion.coach_reply',companion)
    monkeypatch.setattr('rococoach.match_coach.run_agent',forbidden)
    assert match_chat('先不讲道理，陪我聊聊',finished,{},'live')['role']=='陪聊'
