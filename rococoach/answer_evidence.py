"""Bind execution receipts to the answer that produced them, never to the page."""
from copy import deepcopy


def evidence_report(result):
    meta=result.get('metadata',{})
    calls=[t for t in meta.get('agent',{}).get('trace',[]) if t.get('observation',{}).get('receipt')]
    return {'metadata':{'latency_seconds':meta.get('latency_seconds'),
                        'agent':{'trace':deepcopy(calls)}}}


def bind_legacy_reports(game):
    """Recover only exact known associations. Unknown historical replies stay unknown."""
    messages=game.get('messages',[])
    review=game.get('review',{})
    for item in messages:
        if item.get('kind')=='match_review' and item.get('text')==review.get('answer',{}).get('reply'):
            item.setdefault('tool_report',evidence_report(review))
    last=next((m for m in reversed(messages) if m.get('speaker')=='assistant' and m.get('kind')=='chat'),None)
    result=game.get('last_chat',{})
    if last is not None and last.get('text')==result.get('reply'):
        last.setdefault('tool_report',evidence_report(result))


def elapsed_label(seconds):
    if seconds < 0.01:return '本地处理不足10毫秒'
    if seconds < 1:return f'本地处理约{round(seconds*1000)}毫秒'
    return f'本地处理约{seconds:.2f}秒'


def branch_rows(data):
    return [{'路径':label,'你的剩余生命':data[key]['己方剩余生命'],
             '对手剩余生命':data[key]['对手剩余生命'],
             '你的状态':data[key]['己方状态'],'对手状态':data[key]['对手状态'],
             '该分支已结束':'是' if data[key]['已结束'] else '否',
             '胜者':data[key]['胜者'] or '尚未分出'}
            for label,key in [('实际发生','实际回合结束'),('假设换招','分支回合结束')]]
