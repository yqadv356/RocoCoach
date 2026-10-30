from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT,simulate
from rococoach.companion import Reply
from rococoach.llm import ModelUnavailable
from rococoach.match import advance,new_match,neutral_facts
from rococoach.match_coach import guide_reply,review_match,MatchEnvironment
from rococoach.memory import Memory


def finish_game():
    game=new_match()
    while not(game['battle']['ended'] or game['battle']['capped']):
        n=len(game['frames']);choice=next(m['choice'] for m in game['battle']['advice'] if not m['disabled'])
        game=advance(game,choice,'先考虑命中风险',expected_round=n)
    return game


def test_match_keeps_all_frames_and_replays_real_result():
    game=finish_game()
    assert len(game['frames'])>=3
    assert game['battle']['ended']
    assert simulate('practice',42,game['battle']['history'])['log']==game['battle']['log']
    for i,frame in enumerate(game['frames']):
        assert frame['before']['history']==game['battle']['history'][:i]
        assert frame['after']['history']==game['battle']['history'][:i+1]
        assert frame['reason']=='先考虑命中风险'
    with pytest.raises(ValueError):advance(game,'move 1',expected_round=len(game['frames']))


def test_stale_turn_and_bad_choice_cannot_mutate_match():
    game=new_match();original=deepcopy(game)
    with pytest.raises(ValueError):advance(game,'move 1',expected_round=1)
    with pytest.raises(ValueError):advance(game,'switch 6',expected_round=0)
    assert game==original


def test_guide_payload_cannot_access_ranking_or_next_opponent_choice(monkeypatch):
    game=new_match();events=[]
    def fake(system,payload,schema,**kwargs):
        raw=json.dumps(payload,ensure_ascii=False)
        for forbidden in ['minDamage','score','recommended','伤害分值','opponentChoice']:
            assert forbidden not in raw
        assert 'mood' not in payload['memory']['profile']
        kwargs['on_event']({'type':'draft','text':'咬住是最优'})
        return Reply(reply='咬住是最优',evidence_ids=[payload['facts'][0]['id']]),{'mode':'live'}
    monkeypatch.setattr('rococoach.match_coach.structured_call',fake)
    with pytest.raises(ModelUnavailable):guide_reply('告诉我答案',game,{},'live',on_event=events.append)
    assert not any(e['type']=='draft' for e in events)
    assert 'advice' not in json.dumps(neutral_facts(game))


def test_match_persists_and_turn_events_do_not_evict_learning(tmp_path):
    store=Memory(tmp_path/'m.db');game=new_match()
    game=advance(game,'move 2','想稳一点',expected_round=0)
    store.save_match(game)
    store.add('review','review',{'topic':'整局观察'})
    for i in range(10):store.add(str(i),'turn',{'topic':'逐回合'})
    restored=Memory(tmp_path/'m.db')
    assert restored.latest_match()==game
    assert restored.summary()['recent'][0]['topic']=='整局观察'


def test_teacher_only_after_finish_and_can_inspect_any_turn():
    with pytest.raises(ValueError):review_match(new_match(),{},'mock')
    game=finish_game();env=MatchEnvironment(game,{})
    fact=env.execute('inspect_round',json.dumps({'turn':2}))['evidence'][0]
    assert fact['data']['出招前公开状态']['history']==game['battle']['history'][:1]
    assert 'advice' not in fact['data']['出招前公开状态']
    assert 'recommended' not in fact['data']['实际结果']
    assert fact['data']['赛后才开放的计算']
    assert '局中没有看到' in fact['data']['信息边界']
    assert fact['data']['玩家理由']=='先考虑命中风险'
    with pytest.raises(ValueError):env.execute('inspect_round','{"turn":60}')
    result=review_match(game,{},'mock')
    assert 'match:summary' in result['answer']['evidence_ids']
    assert any(x.startswith('match:turn:') for x in result['answer']['evidence_ids'])


