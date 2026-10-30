import pytest

from rococoach.coach import GOALS, build_plan
from rococoach.config import get_mode


@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("minutes", [10, 30, 120])
def test_plan_uses_goal_and_time_budget(goal, minutes):
    plan = build_plan(goal, minutes, "  不知道如何改进  ")
    assert plan.obstacle == "不知道如何改进"
    assert sum(int(step.split(" ")[1]) for step in plan.steps) == minutes
    assert goal in plan.markdown()
    assert "规则演示" in plan.markdown()


@pytest.mark.parametrize("goal,minutes,obstacle", [
    ("未知", 30, "问题"), (GOALS[0], 9, "问题"), (GOALS[0], 121, "问题"),
    (GOALS[0], True, "问题"), (GOALS[0], 30, "  "), (GOALS[0], 30, "字" * 1001),
])
def test_invalid_request(goal, minutes, obstacle):
    with pytest.raises(ValueError):
        build_plan(goal, minutes, obstacle)


def test_unsupported_mode_is_not_silently_mocked(monkeypatch):
    monkeypatch.setenv("ROCOCOACH_MODE", "live")
    with pytest.raises(ValueError, match="仅支持 mock"):
        get_mode()
