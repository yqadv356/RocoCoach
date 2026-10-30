import json
from types import SimpleNamespace as NS

import pytest

from rococoach.llm import ModelConfig,ModelUnavailable,structured_call,tool_step
from rococoach.companion import Reply
from rococoach.streaming import collect_chat,public_prefix


class Stream:
    def __init__(self,items):self.items=items;self.closed=False
    def __iter__(self):return iter(self.items)
    def close(self):self.closed=True


def chunk(content=None,tools=None,finish=None,usage=None):
    return NS(usage=usage,choices=[] if usage else [NS(delta=NS(content=content,tool_calls=tools),finish_reason=finish)])


def part(index,id=None,name=None,args=None):
    return NS(index=index,id=id,function=NS(name=name,arguments=args))


def test_json_projection_never_shows_schema_or_tool_arguments():
    assert public_prefix('{"reply":"你好\\n小',('reply',))=='你好\n小'
    assert public_prefix('{"reply":"你好\\u4',('reply',))=='你好'
    assert public_prefix('{"feedback":{"text":"先比较',('feedback','text'))=='先比较'
    assert public_prefix('{"arguments":"秘密","evidence_ids":["state"]}',('reply',))==''
    assert public_prefix('{"reply":["错误类型"]}',('reply',))==''


def test_stream_reassembles_multiple_fragmented_tools_and_usage():
    stream=Stream([chunk(tools=[part(1,'b','compare_','{"choices":['),part(0,'a','inspect_','{')]),
                   chunk(tools=[part(0,name='battle',args='}'),part(1,name='moves',args='"move 1"]}')]),
                   chunk(finish='tool_calls'),chunk(usage=NS(model_dump=lambda:{'total_tokens':8}))])
    out=collect_chat(stream)
    assert out['calls']==[{'id':'a','name':'inspect_battle','arguments':'{}'},
                         {'id':'b','name':'compare_moves','arguments':'{"choices":["move 1"]}'}]
    assert out['wire']['tool_calls'][1]['function']['name']=='compare_moves'
    assert out['usage']['total_tokens']==8 and stream.closed


@pytest.mark.parametrize('finish',[None,'length','content_filter'])
def test_truncated_stream_is_rejected_and_closed(finish):
    stream=Stream([chunk('{"reply":"草稿'),chunk(finish=finish)])
    with pytest.raises(ModelUnavailable):collect_chat(stream)
    assert stream.closed


def test_transport_error_closes_stream():
    class Broken(Stream):
        def __iter__(self):
            yield chunk('开头')
            raise RuntimeError('disconnected')
    stream=Broken([])
    with pytest.raises(RuntimeError):collect_chat(stream)
    assert stream.closed


def test_active_stream_still_obeys_elapsed_budget():
    stream=Stream([chunk('还有内容')])
    with pytest.raises(ModelUnavailable):collect_chat(stream,deadline=0)
    assert stream.closed


def test_structured_stream_emits_before_validation_but_bad_json_is_not_answer(monkeypatch):
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    events=[];captured={}
    class Client:
        def __init__(self,**kw):
            def create(**kw):
                captured.update(kw)
                return Stream([chunk('{"reply":"草稿'),chunk('内容"}'),chunk(finish='stop')])
            self.chat=NS(completions=NS(create=create))
        def close(self):captured['closed']=True
    monkeypatch.setattr('rococoach.llm.OpenAI',Client)
    with pytest.raises(ModelUnavailable):structured_call('json',{},Reply,on_event=events.append)
    assert [e['text'] for e in events if e['type']=='draft']==['草稿','草稿内容']
    assert captured['stream'] and captured['stream_options']['include_usage'] and captured['closed']


def test_tool_stream_does_not_publish_argument_deltas(monkeypatch):
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    class Client:
        def __init__(self,**kw):
            self.chat=NS(completions=NS(create=lambda **kw:Stream([
                chunk(tools=[part(0,'a','search_rules','{"query":"命中率"}')]),chunk(finish='tool_calls')])))
        def close(self):pass
    monkeypatch.setattr('rococoach.llm.OpenAI',Client)
    events=[]
    out=tool_step([],[],on_event=events.append)
    assert out['calls'][0]['name']=='search_rules'
    assert events==[{'type':'model_start'}]


