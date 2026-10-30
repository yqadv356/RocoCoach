import pytest
from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT, SCENARIOS, report, simulate


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("seed", [42, 71])
def test_real_engine_completes_and_replays(scenario, seed):
    result = simulate(scenario, seed, autoplay=True)
    assert result["ended"]
    assert result["winner"] in {"Student", "Trainer"}
    assert 1 <= len(result["rounds"]) < 60
    replayed = simulate(scenario, seed, result["history"])
    assert replayed["rounds"] == result["rounds"]
    assert replayed["log"] == result["log"]
    assert "|win|" in result["log"]
    assert "原始引擎日志" in report(result)


def test_damage_calculator_matches_noncritical_fixture():
    opening = simulate()
    bolt = next(m for m in opening["advice"] if m["name"] == "Thunderbolt")
    assert bolt["effectiveness"] == 2
    assert bolt["sameType"]
    advanced = simulate(history=[bolt["choice"]])
    loss = opening["opponent"]["hp"] - advanced["opponent"]["hp"]
    assert "|-crit|" not in advanced["log"]
    assert bolt["minDamage"] <= loss <= bolt["maxDamage"]
    assert simulate()["player"]["hp"] == opening["player"]["hp"]


@pytest.mark.parametrize("kwargs", [{"scenario":"unknown"}, {"seed":-1}, {"history":["win"]}])
def test_reject_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        simulate(**kwargs)


def test_ended_battle_rejects_more_actions():
    completed = simulate(autoplay=True)
    with pytest.raises(RuntimeError, match="ended"):
        simulate(history=completed["history"] + ["move 1"])


def test_battle_page_start_play_finish_undo():
    app = AppTest.from_file(str(ROOT / "pages/1_宠物对战.py"), default_timeout=20).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["battle"]["turn"] == 1
    next(b for b in app.button if b.label == "执行这一回合").click().run()
    assert not app.exception
    assert len(app.session_state["battle"]["rounds"]) == 1
    next(b for b in app.button if b.label == "观看军师自动打完").click().run()
    assert not app.exception
    assert app.session_state["battle"]["ended"]
    next(b for b in app.button if b.label == "撤销上一回合").click().run()
    assert not app.exception
    assert not app.session_state["battle"]["ended"]
