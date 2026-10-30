import pytest


@pytest.fixture
def semantic_plan_stub(monkeypatch):
    """Explicit planner boundary stub; no implicit network calls in unit tests."""
    from rococoach.semantic_control import IntentPlan
    def choose(**fields):
        plan=IntentPlan(**fields)
        def parse(system,payload,schema):
            assert schema is IntentPlan
            return plan,{'mode':'live','model':'planner-test','usage':{}}
        monkeypatch.setattr('rococoach.semantic_control.structured_call',parse)
        return plan
    return choose
