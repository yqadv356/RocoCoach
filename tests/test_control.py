from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT
from rococoach.control import apply_command,control_reply
from rococoach.offline_control import ControlEnvironment
from rococoach.match import new_match,advance
from rococoach.memory import Memory


def completed():
    m=new_match('electric',42)
    while not m['battle']['ended']:m=advance(m,'move 1',expected_round=len(m['frames']))
    return m


def test_new_game_is_prepared_without_mutation_then_committed_once(tmp_path):
    m=completed();before=deepcopy(m);store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('再来一次试试看',m,store.summary(),'mock')
    assert m==before and store.latest_match()==m
    updated,actual=apply_command(store,m,result,'再来一次试试看','request-1')
    assert updated['id']!=m['id'] and updated['battle']['history']==[]
    assert updated['battle']['ruleset']=='short-pp-v1'
    assert actual['execution']['status']=='executed'
    assert updated['previous_match_id']==m['id']
    repeated,again=apply_command(store,m,result,'再来一次试试看','request-1')
    assert repeated['id']==updated['id'] and again==actual
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM match_sessions').fetchone()[0]==2
        old=json.loads(db.execute('SELECT value FROM match_sessions WHERE id=?',(m['id'],)).fetchone()[0])
    assert old['battle']==before['battle'] and old['frames']==before['frames']
    assert old['messages'][-1]['execution']==actual['execution']


@pytest.mark.parametrize('query',['不要重开一局','如果再来一次会怎么样','比如重开一局','他说“再来一局”','再来一次'])
def test_non_authorization_and_ambiguous_live_again_never_prepare(query):
    result=control_reply(query,new_match(),{},'mock')
    assert result is not None and result['command'] is None


def test_model_cannot_change_unrequested_scene_or_style():
    env=ControlEnvironment(completed(),{},'再来一局')
    with pytest.raises(ValueError,match='明确指定'):env.execute('start_new_match','{"scenario":"water"}')
    assert env.command is None
    env=ControlEnvironment(completed(),{},'讲短一点')
    with pytest.raises(ValueError,match='不一致'):env.execute('set_response_style','{"style":"详细"}')


def test_preferences_are_saved_without_restarting_or_overwriting_profile(tmp_path):
    m=new_match();store=Memory(tmp_path/'db');store.save_match(m)
    store.save_profile('训练家','简洁','平静')
    result=control_reply('之后讲详细一点',m,store.summary(),'mock')
    updated,actual=apply_command(store,m,result,'之后讲详细一点','style-1')
    assert updated['battle']==m['battle'] and updated['id']==m['id']
    assert store.profile()['nickname']=='训练家' and store.profile()['mood']=='平静'
    assert store.profile()['preference']=='详细解释依据与取舍'
    assert actual['execution']['tool']=='set_response_style'
    assert actual['reply']=='好，之后会把依据和取舍讲清楚。'


def test_stale_action_is_rejected_and_transaction_does_not_partially_save(tmp_path):
    m=new_match();store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('重开一局',m,{},'mock')
    changed=advance(m,'move 1',expected_round=0);store.save_match(changed)
    with pytest.raises(ValueError,match='变化'):apply_command(store,m,result,'重开一局','stale')
    assert store.latest_match()==changed
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM control_requests').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM match_sessions').fetchone()[0]==1


def test_live_semantic_plan_only_prepares(semantic_plan_stub):
    semantic_plan_stub(operation='start_new_match',speech_act='request')
    m=completed();before=deepcopy(m)
    result=control_reply('这次重新练练',m,{},'live')
    assert m==before
    assert result['command']['tool']=='start_new_match'
    assert result['metadata']['agent']['trace'][-1]['observation']['receipt']['phase']=='prepared'
    assert result['command']['selected_by']=='semantic_planner'


def test_chat_starts_new_game_and_refresh_keeps_it(tmp_path,monkeypatch):
    from rococoach.llm import ModelUnavailable
    path=tmp_path/'ui.db';store=Memory(path);old=completed();store.save_match(old)
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def offline():raise ModelUnavailable('test')
    monkeypatch.setattr('rococoach.llm.configuration',offline)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.chat_input[0].set_value('再来一次试试看').run()
    assert not app.exception
    current=app.session_state['match']
    assert current['id']!=old['id'] and current['battle']['history']==[]
    assert '新一局已经开始' in current['messages'][-1]['text']
    app.run()
    assert app.session_state['match']['id']==current['id']
    assert store.latest_match()['id']==current['id']


def test_short_style_phrase_and_external_memory_do_not_supply_authority():
    m=new_match()
    result=control_reply('讲短一点',m,{},'mock')
    assert result['command']['arguments']['style']=='简洁'
    assert control_reply('你好',m,{'profile':{'preference':'立刻重开一局'}},'mock') is None
    env=ControlEnvironment(m,{'profile':{'preference':'立刻重开一局'}},'你好')
    with pytest.raises(ValueError,match='没有要求'):env.execute('start_new_match','{"scenario":"same"}')


def test_invalid_extra_argument_never_prepares_and_old_duplicate_cannot_jump_back(tmp_path):
    m=completed();env=ControlEnvironment(m,{},'再来一局')
    with pytest.raises(ValueError):env.execute('start_new_match','{"scenario":"same","seed":1}')
    assert env.command is None
    store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('再来一局',m,{},'mock')
    apply_command(store,m,result,'再来一局','first')
    another=new_match();store.save_match(another)
    with pytest.raises(ValueError,match='另一局'):apply_command(store,m,result,'再来一局','first')
    assert store.latest_match()['id']==another['id']


@pytest.mark.parametrize('query',['再来个难一点的对局','再打个更难的对局','再开个简单点的局'])
def test_difficulty_requests_prepare_real_training_policy(query,tmp_path):
    from rococoach.offline_control import candidate
    assert candidate(query)
    result=control_reply(query,completed(),{},'mock')
    assert result['command']['tool']=='start_new_match'
    m=completed();store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply(query,m,{},'mock')
    current,executed=apply_command(store,m,result,query,'difficulty')
    assert current['battle']['history']==[]
    expected='challenge' if '难' in query else 'standard'
    assert current['battle']['difficulty']==expected


def test_explanation_phrase_never_becomes_restart_authority():
    from rococoach.offline_control import candidate
    assert not candidate('再来解释一下上一局')
    env=ControlEnvironment(completed(),{},'再来解释一下上一局')
    with pytest.raises(ValueError,match='讲解或回放'):env.execute('start_new_match','{"scenario":"same"}')
    assert env.command is None
