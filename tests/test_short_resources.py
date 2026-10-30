"""Real-engine resource limits, replay versioning and exhaustion boundaries."""
from copy import deepcopy
import json
import subprocess

import pytest

from rococoach.battle import ROOT, node_path, simulate, SCENARIOS
from rococoach.match import new_match, advance, neutral_facts
from rococoach.match_tools import AlternativeArgs, replay_alternative

SHORT = 'short-pp-v1'


def test_use_consumes_resource_and_exhausted_move_cannot_advance():
    game = new_match(ruleset=SHORT)
    opening = {m['choice']: m for m in game['battle']['advice']}
    assert [opening[f'move {i}']['pp'] for i in range(1, 5)] == [3, 4, 3, 1]
    game = advance(game, 'move 4', expected_round=0)
    ice = next(m for m in game['battle']['advice'] if m['choice'] == 'move 4')
    assert ice['pp'] == 0 and ice['maxPp'] == 1 and ice['disabled']
    original = deepcopy(game)
    with pytest.raises(ValueError, match='不可用'):
        advance(game, 'move 4', expected_round=1)
    with pytest.raises(RuntimeError, match='Illegal'):
        simulate('practice', 42, ['move 4', 'move 4'], ruleset=SHORT)
    assert game == original
    assert new_match(ruleset=SHORT)['battle']['advice'] == list(game['battle']['lessons'])
    assert '短局次数' in json.dumps(neutral_facts(game), ensure_ascii=False)


@pytest.mark.parametrize('scenario', SCENARIOS)
@pytest.mark.parametrize('seed', [42, 71])
def test_short_matches_finish_and_reproduce(scenario, seed):
    b = simulate(scenario, seed, autoplay=True, ruleset=SHORT)
    assert b['ended'] and not b['capped']
    assert max(m['maxPp'] for m in b['lessons']) <= 4
    replay = simulate(scenario, seed, b['history'], ruleset=SHORT)
    assert replay['rounds'] == b['rounds'] and replay['log'] == b['log']


def test_legacy_and_short_branch_keep_their_own_rules():
    legacy = new_match()
    assert next(m['pp'] for m in legacy['battle']['advice'] if m['name'] == 'Ice Beam') == 16
    legacy['battle'].pop('ruleset')  # Previously saved records have no version.
    legacy = advance(legacy, 'move 4', expected_round=0)
    assert legacy['battle']['ruleset'] == 'standard-v1'
    assert next(m['pp'] for m in legacy['battle']['advice'] if m['name'] == 'Ice Beam') == 15
    game = advance(new_match(ruleset=SHORT), 'move 4', expected_round=0)
    original = deepcopy(game)
    branch = replay_alternative(game, AlternativeArgs(turn=1, choice='move 2'))
    assert branch['复现参数']['规则版本'] == SHORT
    expected = simulate('practice', 42, ['move 2'], ruleset=SHORT)
    assert branch['分支回合结束']['对手剩余生命'] == expected['opponent']['hp']
    assert game == original and game['frames'][0]['before']['ruleset'] == SHORT


def test_both_sides_consume_on_miss_and_all_empty_falls_back_to_struggle():
    # A long-lived fixture exercises the otherwise rare all-exhausted boundary.
    # No special fixture parameters are exposed in the production bridge.
    script = r"""
    const assert=require('node:assert/strict');
    const {Battle}=require('./engine/node_modules/pokemon-showdown');
    const {advice,run}=require('./engine/bridge.cjs');
    const set={species:'Squirtle',ability:'Torrent',level:50,
      moves:['Tackle','Scratch','Pound','Water Gun']};
    const b=new Battle({formatid:'gen9customgame',seed:[42,2,3,4],
      p1:{name:'Student',team:[structuredClone(set)]},
      p2:{name:'Trainer',team:[structuredClone(set)]}});
    for(const side of b.sides) for(const p of side.pokemon){
      for(const slot of p.baseMoveSlots)slot.pp=slot.maxpp=1;
      p.moveSlots=p.baseMoveSlots.slice();
    }
    b.makeChoices('team 1','team 1');
    for(const side of b.sides){side.active[0].hp=side.active[0].maxhp=10000;}
    for(let i=1;i<=4;i++)b.makeChoices(`move ${i}`,`move ${i}`);
    for(const side of b.sides){
      assert(side.active[0].moveSlots.every(s=>s.pp===0));
      assert.equal(side.activeRequest.active[0].moves[0].id,'struggle');
    }
    const fallback=advice(b);
    assert.equal(fallback.length,1);assert.equal(fallback[0].name,'Struggle');
    assert.equal(fallback[0].pp,null);assert.equal(fallback[0].maxPp,null);
    assert.equal(fallback[0].disabled,false);
    b.makeChoices('move 1','move 1');
    assert(b.log.some(line=>line.includes('[from] recoil')));
    b.destroy();
    let found=false;
    for(let seed=0;seed<30&&!found;seed++){
      const game=run({scenario:'electric',seed,history:['move 3'],ruleset:'short-pp-v1'});
      if(game.rounds[0].events.some(line=>line.startsWith('|-miss|p1a:'))){
        assert.equal(game.advice.find(m=>m.name==='Iron Tail').pp,1);found=true;
      }
    }
    assert(found,'Need an actual miss, not a fabricated PP counter');
    process.stdout.write('symmetric deduction, exhaustion, recoil, missed move: passed');
    """
    result = subprocess.run([node_path(), '-e', script], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_page_uses_short_resources_and_labels_actual_remaining(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from rococoach.llm import ModelUnavailable
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB', tmp_path/'ui.db')
    def offline():
        raise ModelUnavailable('离线界面验证')
    monkeypatch.setattr('rococoach.llm.configuration', offline)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    assert not app.exception
    assert app.session_state['match']['battle']['ruleset'] == SHORT
    pick = next(s for s in app.selectbox if s.label == '这回合用哪招')
    assert '冰冻光束 · 剩1/1次' in pick.options
    pick.select('move 4')
    next(b for b in app.button if b.label == '出招').click().run()
    assert not app.exception
    pick = next(s for s in app.selectbox if s.label == '这回合用哪招')
    assert not any('冰冻光束' in option for option in pick.options)
    assert any('0/1' in table.value.to_string() for table in app.table)
