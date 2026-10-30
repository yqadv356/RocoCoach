from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT, simulate
from rococoach.llm import ModelUnavailable
from rococoach.memory import Memory
from rococoach.tutor import make_context, mock_answer, next_quiz, review, validate_answer


@pytest.fixture
def context(tmp_path):
    before = simulate()
    after = simulate(history=["move 2"])
    return make_context(before, after, "move 2", "我只看了威力", Memory(tmp_path/"test.db").summary())


def test_teacher_feedback_and_transfer_quiz(context):
    result = review(context)
    assert result["metadata"]["mode"] == "mock"
    assert result["answer"]["suggested_choice"] == "move 1"
    assert "规则演示" in result["answer"]["uncertainty"]
    quiz = next_quiz("electric",42)
    assert quiz["scenario"] != "electric"
    assert quiz["correct_choice"] in {m["choice"] for m in quiz["options"]}


@pytest.mark.parametrize("change", ["illegal_move", "invented_citation"])
def test_reject_hallucinated_action_or_citation(context, change):
    answer = mock_answer(context)
    if change == "illegal_move":
        answer.suggested_choice = "switch 6"
    else:
        answer.explanation.evidence_ids = ["source:nonexistent"]
    with pytest.raises(ModelUnavailable):
        validate_answer(answer, context)


def test_live_adapter_called_without_silent_fallback(context, monkeypatch):
    def fake_call(system, payload, schema):
        assert payload["selected_choice"] == "move 2"
        return mock_answer(payload), {"mode":"live","model":"test-double","usage":{},"latency_seconds":0.1}
    monkeypatch.setattr("rococoach.tutor.structured_call", fake_call)
    result = review(context, "live",agentic=False)
    assert result["metadata"]["mode"] == "live"
    def failing(*args):
        raise ModelUnavailable("timeout")
    monkeypatch.setattr("rococoach.tutor.structured_call", failing)
    with pytest.raises(ModelUnavailable, match="timeout"):
        review(context, "live",agentic=False)


def test_memory_survives_reopen_and_is_idempotent(tmp_path):
    path = tmp_path/"memory.db"
    store = Memory(path)
    store.save_profile("小雨", "先给提示", "有点挫败")
    store.add("one", "quiz", {"topic":"属性与命中","correct":True})
    store.add("one", "quiz", {"topic":"重复","correct":False})
    restored = Memory(path)
    assert restored.profile()["nickname"] == "小雨"
    assert len(restored.recent()) == 1
    assert restored.summary()["recent"][0]["correct"] is True


def test_bad_history_cannot_be_evidence(tmp_path):
    before=simulate()
    after=simulate(history=["move 1"])
    with pytest.raises(ValueError, match="不一致"):
        make_context(before, after, "move 2", "因为威力", Memory(tmp_path/"x.db").summary())


def test_llm_teacher_page_complete_loop(tmp_path, monkeypatch):
    monkeypatch.setattr("rococoach.memory.DEFAULT_DB",tmp_path/"ui.db")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    def unavailable():
        raise ModelUnavailable("test: no real calls")
    monkeypatch.setattr("rococoach.llm.configuration", unavailable)
    app=AppTest.from_file(str(ROOT/"pages/3_单回合练习.py"),default_timeout=20).run()
    assert not app.exception
    next(t for t in app.text_input if t.label=="你的想法").input("我觉得威力高更好，但不确定命中率")
    next(b for b in app.button if b.label=="出招").click().run()
    assert not app.exception
    assert app.session_state["lesson"]["result"]["metadata"]["mode"]=="mock"
    quiz=app.session_state["lesson"]["quiz"]
    next(s for s in app.selectbox if s.label=="你会选哪招").select(quiz["correct_choice"])
    next(b for b in app.button if b.label=="确认判断").click().run()
    assert not app.exception
    assert app.session_state["lesson"]["quiz_result"]["correct"]
    assert len(Memory(tmp_path/"ui.db").recent())==2


def test_failed_review_retries_without_replaying_action(tmp_path,monkeypatch):
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'retry.db')
    def missing():raise ModelUnavailable('no real calls')
    monkeypatch.setattr('rococoach.llm.configuration',missing)
    calls=[]
    def flaky(context,mode):
        calls.append(deepcopy(context))
        if len(calls)==1:raise ModelUnavailable('演示超时')
        return review(context,'mock')
    monkeypatch.setattr('rococoach.tutor.review',flaky)
    app=AppTest.from_file(str(ROOT/'pages/3_单回合练习.py'),default_timeout=20).run()
    next(b for b in app.button if b.label=='出招').click().run()
    assert not app.exception
    state=app.session_state['lesson']
    first=deepcopy(state['after'])
    assert 'result' not in state and first['history']==['move 1']
    next(b for b in app.button if b.label=='重试复盘').click().run()
    assert not app.exception
    assert app.session_state['lesson']['after']==first
    assert calls[0]==calls[1]
    assert len([e for e in Memory(tmp_path/'retry.db').recent() if e['kind']=='review'])==1


def test_quiz_help_is_recorded_as_assisted(tmp_path,monkeypatch):
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',tmp_path/'assisted.db')
    def missing():raise ModelUnavailable('no real calls')
    monkeypatch.setattr('rococoach.llm.configuration',missing)
    app=AppTest.from_file(str(ROOT/'pages/3_单回合练习.py'),default_timeout=20).run()
    next(b for b in app.button if b.label=='出招').click().run()
    app.chat_input[0].set_value('这个新场景怎么选？').run()
    assert not app.exception
    assert app.session_state['lesson']['last_routing']['context_source']=='transfer_quiz'
    next(b for b in app.button if b.label=='确认判断').click().run()
    event=next(e for e in Memory(tmp_path/'assisted.db').recent() if e['kind']=='quiz')
    assert event['value']['assisted'] is True
