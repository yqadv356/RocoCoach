from copy import deepcopy

import pytest

from rococoach.battle import simulate
from rococoach.companion import coach_reply, Reply
from rococoach.memory import Memory
from rococoach.routing import route_query


@pytest.mark.parametrize('query,expected',[
    ('这回合怎么选？','军师'),('帮我推荐下一招','军师'),
    ('为什么十万伏特更合适？','老师'),('没看懂，解释一下','老师'),
    ('我有点挫败','陪聊'),('先不讲道理，陪我聊聊','陪聊'),
    ('我输了很难过，但下一招怎么选？','军师'),
    ('别分析属性了，先陪我聊天','陪聊'),('你好呀','陪聊'),
])
def test_one_coach_routes_explicit_needs(query,expected):
    r=route_query(query)
    assert r.role==expected
    assert r.version=='intent-rules-v1'


def test_scene_events_and_followup_have_traceable_priority():
    assert route_query('怎么选',event='review').role=='老师'
    r=route_query('然后呢',history=[{'role':'老师'}])
    assert r.role=='老师' and r.source=='history'
    assert route_query('随便说点',battle={'ended':True}).source=='scene'
    assert route_query('我很累了',battle={'ended':True}).role=='陪聊'


def test_unified_entry_passes_selected_style_and_retains_routing(tmp_path,monkeypatch):
    captured=[]
    def fake(system,payload,schema):
        captured.append(payload)
        return Reply(reply='先比较命中率，再看伤害。',evidence_ids=['move 1'],suggested_choice='move 1'),{'mode':'live'}
    monkeypatch.setattr('rococoach.companion.structured_call',fake)
    b=simulate();memory=Memory(tmp_path/'m.db').summary()
    a=coach_reply('怎么选？',b,memory,mode='live',agentic=False)
    c=coach_reply('为什么这样选？',b,memory,mode='live',agentic=False)
    assert [p['role'] for p in captured]==['军师','老师']
    assert a['routing']['source']=='query' and c['routing']['role']=='老师'


def test_transfer_scene_and_previous_turn_are_not_confused(tmp_path):
    from rococoach.session import select_context
    from rococoach.tutor import next_quiz,make_context
    b=simulate();after=simulate(history=['move 1'])
    context=make_context(b,after,'move 1','想稳一点',Memory(tmp_path/'ctx.db').summary())
    lesson={'before':b,'after':after,'context':context,'result':{},'quiz':next_quiz('electric',42)}
    recent=select_context(lesson,'刚才为什么用十万伏特？')
    current=select_context(lesson,'喷火龙这回合怎么选？')
    assert recent.source=='previous_turn' and recent.battle['scenario']=='electric'
    assert recent.lesson_context['selected_choice']=='move 1'
    assert current.source=='transfer_quiz' and current.battle['scenario']=='fire'
    assert current.lesson_context is None


def test_chat_does_not_evict_learning_memory(tmp_path):
    m=Memory(tmp_path/'history.db');m.add('review','review',{'topic':'属性与命中'})
    for i in range(40):m.add(str(i),'chat',{'user':'你好','assistant':'我在','role':'陪聊'})
    assert m.summary()['recent'][0]['topic']=='属性与命中'


@pytest.mark.parametrize('choice,refs',[
    ('switch 6',['move 1']),('move 2',['move 1']), (None,['move 1']),
])
def test_strategist_action_and_reference_must_agree(tmp_path,monkeypatch,choice,refs):
    from rococoach.llm import ModelUnavailable
    def fake(*args):return Reply(reply='建议十万伏特。',evidence_ids=refs,suggested_choice=choice),{'mode':'live'}
    monkeypatch.setattr('rococoach.companion.structured_call',fake)
    with pytest.raises(ModelUnavailable):
        coach_reply('怎么选？',simulate(),Memory(tmp_path/'guard.db').summary(),mode='live',agentic=False)


def test_followup_uses_current_teaching_exchange():
    from rococoach.session import dialogue_history
    lesson={'messages':[
        {'speaker':'user','text':'我选十万伏特','kind':'decision'},
        {'speaker':'assistant','text':'先看命中和伤害','kind':'review'},
        {'speaker':'user','text':'刚才的回答失败了','kind':'chat'},
    ]}
    history=dialogue_history(lesson)
    assert len(history)==1 and history[0]['role']=='老师'
    assert route_query('然后呢',history=history).role=='老师'


def test_reject_overconfident_live_wording_even_with_valid_references(tmp_path,monkeypatch):
    from rococoach.llm import ModelUnavailable
    def fake(*args):
        return Reply(reply='十万伏特是必中招式。',evidence_ids=['move 1'],suggested_choice='move 1'),{'mode':'live'}
    monkeypatch.setattr('rococoach.companion.structured_call',fake)
    with pytest.raises(ModelUnavailable,match='绝对'):
        coach_reply('为什么推荐？',simulate(),Memory(tmp_path/'wording.db').summary(),mode='live',agentic=False)


def test_teaching_followup_binds_pre_action_time(tmp_path,monkeypatch):
    from rococoach.tutor import make_context
    b=simulate();after=simulate(history=['move 1'])
    memory=Memory(tmp_path/'timing.db').summary()
    ctx=make_context(b,after,'move 1','先比较命中',memory)
    def fake(system,payload,schema):
        assert payload['teaching_focus']['当时对方生命']==119
        assert after['opponent']['hp']==17
        assert '倒推' in payload['teaching_focus']['任务']
        return Reply(reply='比较出招前的命中与伤害。',evidence_ids=['calc:thunderbolt']),{'mode':'live'}
    monkeypatch.setattr('rococoach.companion.structured_call',fake)
    coach_reply('刚才为什么这样选？',after,memory,mode='live',agentic=False,lesson_context=ctx)


def test_support_route_omits_active_tactics_but_keeps_dialogue_context(tmp_path,monkeypatch):
    def fake(system,payload,schema):
        assert payload['facts']==[] and payload['legal_choices']==[]
        assert payload['history']==[{'role':'军师','user':'怎么选','assistant':'伤害86～104'}]
        assert '本轮自然交谈' in system
        return Reply(reply='听起来有点累。想先歇一下吗？',evidence_ids=[]),{'mode':'live'}
    monkeypatch.setattr('rococoach.companion.structured_call',fake)
    coach_reply('先别讲道理，陪我聊聊',simulate(),Memory(tmp_path/'support.db').summary(),
                history=[{'role':'军师','user':'怎么选','assistant':'伤害86～104'}],mode='live',agentic=False)


def test_completed_quiz_keeps_scene_and_assessment_context():
    from rococoach.session import select_context
    from rococoach.tutor import next_quiz
    quiz=next_quiz('electric',42)
    lesson={'before':simulate(),'result':{},'quiz':quiz,
            'quiz_result':{'correct':True,'selected':quiz['correct_choice']},'quiz_assisted':True}
    chosen=select_context(lesson,'刚才这题我选对了吗？')
    assert chosen.battle['scenario']=='fire'
    assert chosen.practice_result['判断与计算一致'] is True
    assert chosen.practice_result['是否使用提示'] is True
    assert route_query('这题我选对了吗？').role=='老师'
