from copy import deepcopy
import time

import pytest

from rococoach.control import apply_command,control_reply,token
from rococoach.match import new_match,advance
from rococoach.memory import Memory
from rococoach.semantic_control import IntentPlan,semantic_snapshot,latest_reference


def ended():
    m=new_match('electric',42)
    while not m['battle']['ended']:m=advance(m,'move 1',expected_round=len(m['frames']))
    return m


@pytest.mark.parametrize('query',['这轮太温柔了，找个懂得还手的对手继续','别放水啦，安排一场新的训练','Game on, give me a tougher sparring partner.'])
def test_online_semantics_does_not_require_command_words(query,semantic_plan_stub,tmp_path):
    semantic_plan_stub(operation='start_new_match',speech_act='request',difficulty='challenge')
    m=ended();store=Memory(tmp_path/'db');store.save_match(m)
    before=deepcopy(m);result=control_reply(query,m,{},'live')
    assert m==before
    current,actual=apply_command(store,m,result,query,'semantic-new')
    assert current['id']!=m['id'] and current['battle']['history']==[]
    assert current['battle']['difficulty']=='challenge'
    assert actual['execution']['status']=='executed'


@pytest.mark.parametrize('speech',['negation','quotation','hypothetical','ambiguous'])
def test_semantic_non_requests_cannot_prepare_writes(speech,semantic_plan_stub):
    semantic_plan_stub(operation='start_new_match',speech_act=speech)
    m=ended();before=deepcopy(m)
    result=control_reply('当前消息交给语义规划识别',m,{},'live')
    assert result['command'] is None and m==before


def test_online_confirmation_has_no_literal_affirmative_list(semantic_plan_stub,tmp_path):
    m=ended();m['pending_action']={'id':'typed-pending','arguments':{'scenario':'practice','difficulty':'challenge'},
        'source_token':token(m),'expires_at':time.time()+60,'origin':'semantic_planner'}
    m['messages'].append({'speaker':'assistant','kind':'chat','text':'安排均衡进阶对练，现在开始吗？','proposal_id':'typed-pending'})
    semantic_plan_stub(operation='confirm_pending',speech_act='confirmation',reference='pending')
    store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('就照这个安排上',m,{},'live')
    current,_=apply_command(store,m,result,'就照这个安排上','semantic-confirm')
    assert current['battle']['history']==[] and current['battle']['difficulty']=='challenge'


def test_legacy_offer_reference_is_bound_without_parsing_pet_names(semantic_plan_stub,tmp_path):
    m=ended();m['messages'].append({'speaker':'assistant','kind':'chat','text':'这次换均衡进阶对练，可以现在出发。'})
    semantic_plan_stub(operation='confirm_pending',speech_act='confirmation',reference='latest_assistant',scenario='practice',difficulty='challenge')
    store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('那就动身',m,{},'live')
    assert result['command']['expected_offer_id']==latest_reference(m)['id']
    current,_=apply_command(store,m,result,'那就动身','legacy-semantic')
    assert current['battle']['scenario']=='practice'


def test_semantic_planner_failure_does_not_fall_back_to_phrase_execution(monkeypatch):
    def fail(*a,**kw):raise RuntimeError('planner unavailable')
    monkeypatch.setattr('rococoach.semantic_control.structured_call',fail)
    m=ended();before=deepcopy(m)
    with pytest.raises(RuntimeError):control_reply('再来一局',m,{},'live')
    assert m==before


def test_stale_semantic_confirmation_and_intervening_conversation(semantic_plan_stub):
    m=ended();m['pending_action']={'id':'p','arguments':{'scenario':'same','difficulty':'same'},'source_token':token(m),'expires_at':0}
    m['messages'].append({'speaker':'assistant','kind':'chat','text':'继续练吗','proposal_id':'p'})
    semantic_plan_stub(operation='confirm_pending',speech_act='confirmation',reference='pending')
    result=control_reply('就这么定',m,{},'live')
    assert result['command'] is None and result['clear_pending']
    m['messages'].append({'speaker':'assistant','kind':'chat','text':'今天先聊聊。'})
    assert semantic_snapshot(m,{})['pending'] is None


def test_style_plan_can_interpret_negative_form_without_blocking_it(semantic_plan_stub,tmp_path):
    semantic_plan_stub(operation='set_response_style',speech_act='request',style='简洁')
    m=ended();store=Memory(tmp_path/'db');store.save_match(m)
    result=control_reply('以后不要写那么多，先给我结论',m,{},'live')
    current,_=apply_command(store,m,result,'以后不要写那么多，先给我结论','style')
    assert current['battle']==m['battle'] and store.profile()['preference']=='简洁、先说重点'


def test_planner_payload_excludes_failed_and_generating_drafts():
    m=ended();m['messages'].extend([
        {'speaker':'user','kind':'chat','text':'问一句'},
        {'speaker':'assistant','kind':'chat_failed','status':'failed','text':'错误建议','previews':['不可靠草稿']},
        {'speaker':'user','kind':'chat','text':'当前问题'},
        {'speaker':'assistant','kind':'chat_pending','status':'generating','text':'正在生成'}])
    payload=semantic_snapshot(m,{})
    assert '不可靠草稿' not in str(payload) and '错误建议' not in str(payload)


def test_equivalent_typed_confirmation_is_normalized_without_phrase_matching(semantic_plan_stub):
    semantic_plan_stub(operation='start_new_match',speech_act='confirmation',reference='latest_assistant',scenario='practice',difficulty='challenge')
    m=ended();m['messages'].append({'speaker':'assistant','kind':'chat','text':'可以安排一场均衡进阶对练，现在开始吗？'})
    result=control_reply('照那个办就成',m,{},'live')
    assert result['command']['expected_offer_id']==latest_reference(m)['id']
    assert result['metadata']['planner']['raw_intent']['operation']=='start_new_match'
    assert result['metadata']['intent']['operation']=='confirm_pending'


def test_active_match_replacement_requires_independent_semantic_check(semantic_plan_stub,monkeypatch):
    from rococoach.semantic_control import ReplacementCheck
    semantic_plan_stub(operation='start_new_match',speech_act='request')
    monkeypatch.setattr('rococoach.semantic_control.verify_active_replacement',lambda q,s:(ReplacementCheck(replace_now=False,clarification='你是指重讲还是重开？'),{}))
    m=new_match();before=deepcopy(m)
    result=control_reply('再做一次',m,{},'live')
    assert result['command'] is None and result['reply']=='你是指重讲还是重开？'
    assert m==before


def test_live_clarification_cannot_bypass_guidance_policy(semantic_plan_stub):
    from rococoach.match_coach import match_chat
    from rococoach.llm import ModelUnavailable
    semantic_plan_stub(operation='clarify',speech_act='ambiguous',question='是否使用十万伏特？')
    with pytest.raises(ModelUnavailable,match='具体答案'):match_chat('再解释一下',new_match('electric'),{},'live')
