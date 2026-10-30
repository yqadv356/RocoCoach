from rococoach.battle import simulate
from rococoach.zh import matchup_rows


def test_explanation_uses_different_defenses_and_engine_damage():
    battle=simulate()
    rows={r["招式"]:r for r in matchup_rows(battle)}
    assert rows["十万伏特"]["对方抵挡能力"]==f"特防 {battle['opponent']['stats']['spd']}"
    assert rows["电光一闪"]["对方抵挡能力"]==f"防御 {battle['opponent']['stats']['def']}"
    move=next(m for m in battle["advice"] if m["name"]=="Thunderbolt")
    assert rows["十万伏特"]["命中时伤害"]==f"{move['minDamage']}～{move['maxDamage']}"
    assert all("命中时伤害" not in row for row in matchup_rows(battle,show_damage=False))
