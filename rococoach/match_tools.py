"""Read-only whole-match tools. Calculations never advance the player's game."""
import hashlib
import json
from typing import Literal

from pydantic import ConfigDict, BaseModel, Field

from rococoach.battle import simulate
from rococoach.zh import name


class AlternativeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    turn: int = Field(ge=1, le=60)
    choice: Literal['move 1', 'move 2', 'move 3', 'move 4']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def key_turns(match):
    """Candidate selection by observable changes, never a player-skill score."""
    candidates = []
    for f in match['frames']:
        before, after = f['before'], f['after']
        changes = {side: round((before[side]['hp']-after[side]['hp'])/before[side]['maxHp']*100, 2)
                   for side in ('player', 'opponent')}
        tags = []
        for side, label in [('player', '己方'), ('opponent', '对手')]:
            if abs(changes[side]) >= 25: tags.append(label+'生命净变化达到上限的四分之一')
            if before[side]['status'] != after[side]['status']: tags.append(label+'状态改变')
            if before[side]['boosts'] != after[side]['boosts']: tags.append(label+'能力等级改变')
        if after['ended'] or after['capped']: tags.append('终局')
        magnitude = max(abs(v) for v in changes.values())
        candidates.append({'回合': f['turn'], '入选线索': tags or ['生命变化供对照'],
                           '生命净消耗占上限百分比': {'己方': changes['player'], '对手': changes['opponent']},
                           '_priority': (bool(after['ended'] or after['capped']), len(tags), magnitude)})
    selected = sorted(candidates, key=lambda x: x['_priority'], reverse=True)[:3]
    return {'候选回合': [{k:v for k,v in c.items() if k != '_priority'} for c in sorted(selected, key=lambda x:x['回合'])],
            '筛选规则': '优先终局，再看状态/能力变化和生命变化幅度，最多三回合；这是可解释的回看入口，不是失误检测或最优策略判定。',
            '边界': '净生命变化包括回合其他效果；正值表示净消耗，负值表示净恢复。未入选不代表不重要。'}


def replay_alternative(match, args):
    frame = next((f for f in match['frames'] if f['turn'] == args.turn), None)
    if frame is None: raise ValueError('该回合没有发生。')
    before = frame['before']
    legal = {m['choice']:m for m in before['advice'] if not m['disabled']}
    if args.choice not in legal: raise ValueError('该回合不能使用这个招式。')
    if args.choice == frame['choice']: raise ValueError('请提供与实际行动不同的候选招式。')
    original_hash = digest(match)
    alternative = simulate(before['scenario'], before['seed'], before['history'] + [args.choice],ruleset=before.get('ruleset','standard-v1'),difficulty=before.get('difficulty','standard'))
    if alternative['history'] != before['history'] + [args.choice]:
        raise RuntimeError('独立分支未正确执行，不返回比较结果。')
    if digest(match) != original_hash: raise RuntimeError('对局完整性检查未通过。')
    def result(b):
        return {'己方剩余生命': b['player']['hp'], '对手剩余生命': b['opponent']['hp'],
                '己方状态': name(b['player']['status']), '对手状态': name(b['opponent']['status']),
                '已结束': b['ended'], '胜者': name(b['winner']) if b['winner'] else None}
    return {'回合': args.turn, '实际招式': name(frame['actual']['selected']),
            '另一个招式': name(legal[args.choice]['name']),
            '实际回合结束': result(frame['after']), '分支回合结束': result(alternative),
            '相对实际的剩余生命差': {'己方': alternative['player']['hp']-frame['after']['player']['hp'],
                               '对手': alternative['opponent']['hp']-frame['after']['opponent']['hp']},
            '复现参数': {'场景': before['scenario'], '种子': before['seed'], '规则版本':before.get('ruleset','standard-v1'), '训练档位':before.get('difficulty','standard'), '历史前缀': before['history'], '候选行动': args.choice},
            '引擎': alternative['engine'], '真实对局未改变': True, '对局哈希': original_hash,
            '边界': '只从该回合出招前重放一个回合，不延伸整局。固定种子单样本，不是期望伤害、胜率或因果效果估计；改变行动可能改变随机数消耗，不能假定其他随机事件完全相同。'}
