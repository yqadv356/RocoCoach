"""Bounded background review jobs. Workers never touch Streamlit or player state."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass,field
from threading import Lock
import time

_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='roco-review')
_JOBS={}
_REGISTRY_LOCK=Lock()


@dataclass
class ReviewJob:
    started:float=field(default_factory=time.monotonic)
    lock:Lock=field(default_factory=Lock)
    future:object=None
    draft:str=''
    status:str='正在读取整局记录…'
    first_draft:float|None=None
    updates:int=0
    event_type:str='tool'
    previews:list=field(default_factory=list)

    def receive(self,event):
        with self.lock:
            kind=event['type']
            if kind in {'draft','tool','revision','validating','model_start'}:self.event_type=kind
            if kind=='draft':
                self.draft=event['text'];self.updates+=1
                if self.first_draft is None:self.first_draft=round(time.monotonic()-self.started,3)
                self.status='复盘草稿 · 正在生成'
            elif kind=='tool':
                self.status={'inspect_match':'正在回看整局…','find_key_turns':'正在定位关键回合…',
                    'inspect_round':'正在核对回合记录…','search_rules':'正在核对规则…',
                    'simulate_round_alternative':'正在独立重放候选行动…'}.get(event['name'],'正在查证…')
            elif kind=='revision':
                if self.draft:self.previews=(self.previews+[self.draft[:12000]])[-4:]
                self.draft='';self.status='刚才的复盘草稿未通过核对，正在重新整理…'
            elif kind=='validating':self.status='正在核对复盘依据…'
            elif kind=='model_start':self.status='正在整理整局复盘…'

    def snapshot(self):
        with self.lock:
            previews=list(self.previews)
            if self.draft and (not previews or previews[-1]!=self.draft):previews.append(self.draft[:12000])
            return {'draft':self.draft,'event_type':self.event_type,'previews':previews[-4:],'status':self.status,'seconds':round(time.monotonic()-self.started,1)}


def review_job(match,memory,mode,review_fn,*,retry=False):
    key=(match['id'],mode)
    with _REGISTRY_LOCK:
        old=_JOBS.get(key)
        if old is not None and (not retry or not old.future.done()):return old
        # Retain active jobs across page reconnects, bound completed-job memory.
        completed=[k for k,j in _JOBS.items() if j.future.done()]
        for k in completed[:-15]:_JOBS.pop(k)
        job=ReviewJob();frozen=deepcopy(match);memory=deepcopy(memory)
        def run():
            result=review_fn(frozen,memory,mode,on_event=job.receive)
            if job.previews:result.setdefault('metadata',{})['rejected_previews']=list(job.previews)
            result.setdefault('metadata',{})['stream']={'transport':'background_provider_stream',
                'first_draft_seconds':job.first_draft,'draft_updates':job.updates,
                'validated_seconds':round(time.monotonic()-job.started,3)}
            return result
        job.future=_POOL.submit(run);_JOBS[key]=job
        return job
