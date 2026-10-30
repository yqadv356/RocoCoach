// Export the installed, pinned rules only; no network or game state mutation.
'use strict';
const fs=require('node:fs');
const {Dex}=require('pokemon-showdown');
const version=require('pokemon-showdown/package.json').version;
if(version!=='0.11.11')throw Error('Review knowledge export when engine version changes');
const labels=JSON.parse(fs.readFileSync(0,'utf8')).entries;
const moves=labels.filter(x=>x.kind==='move').map(row=>{
 const m=Dex.moves.get(row.slug);
 if(!m.exists)throw Error('Unknown move: '+row.slug);
 return {id:m.id,name:m.name,zh:row.zh,type:m.type,category:m.category,
   power:m.basePower,accuracy:m.accuracy,priority:m.priority,pp:m.pp,
   description:m.desc||m.shortDesc||''};
});
const species=labels.filter(x=>x.kind==='species').map(row=>{
 const p=Dex.species.get(row.slug);
 if(!p.exists)throw Error('Unknown species: '+row.slug);
 return {id:p.id,name:p.name,zh:row.zh,types:p.types,abilities:Object.values(p.abilities)};
});
process.stdout.write(JSON.stringify({engine:'pokemon-showdown',version,generation:9,moves,species}));
