import re

import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT, simulate
from rococoach.companion import Reply, respond
from rococoach.llm import ModelUnavailable
from rococoach.memory import Memory
from rococoach.zh import name, text, dialogue, move_rows, event_lines


@pytest.mark.parametrize("scenario",["electric","fire","water"])
def test_all_scenario_names_have_chinese_without_changing_engine(scenario):
    b=simulate(scenario)
    for mon in [b["player"],b["opponent"]]:
        for value in [mon["name"],mon["ability"],*mon["types"]]:
            assert name(value)!="未收录名称"
            assert not re.search('[A-Za-z]',name(value))
    for row in move_rows(b["advice"]):
        assert not re.search('[A-Za-z]',row["招式"]+row["属性"])
    assert b["advice"][0]["choice"].startswith("move ")


def test_text_maps_known_terms_and_does_not_guess_unknown():
    assert text("Pikachu uses Thunderbolt, HP 20") == "皮卡丘 uses 十万伏特, 生命值 20"
    assert dialogue("unexpected_unknown_word")=="unexpected_unknown_word"
    assert "十万伏特" in dialogue("Thunderbolt (move 1)")


def test_companion_memory_and_legal_evidence(tmp_path,monkeypatch):
    store=Memory(tmp_path/"memory.db")
    result=respond("怎么选？","军师",simulate(),store.summary())
    assert "十万伏特" in result["reply"]
    store.add("chat-one","chat",{"user":"我想稳一点","assistant":"记住了","role":"陪聊"})
    assert Memory(tmp_path/"memory.db").chat_history()[0]["user"]=="我想稳一点"
    def fake(*args):
        return Reply(reply="用未见过的招式。",evidence_ids=["imaginary"]),{"mode":"live"}
    monkeypatch.setattr("rococoach.companion.structured_call",fake)
    with pytest.raises(ModelUnavailable):respond("怎么选？","军师",simulate(),store.summary(),mode="live")


def test_single_surface_without_role_controls(tmp_path,monkeypatch):
    monkeypatch.setattr("rococoach.memory.DEFAULT_DB",tmp_path/"page.db")
    def missing():raise ModelUnavailable("test")
    monkeypatch.setattr("rococoach.llm.configuration",missing)
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=20).run()
    assert not app.exception
    assert not app.tabs
    assert not any(r.label=="现在想让我做什么" for r in app.radio)
    assert not any(b.label in {"给个建议","为什么这样选","有点挫败，聊聊"} for b in app.button)
    assert len(app.chat_input)==1
    app.chat_input[0].set_value("我有点挫败，先陪我聊聊").run()
    assert not app.exception
    record=Memory(tmp_path/"page.db").chat_history()[-1]
    assert record["role"]=="陪聊" and record["routing"]["source"]=="query"
    assert any(b.label=="出招" for b in app.button)


def test_reject_species_not_present_in_scene():
    from rococoach.zh import validate_species
    with pytest.raises(ModelUnavailable):
        validate_species('十万伏特能击败水箭龟','Pikachu Squirtle')
    validate_species('比较皮卡丘与杰尼龟','Pikachu Squirtle')
    assert 'vs' not in text('Pikachu vs Squirtle')
