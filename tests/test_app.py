from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "pages/2_训练计划.py"


def test_page_and_complete_flow(monkeypatch):
    monkeypatch.setenv("ROCOCOACH_MODE", "mock")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.title[0].value == "🧭 洛洛教练"
    app.button[0].click().run()
    assert app.warning
    app.selectbox[0].select("对战复盘")
    app.text_area[0].input("不知道如何复盘关键回合")
    app.button[0].click().run()
    assert not app.exception
    assert "对战复盘" in app.session_state["plan"]
    app.text_area[1].input("下一次记录每回合的选择").run()
    assert app.session_state["reflection"] == "下一次记录每回合的选择"
    app.button[0].click().run()
    assert app.session_state["reflection"] == ""
    assert not app.exception


def test_bad_configuration_is_visible(monkeypatch):
    monkeypatch.setenv("ROCOCOACH_MODE", "live")
    app = AppTest.from_file(str(APP)).run()
    assert app.error
    assert not app.exception
