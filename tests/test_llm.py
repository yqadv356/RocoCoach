import json
from types import SimpleNamespace

import pytest

from rococoach.llm import ModelConfig, ModelUnavailable, configuration, structured_call
from rococoach.tutor import TutorAnswer


def test_configuration_hot_reload_and_no_key_leak(tmp_path,monkeypatch):
    monkeypatch.setattr("rococoach.llm.ROOT",tmp_path)
    for key in ["LLM_PROVIDER","LLM_API_KEY","DEEPSEEK_API_KEY","LLM_MODEL","LLM_BASE_URL"]:
        monkeypatch.delenv(key,raising=False)
    (tmp_path/".env").write_text("LLM_PROVIDER=deepseek\nLLM_API_KEY=\nLLM_MODEL=test-model\n")
    with pytest.raises(ModelUnavailable):
        configuration()
    (tmp_path/".env").write_text("LLM_PROVIDER=deepseek\nLLM_API_KEY=test-only-token\nLLM_MODEL=test-model\n")
    assert configuration().key=="test-only-token"
    assert configuration().base_url=="https://api.deepseek.com"


@pytest.mark.parametrize("content,finish",[("", "stop"),("{}","length"),("not json","stop")])
def test_bad_provider_output_fails_explicitly(monkeypatch,content,finish):
    monkeypatch.setattr("rococoach.llm.configuration",lambda:ModelConfig("deepseek","fake","not-real","http://localhost"))
    class FakeClient:
        def __init__(self,**kwargs):
            self.chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:SimpleNamespace(
                choices=[SimpleNamespace(finish_reason=finish,message=SimpleNamespace(content=content))],usage=None)))
        def close(self):
            pass
    monkeypatch.setattr("rococoach.llm.OpenAI",FakeClient)
    with pytest.raises(ModelUnavailable):
        structured_call("json",{},TutorAnswer)


def test_qwen_accepts_existing_openai_names(tmp_path,monkeypatch):
    monkeypatch.setattr("rococoach.llm.ROOT",tmp_path)
    for name in ["LLM_PROVIDER","LLM_API_KEY","LLM_MODEL","LLM_BASE_URL","DASHSCOPE_API_KEY","OPENAI_API_KEY","OPENAI_MODEL"]:
        monkeypatch.delenv(name,raising=False)
    (tmp_path/".env").write_text('LLM_PROVIDER=qwen\nOPENAI_API_KEY=test-only\nOPENAI_MODEL="qwen3.8-flash"\n')
    cfg=configuration()
    assert cfg.provider=="qwen"
    assert cfg.model=="qwen3.8-flash"
    assert cfg.key=="test-only"
    assert cfg.base_url=="https://dashscope.aliyuncs.com/compatible-mode/v1"
