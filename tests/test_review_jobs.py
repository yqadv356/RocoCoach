from copy import deepcopy
from threading import Event

from streamlit.testing.v1 import AppTest

from rococoach.battle import ROOT
from rococoach.match import new_match,advance
from rococoach.match_coach import review_match
from rococoach.memory import Memory
from rococoach.review_jobs import review_job
from rococoach.zh import dialogue


def completed():
    m=new_match('electric',42)
    while not m['battle']['ended']:m=advance(m,'move 1',expected_round=len(m['frames']))
    return m


def test_presentation_never_erases_review_for_english_names_or_unknown_terms():
    for word in ['Alex','Mary-Jane','玩家A','CPU','未知词xyz']:
        original=f'{word}，这局结束了。对手剩余 HP 为0，回看第二回合。'
        rendered=dialogue(original)
        assert word in rendered and '回看第二回合' in rendered
        assert '生命值' in rendered and '未转换' not in rendered


def test_background_job_is_nonblocking_reused_and_does_not_mutate_game():
    m=completed();before=deepcopy(m);entered=Event();release=Event();calls=[]
    def generate(match,memory,mode,*,on_event):
        entered.set();calls.append(1);on_event({'type':'tool','name':'inspect_round'})
        assert release.wait(5)
        on_event({'type':'draft','text':'Alex，这局已结束。'})
        return review_match(match,memory,'mock')
    try:
        job=review_job(m,{},'live',generate)
        assert entered.wait(2) and not job.future.done()
        assert '回合记录' in job.snapshot()['status']
        assert review_job(m,{},'live',generate) is job
    finally:release.set()
    result=job.future.result(timeout=5)
    assert calls==[1] and m==before
    assert result['metadata']['stream']['draft_updates']==1
    assert 'Alex' in job.snapshot()['draft']


def test_live_finished_page_shows_result_before_review_and_keeps_final_after_rerun(tmp_path,monkeypatch):
    from rococoach.llm import ModelConfig
    m=completed();path=tmp_path/'async-review.db';Memory(path).save_match(m)
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    monkeypatch.setattr('rococoach.llm.configuration',lambda:ModelConfig('qwen','fake','test-only','http://localhost'))
    release=Event();entered=Event();jobs=[]
    def slow(match,memory,mode,*,on_event):
        entered.set();assert release.wait(10)
        on_event({'type':'draft','text':'Alex，本局复盘完成。'})
        result=review_match(match,memory,'mock')
        result['answer']['reply']='Alex，本局复盘完成。先检查命中风险，再回看实际结果。'
        return result
    monkeypatch.setattr('rococoach.match_coach.review_match',slow)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20)
    try:
        app.run()
        assert not app.exception and entered.wait(2)
        assert 'review' not in app.session_state['match']
        assert any(b.label=='再来一局' for b in app.button)
        assert any('赛果已保存' in c.value for c in app.caption)
        job=review_job(m,{},'live',slow);jobs.append(job)
    finally:release.set()
    jobs[0].future.result(timeout=5)
    app.run()
    assert not app.exception
    assert any('Alex，本局复盘完成' in x.value for x in app.markdown)
    assert app.session_state['match']['battle']==m['battle']
    app.run()
    assert sum(x.get('kind')=='match_review' for x in app.session_state['match']['messages'])==1
    assert len([r for r in Memory(path).recent(50) if r['kind']=='review'])==1
    assert not any('未转换' in x.value for x in app.markdown)


def test_review_prefetch_can_finish_with_one_model_call_and_real_receipts(monkeypatch):
    import json
    calls=[]
    def model(messages, tools, **kwargs):
        calls.append(messages)
        observations=[json.loads(m['content']) for m in messages[2:]]
        assert {x['宿主已执行的工具'] for x in observations} == {'inspect_match','find_key_turns','inspect_round'}
        evidence=[e for o in observations for e in o['结果']['evidence']]
        ids=[e['id'] for e in evidence]
        turn_id=next(i for i in ids if i.startswith('match:turn:'))
        return {'content':json.dumps({'reply':'本局已结束。先对照自己的选择理由，再回看命中与生命变化。',
            'evidence_ids':['match:summary',turn_id],'focus':'综合比较','next_practice':'出招前写下你最在意的风险。'},ensure_ascii=False),
            'calls':[],'provider':'test','model':'test','usage':{}}
    monkeypatch.setattr('rococoach.agent.tool_step',model)
    result=review_match(completed(),{},'live')
    agent=result['metadata']['agent']
    assert len(calls)==agent['model_calls']==1
    assert len(agent['trace'])>=3
    assert all(t['selected_by']=='host' and t['observation']['receipt']['match_unchanged'] for t in agent['trace'])
    assert len(result['evidence'])>=3


def test_tool_progress_does_not_erase_existing_stream_draft():
    from rococoach.review_jobs import ReviewJob
    job=ReviewJob()
    job.receive({'type':'draft','text':'先对照你的选择理由。'})
    job.receive({'type':'tool','name':'inspect_round'})
    assert job.snapshot()['draft']=='先对照你的选择理由。'
    assert '核对回合' in job.snapshot()['status']
    # A rejected draft must still be withdrawn; it is never a validated answer.
    job.receive({'type':'revision'})
    assert job.snapshot()['draft']==''


def test_failed_review_preserves_rejected_preview_in_job():
    from rococoach.review_jobs import review_job
    import pytest
    def fail(match,memory,mode,*,on_event):
        on_event({'type':'draft','text':'已生成的复盘草稿。'})
        on_event({'type':'revision'})
        raise RuntimeError('模拟末尾核对失败')
    job=review_job(completed(),{},'live',fail)
    with pytest.raises(RuntimeError):job.future.result(timeout=5)
    assert job.snapshot()['previews']==['已生成的复盘草稿。']
