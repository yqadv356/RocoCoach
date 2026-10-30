"""Typed capabilities and atomic commit. Live language interpretation is semantic."""
from copy import deepcopy
import json
import time
from secrets import randbelow
from typing import Literal
from rococoach.agent import Args
from rococoach.battle import SCENARIOS
from rococoach.match import new_match
from rococoach.match_tools import digest


class NewGame(Args):
    scenario: Literal['same','practice','electric','fire','water'] = 'same'
    difficulty: Literal['same','standard','challenge'] = 'same'


class ResponseStyle(Args):
    style: Literal['简洁','详细','引导式']


class ControlConflict(ValueError):pass


def token(match):
    b=match['battle']
    return digest({'id':match['id'],'scenario':b['scenario'],'seed':b['seed'],
                   'history':b['history'],'ruleset':b.get('ruleset','standard-v1'),'difficulty':b.get('difficulty','standard')})


def control_reply(query,match,memory,mode='mock'):
    if mode=='live':
        from rococoach.semantic_control import semantic_control_reply
        return semantic_control_reply(query,match,memory)
    from rococoach.offline_control import offline_control_reply
    return offline_control_reply(query,match,memory,mode)


def apply_command(store,match,result,query,request_id):
    """Atomic session/profile update + replayable receipt, guarded against stale UI."""
    command=result.get('command')
    if not command:return match,result
    if command.get('query_hash')!=digest(query):raise ValueError('操作请求与当前输入不一致。')
    if command['source_token']!=token(match):raise ControlConflict('对局已变化，请看当前局面后重新提出操作。')
    tool=command['tool']
    if tool=='start_new_match':
        args=NewGame.model_validate(command['arguments'])
        scenario=match['battle']['scenario'] if args.scenario=='same' else args.scenario
        difficulty=match['battle'].get('difficulty','standard') if args.difficulty=='same' else args.difficulty
        updated=new_match(scenario,randbelow(65536),ruleset='short-pp-v1',difficulty=difficulty)
        if (updated['id']==match['id'] or updated['battle']['history'] or updated['frames'] or updated['battle']['ended']
            or updated['battle']['scenario']!=scenario or updated['battle'].get('difficulty')!=difficulty
            or updated['battle'].get('ruleset')!='short-pp-v1'):
            raise RuntimeError('开局结果未满足操作计划，旧对局保留，未宣布成功。')
        updated['previous_match_id']=match['id']
        reply='新一局已经开始，还是一起慢慢打。' if args.scenario=='same' else '新一局已经开始：'+SCENARIOS[scenario]+'。'
        if difficulty=='challenge':reply+=' 进阶对手会根据公开局面优先评估命中和直接伤害，再选择招式；你仍然自己出招。'
    elif tool=='set_response_style':
        args=ResponseStyle.model_validate(command['arguments']);updated=deepcopy(match)
        reply={'简洁':'好，之后我讲短一点，先说重点。','详细':'好，之后会把依据和取舍讲清楚。','引导式':'好，之后我会多给思考方向，留给你自己判断。'}[args.style]
    else:raise ValueError('不支持的操作。')
    receipt={'request_id':request_id,'tool':tool,'status':'executed','source_match_id':match['id'],
             'target_match_id':updated['id'],'arguments':command['arguments'],
             'source_token':command['source_token'],'target_token':token(updated),
             'ruleset':updated['battle'].get('ruleset','standard-v1')}
    executed={**result,'reply':reply,'command':None,'execution':receipt}
    messages=[{'speaker':'user','text':query,'kind':'chat'},
              {'speaker':'assistant','text':reply,'kind':'control','role':'陪聊','execution':receipt}]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT value FROM control_requests WHERE id=?',(request_id,)).fetchone()
        if old:
            saved=json.loads(old[0])
            latest_id=db.execute('SELECT id FROM match_sessions ORDER BY rowid DESC LIMIT 1').fetchone()[0]
            if latest_id!=saved['execution']['target_match_id']:raise ControlConflict('这次操作已经完成，目前已是另一局。')
            target=db.execute('SELECT value FROM match_sessions WHERE id=?',(saved['execution']['target_match_id'],)).fetchone()
            return json.loads(target[0]),saved
        latest=db.execute('SELECT id,value FROM match_sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        if not latest or latest[0]!=match['id'] or token(json.loads(latest[1]))!=command['source_token']:
            raise ControlConflict('当前对局已经变化，操作未执行。')
        # Merge against stored data, retaining reviews/chats completed while planning.
        source=json.loads(latest[1])
        if command.get('expected_offer_id'):
            from rococoach.semantic_control import latest_reference
            reference=latest_reference(source)
            if not reference or reference['id']!=command['expected_offer_id']:
                raise ControlConflict('刚才的开局提议已经变化，操作未执行。')
        if command.get('proposal_id'):
            pending=source.get('pending_action')
            if pending:
                from rococoach.semantic_control import latest_reference
                reference=latest_reference(source)
                if reference and reference.get('proposal_id')!=pending['id']:pending=None
            elif command.get('confirmation_origin')=='legacy_offer':
                from rococoach.offline_control import pending_action
                pending=pending_action(source)
            if not pending or pending['id']!=command['proposal_id'] or pending['expires_at']<time.time():
                raise ControlConflict('待确认方案已经变化或过期，操作未执行。')
        source.pop('pending_action',None)
        source['messages']=[m for m in source['messages'] if m.get('request_id')!=request_id]
        source['messages'].extend(messages)
        if tool=='start_new_match':
            updated['messages'].extend(deepcopy(messages))
            db.execute('UPDATE match_sessions SET value=? WHERE id=?',(json.dumps(source,ensure_ascii=False),source['id']))
            db.execute('INSERT INTO match_sessions(id,value) VALUES (?,?)',(updated['id'],json.dumps(updated,ensure_ascii=False)))
        else:
            updated=source
            row=db.execute('SELECT value FROM profile WHERE id=1').fetchone()
            profile=json.loads(row[0]) if row else {'nickname':'小训练家','preference':'简洁','mood':'平静'}
            profile['preference']={'简洁':'简洁、先说重点','详细':'详细解释依据与取舍','引导式':'多给思考方向，不直接给答案'}[args.style]
            db.execute('INSERT OR REPLACE INTO profile(id,value) VALUES(1,?)',(json.dumps(profile,ensure_ascii=False),))
            db.execute('UPDATE match_sessions SET value=? WHERE id=?',(json.dumps(updated,ensure_ascii=False),updated['id']))
        db.execute('INSERT INTO control_requests(id,value) VALUES(?,?)',(request_id,json.dumps(executed,ensure_ascii=False)))
    return updated,executed
