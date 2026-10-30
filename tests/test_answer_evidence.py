from copy import deepcopy

from rococoach.answer_evidence import bind_legacy_reports,evidence_report,elapsed_label,branch_rows


def test_legacy_receipts_cannot_migrate_to_other_answers():
    result={'reply':'独立重放已完成','metadata':{'agent':{'trace':[{'tool':'simulate_round_alternative','observation':{'receipt':{'tool':'simulate_round_alternative'}}}]}}}
    game={'last_chat':result,'review':{'answer':{'reply':'教师复盘'},'metadata':{'agent':{'trace':[]}}},'messages':[
        {'speaker':'assistant','kind':'chat','text':'我没有接口'},
        {'speaker':'assistant','kind':'match_review','text':'教师复盘'},
        {'speaker':'assistant','kind':'chat','text':'独立重放已完成'}]}
    bind_legacy_reports(game)
    assert 'tool_report' not in game['messages'][0]
    assert game['messages'][1]['tool_report']['metadata']['agent']['trace']==[]
    assert game['messages'][2]['tool_report']['metadata']['agent']['trace'][0]['tool']=='simulate_round_alternative'
    game['messages'].append({'speaker':'assistant','kind':'chat','text':'另一条无关回复'})
    bind_legacy_reports(game)
    assert 'tool_report' not in game['messages'][-1]
    game['last_chat']={'reply':'另一条无关回复','metadata':{}}
    bind_legacy_reports(game)
    assert game['messages'][-1]['tool_report']['metadata']['agent']['trace']==[]
    assert game['messages'][2]['tool_report']['metadata']['agent']['trace']


def test_receipts_are_snapshot_and_do_not_show_failed_or_unreceipted_tools():
    trace=[{'tool':'a','observation':{'receipt':{'version':1}}},
           {'tool':'b','observation':{'error':'failed'}},{'validation_error':'bad answer'}]
    result={'metadata':{'latency_seconds':12.2,'agent':{'trace':trace}}}
    report=evidence_report(result);trace[0]['observation']['receipt']['version']=2
    assert len(report['metadata']['agent']['trace'])==1
    assert report['metadata']['agent']['trace'][0]['observation']['receipt']['version']==1
    assert report['metadata']['latency_seconds']==12.2


def test_display_separates_timing_health_and_completion_without_raw_booleans():
    assert elapsed_label(0)=='本地处理不足10毫秒'
    assert elapsed_label(0.004)=='本地处理不足10毫秒'
    assert elapsed_label(0.27)=='本地处理约270毫秒'
    assert elapsed_label(2.5)=='本地处理约2.50秒'
    actual={'己方剩余生命':93,'对手剩余生命':99,'己方状态':'正常','对手状态':'正常','已结束':False,'胜者':None}
    data={'实际回合结束':actual,'分支回合结束':{**actual,'对手剩余生命':95}}
    before=deepcopy(data);rows=branch_rows(data)
    assert rows[0]['该分支已结束']=='否' and rows[0]['胜者']=='尚未分出'
    assert rows[1]['对手剩余生命']==95 and rows[1]['你的剩余生命']==93
    assert data==before
