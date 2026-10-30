// Adapter only: battle rules and random opponent are from Pokemon Showdown;
// damage ranges are from @smogon/calc. See THIRD_PARTY.md.
'use strict';
const fs = require('node:fs');
const {Battle, Dex} = require('pokemon-showdown');
const {RandomPlayerAI} = require('pokemon-showdown/dist/sim/tools/random-player-ai');
const calc = require('@smogon/calc');
const gen = calc.Generations.get(9);
const ZERO = {hp:0, atk:0, def:0, spa:0, spd:0, spe:0};
function set(species, ability, moves) {
  return {species, ability, moves, level:50, nature:'Hardy', evs:{...ZERO}, gender:'M'};
}
const scenarios = {
  practice: {title:'均衡对练：杰尼龟 vs 杰尼龟',
    p1:set('Squirtle','Torrent',['Water Gun','Tackle','Bite','Ice Beam']),
    p2:set('Squirtle','Torrent',['Water Gun','Tackle','Bite','Ice Beam'])},
  electric: {title:'属性与命中：皮卡丘 vs 杰尼龟',
    p1:set('Pikachu','Static',['Thunderbolt','Quick Attack','Iron Tail','Thunder']),
    p2:set('Squirtle','Torrent',['Water Gun','Tackle','Bite','Ice Beam'])},
  fire: {title:'不同招式的收益：喷火龙 vs 妙蛙花',
    p1:set('Charizard','Blaze',['Flamethrower','Air Slash','Dragon Claw','Scratch']),
    p2:set('Venusaur','Overgrow',['Razor Leaf','Sludge Bomb','Tackle','Take Down'])},
  water: {title:'比较伤害区间：水箭龟 vs 喷火龙',
    p1:set('Blastoise','Torrent',['Surf','Ice Beam','Bite','Tackle']),
    p2:set('Charizard','Blaze',['Flamethrower','Air Slash','Dragon Claw','Scratch'])},
};
function asCalc(p) {
  return new calc.Pokemon(gen,p.species.name,{
    level:p.level,nature:p.set.nature,evs:p.set.evs,ivs:p.set.ivs,
    ability:Dex.abilities.get(p.ability).name,item:p.item,
    boosts:p.boosts,curHP:p.hp,status:p.status,
  });
}
function details(p) {
  return {name:p.species.name, hp:p.hp,maxHp:p.maxhp,types:p.getTypes(),
    status:p.status || 'healthy', ability:Dex.abilities.get(p.ability).name,
    stats:p.baseStoredStats, boosts:p.boosts};
}
function advice(b, side=0) {
  if (b.ended) return [];
  const me=b.sides[side].active[0], foe=b.sides[1-side].active[0];
  return b.sides[side].activeRequest.active[0].moves.map((m,i)=>{
    const move=Dex.moves.get(m.id);
    const result=calc.calculate(gen,asCalc(me),asCalc(foe),new calc.Move(gen,move.name));
    const [low,high]=result.range();
    const accuracy=typeof move.accuracy==='number'?move.accuracy:100;
    return {choice:`move ${i+1}`,name:move.name,type:move.type,category:move.category,
      power:move.basePower,accuracy,priority:move.priority,pp:m.pp ?? null,maxPp:m.maxpp ?? null,disabled:!!m.disabled,
      minDamage:low,maxDamage:high,score:(low+high)/2*accuracy/100,
      effectiveness:move.id==='struggle'?1:Dex.getImmunity(move.type,foe.getTypes())?2**Dex.getEffectiveness(move.type,foe.getTypes()):0,
      sameType:move.id!=='struggle'&&me.getTypes().includes(move.type),description:move.desc || move.shortDesc || '',
      calculation:result.desc()};
  }).sort((a,b)=>b.score-a.score);
}
function state(b) {
  return {turn:b.turn,ended:!!b.ended,winner:b.winner || null,
    player:details(b.p1.active[0]),opponent:details(b.p2.active[0]),advice:advice(b)};
}
function run(input) {
  const {scenario='electric',seed=42,history=[],autoplay=false,ruleset='standard-v1',difficulty='standard'}=input;
  if (!['standard','challenge'].includes(difficulty)) throw Error('Unknown difficulty');
  if (!['standard-v1','short-pp-v1'].includes(ruleset)) throw Error('Unknown ruleset');
  if (!Object.hasOwn(scenarios,scenario)) throw Error('Unknown scenario');
  if (!Number.isInteger(seed)||seed<0||seed>65535) throw Error('Seed must be 0–65535');
  if (!Array.isArray(history)||history.length>60) throw Error('History limit is 60 turns');
  const s=scenarios[scenario];
  const b=new Battle({formatid:'gen9customgame',seed:[seed,2,3,4],
    p1:{name:'Student',team:[structuredClone(s.p1)]},
    p2:{name:'Trainer',team:[structuredClone(s.p2)]}});
  // Configure both sides before turn-one requests are generated. This is an
  // explicit local training rule, not a change to Dex data or damage formulas.
  if (ruleset==='short-pp-v1') for (const side of b.sides) for (const p of side.pokemon) {
    for (const slot of p.baseMoveSlots) {
      slot.pp=slot.maxpp=Math.max(1,Math.ceil(Dex.moves.get(slot.id).pp/10));
    }
    p.moveSlots=p.baseMoveSlots.slice();
  }
  b.makeChoices('team 1','team 1');
  let opponentChoice;
  const opponent=new RandomPlayerAI({write(choice){opponentChoice=choice;}},{seed:[seed,4,3,2]});
  const lessons=advice(b);
  const rounds=[],choices=[];
  function step(choice) {
    if (b.ended) throw Error('Battle has ended');
    const before=state(b);
    const selected=before.advice.find(x=>x.choice===choice && !x.disabled);
    if (!selected) throw Error('Illegal or disabled move');
    const suggested=before.advice.find(x=>!x.disabled);
    opponentChoice=null;
    if (difficulty==='challenge') opponentChoice=advice(b,1).find(m=>!m.disabled).choice;
    else opponent.receiveRequest(b.p2.activeRequest);
    if (!opponentChoice) throw Error('Opponent did not return a choice');
    const start=b.log.length;
    // Both choices are committed before the engine resolves the turn.
    b.makeChoices(choice,opponentChoice);
    if (b.turn===before.turn&&!b.ended) throw Error('Engine did not advance');
    choices.push(choice);
    rounds.push({turn:before.turn,selected:selected.name,recommended:suggested.name,
      matched:selected.choice===suggested.choice,expectedRange:[selected.minDamage,selected.maxDamage],
      playerHpBefore:before.player.hp,playerHpAfter:b.p1.active[0].hp,
      opponentHpBefore:before.opponent.hp,opponentHpAfter:b.p2.active[0].hp,
      events:b.log.slice(start).filter(x=>!x.startsWith('|t:|'))});
  }
  for (const choice of history) step(choice);
  if (autoplay) while (!b.ended&&choices.length<60) step(advice(b).find(x=>!x.disabled).choice);
  const output={scenario,title:s.title,seed,ruleset,difficulty,opponentPolicy:difficulty==='challenge'?'public-damage-v1':'random-v1',history:choices,rounds,lessons,...state(b),
    log:b.log.filter(x=>!x.startsWith('|t:|')).join('\n'),
    engine:'pokemon-showdown@0.11.11',calculator:'@smogon/calc@0.12.0',
    capped:!b.ended&&choices.length>=60};
  b.destroy();
  return output;
}
module.exports={run,advice};
if (require.main===module) {
  try { process.stdout.write(JSON.stringify(run(JSON.parse(fs.readFileSync(0,'utf8'))))); }
  catch(e) { process.stderr.write(String(e.message)); process.exitCode=1; }
}
