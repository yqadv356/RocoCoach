from rococoach.companion import Reply, respond
from rococoach.routing import route_query
from rococoach.zh import dialogue


def test_identity_does_not_need_game_tools():
    assert route_query("你好，你现在是什么大模型").role=="陪聊"
    assert route_query("为什么电光一闪能先出手").role=="老师"


def test_companion_preserves_cross_role_context_without_battle_payload(monkeypatch):
    history=[{"user":"为什么这样选", "assistant":"先比较命中率。", "role":"老师"}]
    def fake(system,payload,schema):
        assert payload["history"]==history
        assert payload["facts"]==[] and payload["legal_choices"]==[]
        assert "conversation_state" not in payload
        return Reply(reply="这句解释确实太绕了，我换个说法。",evidence_ids=[]),{"mode":"live"}
    monkeypatch.setattr("rococoach.companion.structured_call",fake)
    respond("你说得太死板了","陪聊",None,{"profile":{"mood":"有点挫败"}},history,mode="live")


def test_display_preserves_identifiers_without_erasing_answer():
    answer="当前配置调用的是 qwen3.8-flash。"
    assert dialogue(answer,["qwen3.8-flash"])==answer
    assert dialogue(answer)==answer
    assert dialogue("unexpected_word",["qwen3.8-flash"])=="unexpected_word"


def test_missing_battle_uses_reply_path_instead_of_stateful_tools(monkeypatch):
    def fake(system,payload,schema):
        assert payload["facts"]==[] and payload["legal_choices"]==[]
        return Reply(reply="先开始练习，才能核对当前局面。",evidence_ids=[]),{"mode":"live"}
    def unexpected_agent(*args,**kwargs):
        raise AssertionError("没有局面时不能启动依赖局面的工具环境")
    monkeypatch.setattr("rococoach.companion.structured_call",fake)
    monkeypatch.setattr("rococoach.agent.run_agent",unexpected_agent)
    result=respond("帮我分析一下","老师",None,{},mode="live",agentic=True)
    assert result["suggested_choice"] is None
