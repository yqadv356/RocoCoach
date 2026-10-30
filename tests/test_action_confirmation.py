from copy import deepcopy
import json
import time

import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT,simulate
from rococoach.control import apply_command,control_reply,token
from rococoach.offline_control import ControlEnvironment
from rococoach.match import new_match,advance
from rococoach.memory import Memory


def finished():
    m=new_match('fire',42)
    while not m['battle']['ended']:m=advance(m,'move 1',expected_round=len(m['frames']))
    return m


def proposed(m):
    env=ControlEnvironment(m,{},'换个场景，先推荐一个')
    env.execute('propose_new_match',json.dumps({'scenario':'practice','difficulty':'challenge'}))
    m['pending_action']=env.proposal
    m['messages'].append({'speaker':'assistant','kind':'chat','text':'现在开始吗？','proposal_id':env.proposal['id']})
    return m


def test_typed_proposal_confirmation_executes_once_after_restore(tmp_path):
    m=proposed(finished());store=Memory(tmp_path/'db');store.save_match(m)
    restored=store.latest_match();before=deepcopy(restored)
    result=control_reply('好的',restored,{},'mock')
    assert restored==before and result['command']['proposal_id']==m['pending_action']['id']
    current,execution=apply_command(store,restored,result,'好的','confirmation')
    assert current['battle']['difficulty']=='challenge' and current['battle']['history']==[]
    assert current['battle']['scenario']=='practice'
    assert control_reply('好的',current,{},'mock') is None
    with store.connect() as db:
        old=json.loads(db.execute('SELECT value FROM match_sessions WHERE id=?',(m['id'],)).fetchone()[0])
    assert 'pending_action' not in old and old['frames']==before['frames']


@pytest.mark.parametrize('change',['expired','progress'])
def test_confirmation_rejects_expired_or_stale_proposal(change):
    m=proposed(new_match())
    if change=='expired':m['pending_action']['expires_at']=time.time()-1
    else:m=advance(m,'move 1',expected_round=0)
    result=control_reply('可以',m,{},'mock')
    assert result['command'] is None and result['clear_pending']


def test_cancel_and_unrelated_yes_do_not_start():
    m=proposed(finished())
    result=control_reply('取消',m,{},'mock')
    assert result['clear_pending'] and result['command'] is None
    assert control_reply('好的',finished(),{},'mock') is None


def test_legacy_offered_game_is_confirmed_not_repeated(tmp_path):
    m=finished();m['messages'].extend([
        {'speaker':'user','kind':'chat','text':'再来个难一点的对局'},
        {'speaker':'assistant','kind':'chat','text':'要我现在给你开一局“喷火龙 对阵 妙蛙花”吗？'}])
    store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('好的',m,{},'mock')
    current,actual=apply_command(store,m,result,'好的','legacy-confirm')
    assert current['battle']['scenario']=='fire'
    assert current['battle']['difficulty']=='challenge'
    assert current['battle']['history']==[] and '已经开始' in actual['reply']


def test_explicit_request_cannot_be_turned_into_another_question():
    env=ControlEnvironment(finished(),{},'再来一局难一点')
    with pytest.raises(ValueError,match='明确要求'):env.execute('propose_new_match','{"scenario":"practice"}')


def test_unverified_engine_effect_cannot_be_reported_success(semantic_plan_stub,monkeypatch,tmp_path):
    semantic_plan_stub(operation='start_new_match',speech_act='request',difficulty='challenge')
    m=finished();store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('这次别放水了，换盘新的',m,{},'live')
    monkeypatch.setattr('rococoach.control.new_match',lambda *a,**k:deepcopy(m))
    with pytest.raises(RuntimeError,match='未满足'):apply_command(store,m,result,'这次别放水了，换盘新的','effect')
    assert store.latest_match()==m


def test_ui_yes_after_legacy_offer_actually_starts(tmp_path,monkeypatch):
    from rococoach.llm import ModelUnavailable
    m=finished();m['messages'].extend([
        {'speaker':'user','kind':'chat','text':'再来一局难一点'},
        {'speaker':'assistant','kind':'chat','text':'要我现在开一局喷火龙对阵妙蛙花吗？'}])
    path=tmp_path/'ui.db';Memory(path).save_match(m)
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def offline():raise ModelUnavailable('offline')
    monkeypatch.setattr('rococoach.llm.configuration',offline)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.chat_input[0].set_value('好的').run()
    assert not app.exception
    current=app.session_state['match']
    assert current['id']!=m['id'] and current['battle']['history']==[]
    assert current['battle']['difficulty']=='challenge'
    assert any(b.label=='出招' for b in app.button)
    app.run()
    assert app.session_state['match']['id']==current['id']


def test_challenge_policy_changes_real_opponent_and_replays():
    normal=simulate('practice',42,autoplay=True,ruleset='short-pp-v1')
    hard=simulate('practice',42,autoplay=True,ruleset='short-pp-v1',difficulty='challenge')
    assert hard['opponentPolicy']=='public-damage-v1'
    assert hard['log']!=normal['log']
    replay=simulate('practice',42,hard['history'],ruleset='short-pp-v1',difficulty='challenge')
    assert replay['log']==hard['log'] and hard['ended']
    assert normal['lessons']==hard['lessons']  # No hidden player/stat/PP changes.


def test_challenge_round_branch_and_snapshot_keep_policy():
    from rococoach.match_tools import replay_alternative,AlternativeArgs
    m=new_match('practice',42,ruleset='short-pp-v1',difficulty='challenge')
    m=advance(m,'move 1',expected_round=0)
    assert m['frames'][0]['before']['difficulty']=='challenge'
    result=replay_alternative(m,AlternativeArgs(turn=1,choice='move 2'))
    expected=simulate('practice',42,['move 2'],ruleset='short-pp-v1',difficulty='challenge')
    assert result['复现参数']['训练档位']=='challenge'
    assert result['分支回合结束']['己方剩余生命']==expected['player']['hp']


def test_replaced_pending_proposal_cannot_execute_old_confirmation(tmp_path):
    m=proposed(finished());store=Memory(tmp_path/'db');store.save_match(m)
    prepared=control_reply('好的',m,{},'mock')
    changed=deepcopy(m);changed['pending_action']['id']='new-proposal';store.save_match(changed)
    with pytest.raises(ValueError,match='变化'):apply_command(store,m,prepared,'好的','stale-proposal')
    assert store.latest_match()['id']==m['id']
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM control_requests').fetchone()[0]==0


def test_yes_to_intervening_chat_does_not_execute_old_proposal():
    m=proposed(finished())
    m['messages'].extend([{'speaker':'user','kind':'chat','text':'先聊会儿'},
        {'speaker':'assistant','kind':'chat','text':'好，先休息一下。'}])
    assert control_reply('好的',m,{},'mock') is None
