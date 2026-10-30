"""Transient stream preview. Only the caller's validated result enters history."""
import time
import streamlit as st
from rococoach.zh import dialogue,text
from rococoach.answer_evidence import elapsed_label,branch_rows


class LiveOutput:
    def __init__(self,target,identifiers=(),*,activity=None):
        self.target=target
        self.activity=activity
        self.identifiers=identifiers;self.started=time.monotonic();self.first=None;self.updates=0;self.last_paint=0
        self.visible='';self.previews=[];self.revisions=0
        with target.container():
            self.status=st.empty();self.body=st.empty()
        self.status.caption('洛洛正在回应…')

    def __call__(self,event):
        kind=event['type']
        if self.activity:self.activity(event)
        if kind=='planning':self.status.caption('正在理解你的意思…')
        elif kind=='draft':
            now=time.monotonic()
            if self.first is None:self.first=round(now-self.started,3)
            self.updates+=1
            if now-self.last_paint<0.05:return
            self.last_paint=now
            self.status.caption('正在生成 · 尚未核验')
            self.visible=text(event['text'])[:12000]
            self.body.markdown(self.visible+' ▍')
        elif kind=='tool':
            labels={'inspect_battle':'正在查看局面…','compare_moves':'正在比较招式…',
                    'search_rules':'正在查找资料…','recall_learning':'正在查看学习记录…',
                    'inspect_review':'正在核对刚才的回合…','simulate_alternative':'正在试算另一种选择…',
                    'find_key_turns':'正在寻找值得回看的回合…','simulate_round_alternative':'正在独立重放另一种选择…',
                    'observe_public_state':'正在观察公开局面…','inspect_match':'正在回看整局经过…','inspect_round':'正在核对关键回合…',
                    'plan_practice':'正在准备下一次练习…'}
            self.status.caption(labels.get(event['name'],'正在核对…'))
        elif kind in {'model_start','revision'}:
            if kind=='revision':self.retain();self.revisions+=1
            self.status.caption('正在整理回答…' if kind=='model_start' else '刚才的草稿未通过核对，正在修正…')
        elif kind=='validating':self.status.caption('正在核对回答…')

    def complete(self,text):
        self.body.markdown(dialogue(text,self.identifiers));self.status.empty()
        return {'transport':'provider_stream','first_draft_seconds':self.first,'draft_updates':self.updates,
                'validated_seconds':round(time.monotonic()-self.started,3)}

    def reject(self):
        self.retain()
        self.body.empty();self.status.empty()

    def failed(self,reason):
        self.retain()
        self.status.caption(reason)
        if self.visible:self.body.markdown(self.visible)
        else:self.body.markdown('你的输入与对局记录已保留。')

    def retain(self):
        if self.visible and (not self.previews or self.previews[-1]!=self.visible):
            self.previews.append(self.visible);self.previews=self.previews[-8:]

    def snapshot(self):
        drafts=list(self.previews)
        if self.visible and (not drafts or drafts[-1]!=self.visible):drafts.append(self.visible)
        return {'previews':drafts[-8:],'status':'draft','revision_count':self.revisions}


def unfinished_previews(previews,*,expanded=True):
    if not previews:return
    with st.expander('查看生成草稿（未通过完整核对）',expanded=expanded):
        st.caption('保留生成过程供查看，不作为正式建议，也不会作为已确认的对话依据。')
        for i,draft in enumerate(previews[-8:],1):
            if len(previews)>1:st.caption(f'草稿 {i}')
            st.markdown(draft)


def tool_evidence(result):
    """Compact post-game receipts; no raw tool arguments or hidden reasoning in UI."""
    trace=result.get('metadata',{}).get('agent',{}).get('trace',[])
    calls=[t for t in trace if t.get('observation',{}).get('receipt')]
    if not calls:return
    labels={'inspect_match':'整局记录','inspect_round':'回合核对','find_key_turns':'关键回合定位',
            'simulate_round_alternative':'独立回合重放','search_rules':'规则检索','recall_learning':'学习记录',
            'observe_public_state':'公开局面观察'}
    with st.expander('这次回答核对了什么'):
        st.caption('只对应上面这一条回答。这里记录实际执行的查证；不会引用其他回复的记录。')
        total=result.get('metadata',{}).get('latency_seconds')
        if total is not None:st.caption(f'本条回答共用时约{total:.2f}秒（包括模型生成）。下列时间只计算本地工具执行，不是生命值或伤害。')
        for t in calls:
            r=t['observation']['receipt'];label=labels.get(t['tool'],'证据核对')
            st.caption(f"{label} · {elapsed_label(t['elapsed_seconds'])}"+(' · 复用本次已查结果' if t.get('cached') else '')+' · 不改动原局')
            for fact in t['observation'].get('evidence',[]):
                if fact['id']=='match:key_turns':
                    st.write('值得回看的回合：'+ '、'.join(str(c['回合']) for c in fact['data']['候选回合']))
                    st.caption(fact['data']['筛选规则'])
                if fact['id'].startswith('match:branch:'):
                    d=fact['data'];st.write(f"第{d['回合']}回合：{d['实际招式']} → {d['另一个招式']}")
                    st.caption('下面是该回合结束时的生命值，不是招式威力或胜率。')
                    st.table(branch_rows(d))
                    st.caption(d['边界'])
        st.caption('详细查证记录可在设置中导出。工具结果可核对，仍需留意讲解是否准确。')