def test_main_page_whole_match_chat_and_restore(tmp_path,monkeypatch):
    path=tmp_path/'ui.db';monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def unavailable():raise ModelUnavailable('离线测试')
    monkeypatch.setattr('rococoach.llm.configuration',unavailable)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not app.exception
    for _ in range(15):
        game=app.session_state['match']
        if game['battle']['ended']:break
        app.chat_input[0].set_value('陪我聊聊').run()
        before=len(app.session_state['match']['frames'])
        next(b for b in app.button if b.label=='出招').click().run()
        assert not app.exception
        assert len(app.session_state['match']['frames'])==before+1
        if not app.session_state['match']['battle']['ended']:
            assert 'review' not in app.session_state['match']
            assert not any(b.label=='确认判断' for b in app.button)
    game=app.session_state['match']
    assert game['battle']['ended'] and 'review' in game
    assert len(game['frames'])>=3 and game['messages']
    store=Memory(path)
    assert len([e for e in store.recent(50) if e['kind']=='review'])==1
    restored=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert restored.session_state['match']['battle']['history']==game['battle']['history']
    assert len([e for e in store.recent(50) if e['kind']=='review'])==1


def test_failed_whole_match_review_retry_never_replays(tmp_path,monkeypatch):
    path=tmp_path/'retry.db';store=Memory(path);game=finish_game();store.save_match(game)
    original=deepcopy(game['battle']);calls=[]
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def unavailable():raise ModelUnavailable('离线测试')
    monkeypatch.setattr('rococoach.llm.configuration',unavailable)
    def flaky(game,memory,mode,**kwargs):
        calls.append(game['battle']['history'][:])
        if len(calls)==1:raise ModelUnavailable('模拟超时')
        return review_match(game,memory,'mock')
    monkeypatch.setattr('rococoach.match_coach.review_match',flaky)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not app.exception and 'review' not in app.session_state['match']
    next(b for b in app.button if b.label=='重试整局复盘').click().run()
    assert not app.exception
    assert app.session_state['match']['battle']==original
    assert calls[0]==calls[1]
    assert len([e for e in store.recent(50) if e['kind']=='review'])==1


def test_rejected_guide_is_not_streamed_and_player_can_still_play(tmp_path,monkeypatch):
    from rococoach.llm import ModelConfig
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'guide.db')
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    def reject(*args,**kwargs):raise ModelUnavailable('不能展示答案')
    monkeypatch.setattr('rococoach.match_coach.guide_reply',reject)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not app.exception
    assert any(item.value=='基础观察' for item in app.caption)
    assert not app.error
    assert not any(b.label=='重试提示' for b in app.button)
    next(b for b in app.button if b.label=='出招').click().run()
    assert not app.exception and len(app.session_state['match']['frames'])==1


def test_chat_guard_rejection_becomes_neutral_observation_not_error(tmp_path,monkeypatch):
    from rococoach.llm import ModelConfig
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'guard-chat.db')
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    def guide(*a,**k):return {'reply':'先观察当前状态。','metadata':{'mode':'live'}}
    def reject(*a,**k):
        exc=ModelUnavailable('提示包含具体答案或排序，本次不展示；你仍可独立出招。')
        exc.rejected_output='咬住是最优';raise exc
    monkeypatch.setattr('rococoach.match_coach.guide_reply',guide)
    monkeypatch.setattr('rococoach.match_coach.match_chat',reject)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    before=deepcopy(app.session_state['match']['battle'])
    app.chat_input[0].set_value('给点思路').run()
    assert not app.exception and not app.error
    assert not any('提示包含具体答案' in m.value or '咬住是最优' in m.value for m in app.markdown)
    game=app.session_state['match']
    assert game['battle']==before
    assert game['messages'][-1]['kind']=='chat_failed'
    assert game['messages'][-1]['response_source']=='program'
    assert game['chat_failures'][-1]['rejected_output']=='咬住是最优'
    assert Memory(tmp_path/'guard-chat.db').chat_history()==[]


def test_hint_with_empty_failure_metadata_is_not_retried_on_every_rerun(tmp_path,monkeypatch):
    from rococoach.llm import ModelConfig
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'hint-cache.db')
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    calls=[]
    def reject(*a,**k):
        calls.append(1);exc=ModelUnavailable('校验拒绝');exc.metadata={};raise exc
    monkeypatch.setattr('rococoach.match_coach.guide_reply',reject)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.run();app.run()
    assert len(calls)==1
    assert not app.exception and not app.error
