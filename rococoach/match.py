"""A whole match ledger; player actions advance the engine, never the model."""
from copy import deepcopy
import uuid

from rococoach.battle import simulate
from rococoach.zh import name,event_lines


def snapshot(battle):
    result={k:deepcopy(battle[k]) for k in ['scenario','seed','history','turn','ended','winner','player','opponent','advice','capped']}
    result['ruleset']=battle.get('ruleset','standard-v1')
    result['difficulty']=battle.get('difficulty','standard')
    return result


def new_match(scenario='practice',seed=42,*,ruleset='standard-v1',difficulty='standard'):
    return {'version':'full-match-v1','id':uuid.uuid4().hex,'battle':simulate(scenario,seed,ruleset=ruleset,difficulty=difficulty),
            'frames':[],'guides':{},'messages':[]}


def advance(match,choice,reason='',*,expected_round):
    b=match['battle']
    if expected_round!=len(b['history']):raise ValueError('回合已变化，请查看当前局面后再出招。')
    if b['ended'] or b['capped']:raise ValueError('本局已结束或达到上限，不能继续出招。')
    if choice not in {m['choice'] for m in b['advice'] if not m['disabled']}:
        raise ValueError('当前招式不可用。')
    if not isinstance(reason,str) or len(reason)>1000:raise ValueError('理由请控制在1000字以内。')
    after=simulate(b['scenario'],b['seed'],b['history']+[choice],ruleset=b.get('ruleset','standard-v1'),difficulty=b.get('difficulty','standard'))
    result=deepcopy(match)
    result['frames'].append({'turn':b['turn'],'before':snapshot(b),'after':snapshot(after),
        'choice':choice,'reason':reason.strip(),'actual':deepcopy(after['rounds'][-1]),
        'guide':deepcopy(match['guides'].get(str(len(b['history']))))})
    result['battle']=after
    move=next(m for m in b['advice'] if m['choice']==choice)
    result['messages'].extend([
        {'speaker':'user','kind':'decision','role':'老师','text':f"第{b['turn']}回合，我选{name(move['name'])}。"+reason.strip()},
        {'speaker':'assistant','kind':'turn_result','role':'老师','text':'\n'.join(event_lines(after['rounds'][-1]['events']))}])
    return result


def neutral_facts(match):
    """Public current state only; no rankings, damage forecasts or future opponent move."""
    b=match['battle']
    def public(mon):
        ratio=mon['hp']/mon['maxHp']
        return {'宠物':name(mon['name']),'属性':[name(t) for t in mon['types']],
                '剩余生命':mon['hp'],'生命上限':mon['maxHp'],'剩余生命百分比':round(ratio*100,1),
                '生命阶段':'满生命' if ratio==1 else '高于一半' if ratio>0.5 else '不高于三分之一' if ratio<=1/3 else '不高于一半',
                '状态':name(mon['status']),
                '面板能力':{name(k):v for k,v in mon['stats'].items()},'能力等级变化':mon['boosts']}
    return [{'id':f"public:turn:{b['turn']}",'source':'本地引擎当前公开局面与本局规则',
             'data':{'回合':b['turn'],'已完成回合':len(b['history']),'你的伙伴':public(b['player']),
                     '对手':public(b['opponent']),'已结束':b['ended'],
                     '对手策略':'根据当前公开局面优先评估命中与直接伤害；不偷看本轮行动，不代表全局最优。' if b.get('difficulty')=='challenge' else '随机选择可用招式',
                     '观察维度':['双方生命与状态','属性关系','物理与特殊攻防','标称命中与风险','优先度与速度','剩余招式次数'],
                     '己方招式概况':{'类别':sorted({name(m['category']) for m in b['advice']}),
                          '标称命中范围':[min(m['accuracy'] for m in b['advice']),max(m['accuracy'] for m in b['advice'])],
                          '优先度范围':[min(m.get('priority',0) for m in b['advice']),max(m.get('priority',0) for m in b['advice'])]} if b['advice'] else {},
                     '次数规则':'短局次数：基础次数除以10向上取整；双方相同。耗尽不可选；全部耗尽时只能挣扎，会反伤。' if b.get('ruleset')=='short-pp-v1' else '原有长局次数规则',
                     '己方剩余招式次数范围':[min(m['pp'] for m in b['advice'] if m['pp'] is not None),max(m['pp'] for m in b['advice'] if m['pp'] is not None)] if any(m['pp'] is not None for m in b['advice']) else []}},
            {'id':'public:principles','source':'本项目引导规则',
             'data':'物理看攻击与防御，特殊看特攻与特防；威力不等于实际伤害；通常先比优先度、再比速度；一次结果不能证明选择质量。'}]


def recent_dialogue(match,limit=6):
    from rococoach.session import dialogue_history
    return dialogue_history(match,limit)


def outcome(match):
    b=match['battle']
    if not b['ended']:return '达到回合上限，本局未分胜负' if b['capped'] else '对局尚未结束'
    return '你获胜了' if b['winner']=='Student' else '对手获胜' if b['winner']=='Trainer' else '平局'
