"""Explicit model configuration and bounded calls; never silently falls back."""
from dataclasses import dataclass
import json
import os
import time

from dotenv import dotenv_values
from openai import OpenAI, APIError, APITimeoutError
from pydantic import BaseModel

from rococoach.config import ROOT


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class ModelConfig:
    provider: str
    model: str
    key: str
    base_url: str


def configuration():
    # Read each time so adding a key to .env works without restarting Streamlit.
    local = dotenv_values(ROOT / ".env")
    def setting(name, default=""):
        return os.getenv(name) or local.get(name) or default
    provider = setting("LLM_PROVIDER", "deepseek").strip().lower()
    if provider not in {"deepseek", "openai", "qwen", "compatible"}:
        raise ModelUnavailable("LLM_PROVIDER 请选择 deepseek、openai、qwen 或 compatible。")
    key = setting("LLM_API_KEY") or setting("DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY")
    if provider == "qwen":
        key = setting("LLM_API_KEY") or setting("DASHSCOPE_API_KEY") or setting("OPENAI_API_KEY")
    model = (setting("LLM_MODEL") or setting("OPENAI_MODEL")).strip()
    base = setting("LLM_BASE_URL").strip() or (
        "https://api.deepseek.com" if provider == "deepseek" else
        "https://dashscope.aliyuncs.com/compatible-mode/v1" if provider == "qwen" else "https://api.openai.com/v1")
    if not key or not model:
        raise ModelUnavailable("真实模型尚未配置：请在本地 .env 填写 LLM_API_KEY 和 LLM_MODEL；密钥不要发到聊天里。")
    if provider == "compatible" and not setting("LLM_BASE_URL"):
        raise ModelUnavailable("兼容服务还需要配置 LLM_BASE_URL。")
    return ModelConfig(provider, model, key, base)


def structured_call(system: str, payload: dict, schema: type[BaseModel], *, on_event=None):
    config = configuration()
    client = OpenAI(api_key=config.key, base_url=config.base_url, timeout=35, max_retries=0)
    messages = [{"role":"system", "content":system},
                {"role":"user", "content":json.dumps({**payload,"runtime_identity":{"provider":config.provider,"configured_model":config.model}}, ensure_ascii=False)}]
    start = time.monotonic()
    try:
        if on_event is not None:
            from rococoach.streaming import collect_chat,preview_callback
            on_event({'type':'model_start'})
            receive=preview_callback(on_event,('feedback','text') if schema.__name__=='TutorAnswer' else ('reply',))
        if config.provider == "openai" and on_event is not None:
            raw=''
            with client.responses.stream(model=config.model,input=messages,text_format=schema,max_output_tokens=1800,store=False) as stream:
                for event in stream:
                    if time.monotonic()-start>=35:raise ModelUnavailable('回答流超过时间预算，本次未保存。')
                    if event.type=='response.output_text.delta':
                        raw+=event.delta;receive(raw)
                result=stream.get_final_response()
            if result.status!='completed':raise ModelUnavailable('回答流未完整结束，本次未保存。')
            parsed=result.output_parsed
            usage=result.usage.model_dump() if result.usage else {}
        elif config.provider == "openai":
            result = client.responses.parse(model=config.model, input=messages,
                                             text_format=schema, max_output_tokens=1800, store=False)
            parsed = result.output_parsed
            usage = result.usage.model_dump() if result.usage else {}
        else:
            kwargs = {"extra_body":{"enable_thinking":False}} if config.provider == "qwen" else {}
            if on_event is not None:
                stream=client.chat.completions.create(model=config.model,messages=messages,max_tokens=1800,
                    response_format={'type':'json_object'},stream=True,stream_options={'include_usage':True},**kwargs)
                collected=collect_chat(stream,receive,deadline=start+35)
                if collected['calls']:raise ModelUnavailable('普通回应返回了意外工具请求。')
                parsed=schema.model_validate_json(collected['content']);usage=collected['usage']
            else:
                result = client.chat.completions.create(
                model=config.model, messages=messages, max_tokens=1800,
                response_format={"type":"json_object"}, **kwargs)
                if result.choices[0].finish_reason != "stop":
                    raise ModelUnavailable("模型输出未完整结束，请重试或检查输出长度设置。")
                content = result.choices[0].message.content
                if not content:raise ModelUnavailable("模型返回空内容，请重试。")
                parsed = schema.model_validate_json(content)
                usage = result.usage.model_dump() if result.usage else {}
    except APITimeoutError as exc:
        raise ModelUnavailable("模型响应超时；本地对局和输入已保留，可重试。") from exc
    except APIError as exc:
        # Do not expose request headers, URLs, response body or credentials.
        status = getattr(exc, "status_code", None)
        raise ModelUnavailable(f"模型调用失败（状态 {status or '网络错误'}），请检查本地配置与账户。") from exc
    except (ValueError, IndexError) as exc:
        raise ModelUnavailable("模型输出不符合约定格式，本次未保存为有效复盘。") from exc
    finally:
        client.close()
    if parsed is None:
        raise ModelUnavailable("模型未给出可用的结构化回答。")
    return parsed, {"mode":"live", "provider":config.provider, "model":config.model,
                    "latency_seconds":round(time.monotonic()-start, 3), "usage":usage}


def tool_step(messages, tools, *, remaining_seconds=25, force_final=False, on_event=None, preview_path=('reply',)):
    """Native function calling. Host executes tools; model never runs arbitrary code."""
    config=configuration()
    deadline=time.monotonic()+max(0.1,min(25,remaining_seconds))
    client=OpenAI(api_key=config.key,base_url=config.base_url,
                  timeout=max(0.1,min(25,remaining_seconds)),max_retries=0)
    try:
        kwargs={"extra_body":{"enable_thinking":False}} if config.provider=="qwen" else {}
        if force_final:kwargs['response_format']={'type':'json_object'}
        if on_event is not None:
            from rococoach.streaming import collect_chat,preview_callback
            on_event({'type':'model_start'})
            stream=client.chat.completions.create(model=config.model,messages=messages,tools=tools,
                tool_choice='none' if force_final else 'auto',max_tokens=1800,
                stream=True,stream_options={'include_usage':True},**kwargs)
            return {**collect_chat(stream,preview_callback(on_event,preview_path),deadline=deadline),
                    'provider':config.provider,'model':config.model}
        result=client.chat.completions.create(model=config.model,messages=messages,
            tools=tools,tool_choice="none" if force_final else "auto",max_tokens=1800,**kwargs)
        if not result.choices or result.choices[0].finish_reason not in {"stop","tool_calls"}:
            raise ModelUnavailable("教练工具请求未完整返回，请重试。")
        message=result.choices[0].message
        calls=[{"id":c.id,"name":c.function.name,"arguments":c.function.arguments}
               for c in (message.tool_calls or [])]
        return {"content":message.content or "","calls":calls,
                "wire":message.model_dump(include={"role","content","tool_calls"},exclude_none=True),
                "usage":result.usage.model_dump() if result.usage else {},
                "provider":config.provider,"model":config.model}
    except APITimeoutError as exc:
        raise ModelUnavailable("教练查证超时；当前对局未改变，可以重试。") from exc
    except APIError as exc:
        raise ModelUnavailable(f"教练工具调用失败（状态 {getattr(exc,'status_code',None) or '网络错误'}）。") from exc
    finally:
        client.close()
