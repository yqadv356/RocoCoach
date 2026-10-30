"""Retro handheld presentation; render saved state, never compute battle outcomes."""
from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=16)
def asset(path):
    return 'data:image/png;base64,'+b64encode((ROOT/'assets/vendor/rpgui'/path).read_bytes()).decode()


def theme():
    css=(ROOT/'assets/handheld.css').read_text()
    for token,path in [('FRAME','img/border-image-grey.png'),
                       ('BUTTON','img/button.png'),('HOVER','img/button-hover.png'),('DOWN','img/button-down.png')]:
        css=css.replace('__'+token+'__',asset(path))
    return '<style>'+css+'</style>'


def pet_sprite(species):
    # Original schematic pixel creatures, not copied game sprites.
    turtle=[
        '       OOOO         ', '      OCCCO         ', '     OCCCCCO        ',
        '     OCWCKCO        ', '     OCCCCCO        ', '      OCCCCO        ',
        '    OOOOCCOOOO      ', '   OCCCSSSSSSSO     ', '  OCCCCSSDDSSSSO    ',
        '  OCCCSSDDDDSDSO    ', '   OCCSSDDDDSSSO    ', '   OCCCSSDDSSSSO    ',
        '    OCCCCSSSSSO     ', '   OCCCOOOOCCO      ', '   OCCC    OCCO     ', '    OOO     OOO     ']
    electric=[
        '  OO        OO      ', '  OKO      OKO      ', '  OCO     OCCO      ',
        '  OCCO   OCCCO      ', '   OCCOOOCCCO  OOO  ', '   OCCCCCCCCO OCCO  ',
        '   OCWKCCKWCOOCCO   ', '   OCCCCCCCCOCCO    ', '   OCRCCCRCCOOCO    ',
        '    OCCCCCCO OCO    ', '   OOCCCCCCOOCO     ', '  OCCOCCCCCCOO      ',
        '   OOCCCCCCCO       ', '    OCCOOCCCO       ', '   OCCC  OCCCO      ', '    OOO   OOO       ']
    dragon=['  OO       OO       ','  OCO     OCO       ','   OCCOOOCCO        ','   OCCCCCCCO        ','  OCCKWCCCCCO       ','   OCCCCCCCO        ','    OCCCCO   OO     ','   OOCCCCOO OCCO    ','  OCOCCCCOCOCCO     ',' OCCOCCCCOCCCO      ',' OCOCCCCCCCO        ','  OOCCCCCCCO OO     ','   OCCCCCCCOOCO     ','  OCCCOOOCCCO       ','  OCCO   OCCO       ','   OO     OO        ']
    flower=['     RRRRRRR        ','    RDDDDRDDR       ','     RDRDDDR        ','      RRRRR         ','    SSSCSSSS        ','   SCCCCCCCCS       ','  OCCCCCCCCCCO      ','  OCWKCCKWCCCO      ','  OCCCCCCCCCCO      ','   OCCCCCCCCO       ','  OCCCCCCCCCCO      ','  OCCCCCCCCCCO      ','   OCCCOOCCCO       ','   OCCO  OCCO       ','    OO    OO        ']
    is_electric=species=='Pikachu' 
    pattern=electric if is_electric else dragon if species=='Charizard' else flower if species=='Venusaur' else turtle
    body='#f4d65e' if is_electric else '#ed945d' if species in {'Charizard'} else '#8fbb72' if species=='Venusaur' else '#66bed4'
    palette={'O':'#18253d','C':body,'S':'#b37a4d','D':'#e9bd7a','W':'#fff8e2','K':'#18253d','R':'#db5d61'}
    rects=''.join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{palette[c]}"/>'
                  for y,row in enumerate(pattern) for x,c in enumerate(row) if c in palette)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 17" shape-rendering="crispEdges">{rects}</svg>'
    return 'data:image/svg+xml;base64,'+b64encode(svg.encode()).decode()


def arena(battle):
    from rococoach.zh import name
    def hud(side,label):
        m=battle[side];ratio=max(0,min(1,m['hp']/m['maxHp']));color='#6bc39b' if ratio>.5 else '#efc863' if ratio>1/3 else '#ed797c'
        return f'''<div class="pixel-hud {side}-hud"><div class="hud-head"><b>{escape(name(m['name']))}</b><span>{label} · 50级</span></div>
        <div class="hp-track" role="progressbar" aria-label="{label}剩余生命" aria-valuenow="{m['hp']}" aria-valuemin="0" aria-valuemax="{m['maxHp']}"><i style="width:{ratio*100:.3f}%;background:{color}"></i></div>
        <div class="hud-foot"><span>{escape(' / '.join(name(t) for t in m['types']))}</span><strong>{m['hp']} / {m['maxHp']}</strong></div></div>'''
    return f'''<section class="handheld-arena" aria-label="对战场，状态来自实际对局记录">
    <div class="arena-top"><span><img width="16" height="16" src="{asset('img/icons/sword.png')}" alt=""> 训练对战</span><span>第 {battle['turn']} 回合{' · 已结束' if battle['ended'] or battle['capped'] else ''}</span></div>
    <div class="arena-screen">{hud('opponent','对手')}{hud('player','你的伙伴')}
    <div class="arena-moon"></div><div class="arena-ridge"></div>
    <div class="pet-platform opponent-platform"></div><div class="pet-platform player-platform"></div>
    <img class="pixel-pet opponent-pet" src="{pet_sprite(battle['opponent']['name'])}" alt="对手宠物像素示意图">
    <img class="pixel-pet player-pet" src="{pet_sprite(battle['player']['name'])}" alt="你的伙伴像素示意图">
    </div></section>'''
