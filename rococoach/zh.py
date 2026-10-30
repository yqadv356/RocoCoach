"""Chinese presentation layer; engine IDs and mechanics remain untouched."""
from functools import lru_cache
import json
import re

from rococoach.config import ROOT


@lru_cache(maxsize=1)
def catalog():
    rows=json.loads((ROOT/"data/zh_catalog.json").read_text())["entries"]
    return {re.sub(r"[^a-z0-9]","",r["slug"].lower()):r["zh"] for r in rows if "zh" in r}


WORDS={"Struggle":"挣扎","vs":"对阵","healthy":"正常","fainted":"已失去战斗能力","brn":"灼伤","par":"麻痹","frz":"冰冻","psn":"中毒","tox":"剧毒","slp":"睡眠",
       "Physical":"物理","Special":"特殊","Status":"变化","Student":"你","Trainer":"陪练对手",
       "HP":"生命值","hp":"生命值","PP":"可用次数","atk":"攻击","def":"防御","spa":"特攻","spd":"特防","spe":"速度",
       "assigned_practice":"下一项练习","score":"比较分值","Miss":"未命中","STAB":"同属性加成"}


def name(value):
    if value in WORDS:
        return WORDS[value]
    return catalog().get(re.sub(r"[^a-z0-9]","",str(value).lower()),"未收录名称")


def text(value):
    value=str(value)
    # Evidence identifiers belong in the expandable proof panel, not dialogue.
    value=re.sub(r"\b(?:calc|move|turn|outcome|state):[a-zA-Z0-9_]+\b","对应依据",value)
    value=re.sub(r"\bmove\s+([1-4])\b",lambda m:f"第{m[1]}招",value,flags=re.I)
    replacements=dict(WORDS)
    for key,label in catalog().items():
        replacements[key]=label
    # Handle spaced engine names as well as compact IDs.
    for key,label in {"Quick Attack":"电光一闪","Iron Tail":"铁尾","Water Gun":"水枪","Ice Beam":"冰冻光束",
                      "Air Slash":"空气斩","Dragon Claw":"龙爪","Razor Leaf":"飞叶快刀","Sludge Bomb":"污泥炸弹","Take Down":"猛撞"}.items():
        replacements[key]=label
    pattern=r"(?<![A-Za-z0-9_])("+"|".join(re.escape(k) for k in sorted(replacements,key=len,reverse=True))+r")(?![A-Za-z0-9_])"
    bylower={k.lower():v for k,v in replacements.items()}
    return re.sub(pattern,lambda m:bylower[m[0].lower()],value,flags=re.I)


def dialogue(value, allowed_identifiers=()):
    # Presentation must not discard an entire valid answer because a nickname or
    # unknown proper noun contains Latin letters. Translate known terms only.
    return text(value)


def move_rows(moves, detailed=False):
    rows=[]
    for move in moves:
        row={"招式":name(move["name"]),"属性":name(move["type"]),"威力":move["power"],"命中率":f"{move['accuracy']}%"}
        if detailed:
            row.update({"预计伤害":f"{move['minDamage']}～{move['maxDamage']}","比较分值":round(move["score"],1)})
        rows.append(row)
    return rows


def calculation(move):
    return (f"{name(move['name'])}：命中且没有击中要害时，预计造成 {move['minDamage']}～{move['maxDamage']} 点伤害；"
            f"标称命中率 {move['accuracy']}%。当前直接伤害比较分值 {move['score']:.1f}，不等于胜率。")


def stat_rows(mon):
    return [{"能力":name(k),"数值":v} for k,v in mon["stats"].items()]


def matchup_rows(battle, show_damage=True):
    """Explain engine facts; do not reimplement damage or reveal an active quiz ranking."""
    defender=battle["opponent"]["stats"]
    rows=[]
    for move in sorted(battle["advice"],key=lambda m:m["choice"]):
        category=move["category"]
        defense=(f"防御 {defender['def']}" if category=="Physical" else
                 f"特防 {defender['spd']}" if category=="Special" else "按招式机制")
        row={"招式":name(move["name"]),"类别":name(category),"对方抵挡能力":defense,
             "属性倍率":f"×{move['effectiveness']:g}","本系加成":"有" if move["sameType"] else "无"}
        if show_damage:row["命中时伤害"]=f"{move['minDamage']}～{move['maxDamage']}"
        rows.append(row)
    return rows


def event_lines(events):
    rows=[]
    for raw in events:
        parts=raw.split("|")
        if len(parts)<3:continue
        kind=parts[1]
        if kind=="move":
            actor="你" if parts[2].startswith("p1") else "对手"
            rows.append(f"{actor}使用了{name(parts[3])}。")
        elif kind=="-supereffective":rows.append("效果拔群！")
        elif kind=="-resisted":rows.append("这招被对方属性抵抗了。")
        elif kind=="-miss":rows.append("这次没有命中。")
        elif kind=="-crit":rows.append("击中了要害！")
        elif kind=="faint":rows.append(("你的宠物" if parts[2].startswith("p1") else "对方宠物")+"失去战斗能力。")
        elif kind=="-status" and len(parts)>3:rows.append(("你的宠物" if parts[2].startswith("p1") else "对方宠物")+"进入"+name(parts[3])+"状态。")
    return rows


def validate_species(value, allowed):
    """Reject known species absent from the supplied scene; not full semantic proof."""
    rows=json.loads((ROOT/"data/zh_catalog.json").read_text())["entries"]
    translated=text(value)
    allowed_text=text(allowed)
    wrong=[r["zh"] for r in rows if r["kind"]=="species" and r["zh"] in translated and r["zh"] not in allowed_text]
    if wrong:
        from rococoach.llm import ModelUnavailable
        raise ModelUnavailable("教练混淆了当前场景的宠物，本次回答未通过检查，请重新问一次。")


def validate_claim_language(value):
    """Local negation-aware wording guard; still not semantic entailment proof."""
    translated=text(value)
    for match in re.finditer("必中|必胜|绝对最优|保证获胜",translated):
        prefix=re.split(r"[，。！？；,.;!?\n]",translated[:match.start()])[-1]
        negated=re.search(r"(?:不保证|不能保证|无法保证|不等于|不是|并非|不代表|不意味着|不承诺|不要|避免|并不).{0,8}$",prefix)
        if not negated:
            from rococoach.llm import ModelUnavailable
            raise ModelUnavailable("这次解释用了过于绝对的判断，未通过检查，请重试。")
