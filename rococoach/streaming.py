"""Project incomplete JSON onto one public string, never raw tool arguments."""
from pydantic_core import from_json
import time


def public_prefix(raw, path):
    try:
        value=from_json(raw,allow_partial='trailing-strings')
        for key in path:value=value[key]
        return value[:600] if isinstance(value,str) else ''
    except (ValueError,KeyError,TypeError):
        return ''


def collect_chat(stream, on_content=None, *, deadline=None):
    """Assemble content and indexed tool deltas before any tool may execute."""
    content='';calls={};usage={};finish=None
    try:
        for chunk in stream:
            if deadline is not None and time.monotonic()>=deadline:
                from rococoach.llm import ModelUnavailable
                raise ModelUnavailable('回答流超过时间预算；草稿未保存，可以重试。')
            if chunk.usage:usage=chunk.usage.model_dump()
            if not chunk.choices:continue
            choice=chunk.choices[0];delta=choice.delta
            if delta.content:
                content+=delta.content
                if on_content:on_content(content)
            for part in delta.tool_calls or []:
                call=calls.setdefault(part.index,{'id':'','name':'','arguments':''})
                if part.id:call['id']+=part.id
                if part.function:
                    if part.function.name:call['name']+=part.function.name
                    if part.function.arguments:call['arguments']+=part.function.arguments
            if choice.finish_reason:finish=choice.finish_reason
    finally:
        stream.close()
    from rococoach.llm import ModelUnavailable
    if finish not in {'stop','tool_calls'}:
        raise ModelUnavailable('回答流未完整结束；草稿未保存，可以重试。')
    ordered=[calls[i] for i in sorted(calls)]
    if ordered and finish!='tool_calls':raise ModelUnavailable('工具流未完整结束，未执行请求。')
    if finish=='tool_calls' and not ordered:raise ModelUnavailable('工具流缺少完整请求。')
    wire={'role':'assistant','content':content or None}
    if ordered:
        wire['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in ordered]
    return {'content':content,'calls':ordered,'wire':wire,'usage':usage}


def preview_callback(on_event, path):
    previous=''
    def receive(raw):
        nonlocal previous
        value=public_prefix(raw,path)
        if value and value!=previous:
            previous=value
            on_event({'type':'draft','text':value})
    return receive