def test_preview_is_retained_for_audit_when_revising_or_failing(monkeypatch):
    from rococoach.live_ui import LiveOutput
    class Box:
        def __init__(self):self.value=None
        def container(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def caption(self,value):self.value=value
        def markdown(self,value):self.value=value
        def empty(self):self.value=None
    boxes=[]
    def empty():
        box=Box();boxes.append(box);return box
    monkeypatch.setattr('rococoach.live_ui.st.empty',empty)
    view=LiveOutput(Box())
    view({'type':'draft','text':'未核实的内容'})
    assert boxes[1].value
    view({'type':'revision'})
    assert '未核实的内容' in boxes[1].value
    assert view.snapshot()['previews']==['未核实的内容']
    view.last_paint=0;view({'type':'draft','text':'尚未完整的内容'})
    view.reject()
    assert boxes[1].value is None
    assert view.snapshot()['previews']==['未核实的内容','尚未完整的内容']
    metrics=view.complete('核对后的内容')
    assert boxes[1].value=='核对后的内容' and boxes[0].value is None
    assert metrics['draft_updates']==2


@pytest.mark.parametrize('fails',[False,True])
def test_live_page_stream_persists_only_completed_reply(tmp_path,monkeypatch,fails):
    from streamlit.testing.v1 import AppTest
    from rococoach.battle import ROOT
    from rococoach.memory import Memory
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'stream.db')
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    def fake(*args,**kwargs):
        callback=kwargs['on_event']
        callback({'type':'model_start'});callback({'type':'draft','text':'未完成草稿'})
        if fails:raise ModelUnavailable('模拟连接中断')
        return {'reply':'核对后的完整回答','role':'陪聊','routing':{'role':'陪聊'},
                'metadata':{'mode':'live'},'evidence_ids':[],'suggested_choice':None}
    monkeypatch.setattr('rococoach.match_coach.match_chat',fake)
    monkeypatch.setattr('rococoach.match_coach.guide_reply',lambda *a,**k: {'reply':'观察生命和状态，再自己判断。','metadata':{'mode':'live'},'evidence_ids':[]})
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.chat_input[0].set_value('聊聊今天').run()
    assert not app.exception
    rows=Memory(tmp_path/'stream.db').chat_history()
    assert not rows if fails else rows[-1]['assistant']=='核对后的完整回答'
    if fails:
        assert any('未完成草稿' in item.value for item in app.markdown)
        failed=app.session_state['match']['messages'][-1]
        assert failed['status']=='failed' and failed['previews']==['未完成草稿']
        from rococoach.match import recent_dialogue
        assert '未完成草稿' not in str(recent_dialogue(app.session_state['match']))
        app.run()
        assert any('未完成草稿' in item.value for item in app.markdown)
    else:
        assert all('未完成草稿' not in item.value for item in app.markdown)


def test_late_validation_failure_retains_seen_versions_and_excludes_context(tmp_path,monkeypatch):
    import time
    from streamlit.testing.v1 import AppTest
    from rococoach.agent import AgentFailure
    from rococoach.battle import ROOT
    from rococoach.memory import Memory
    from rococoach.match import new_match,recent_dialogue
    path=tmp_path/'late-failure.db';Memory(path).save_match(new_match())
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test','http://localhost'))
    monkeypatch.setattr('rococoach.match_coach.guide_reply',lambda *a,**k:{'reply':'先看公开局面。','metadata':{'mode':'live'}})
    def failing(*args,**kwargs):
        emit=kwargs['on_event']
        emit({'type':'draft','text':'第一版已经展示的文字。'})
        checkpoint=Memory(path).latest_match()['messages'][-1]
        assert checkpoint['status']=='generating' and checkpoint['previews']==['第一版已经展示的文字。']
        emit({'type':'revision'})
        time.sleep(.06)
        emit({'type':'draft','text':'第二版已经展示的文字。'})
        raise AgentFailure('核对未完成',[{'validation_error':'教练混淆了当前场景的宠物'}])
    monkeypatch.setattr('rococoach.match_coach.match_chat',failing)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.chat_input[0].set_value('帮我继续练习').run()
    assert not app.exception
    stored=Memory(path).latest_match();last=stored['messages'][-1]
    assert last['status']=='failed' and len(last['previews'])==2
    assert len([m for m in stored['messages'] if m.get('request_id')==last['request_id']])==2
    assert stored['chat_failures'][-1]['query']=='帮我继续练习'
    assert stored['chat_failures'][-1]['request_id']==last['request_id']
    assert '第一版' not in str(recent_dialogue(stored))
    assert Memory(path).chat_history()==[]
    app.run()
    text=' '.join(m.value for m in app.markdown)
    assert '第一版已经展示' in text and '第二版已经展示' in text and '未通过核对' in text
    assert not any('这部分先放一放' in m.value for m in app.markdown)
