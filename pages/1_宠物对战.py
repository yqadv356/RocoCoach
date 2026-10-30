import streamlit as st

from rococoach.battle import SCENARIOS, report, simulate
from rococoach.zh import name, text, move_rows, calculation, event_lines

st.set_page_config(page_title="自由对战 · 洛洛教练",page_icon="⚔️",layout="wide")
st.title("⚔️ 自由对战：你来出招，洛洛陪练")
st.caption("先自己打，想比较招式时再看军师。这里采用宝可梦规则，不代表洛克王国机制。")
with st.expander("选择教学场景",expanded="battle" not in st.session_state):
    scenario=st.selectbox("场景",list(SCENARIOS),format_func=lambda s:text(SCENARIOS[s]))
    seed=st.number_input("练习编号（相同编号可重现对局）",0,65535,42)
    if st.button("开始 / 重置对局",type="primary"):
        try:st.session_state["battle"]=simulate(scenario,int(seed))
        except (ValueError,RuntimeError) as exc:st.error(str(exc))
if "battle" not in st.session_state:
    st.write("选个场景，开始一局。对手会从可用招式里随机选择。")
    st.stop()
battle=st.session_state["battle"]
st.subheader(text(battle["title"]))
st.caption(f"已完成 {len(battle['rounds'])} 回合")
for col,label,mon in zip(st.columns(2),["你的伙伴","陪练对手"],[battle["player"],battle["opponent"]]):
    with col.container(border=True):
        st.subheader(label+" · "+name(mon["name"]))
        st.progress(mon["hp"]/mon["maxHp"],text=f"生命值 {mon['hp']} / {mon['maxHp']}")
        st.caption(" / ".join(name(t) for t in mon["types"])+"属性 · "+name(mon["ability"])+" · "+("已失去战斗能力" if mon["hp"]==0 else name(mon["status"])))
if battle["ended"]:st.success("对局结束："+("你获胜了" if battle["winner"]=="Student" else "陪练获胜" if battle["winner"]=="Trainer" else "平局"))
elif battle["capped"]:st.warning("已达到这次练习的回合上限，换一局试试。")
practice,advisor,teacher,replay=st.tabs(["🎮 我来选招","🧭 看看军师","📖 学个小知识","📝 这局复盘"])

def advance(history,autoplay=False):
    try:updated=simulate(battle["scenario"],battle["seed"],history,autoplay=autoplay)
    except (ValueError,RuntimeError) as exc:st.error(str(exc));return
    st.session_state["battle"]=updated;st.rerun()

with practice:
    if not battle["ended"] and not battle["capped"]:
        moves=sorted((m for m in battle["advice"] if not m["disabled"]),key=lambda m:m["choice"])
        selected=st.selectbox("本回合招式",moves,format_func=lambda m:f"{name(m['name'])} · {name(m['type'])}属性 · 还能用{m['pp']}次",key=f"move_{len(battle['history'])}_{battle['scenario']}")
        if st.button("执行这一回合",type="primary"):advance(battle["history"]+[selected["choice"]])
        if st.button("观看军师自动打完"):advance(battle["history"],autoplay=True)
        st.caption("自动演示按当前直接伤害比较出招，不是高手策略。")
    if battle["history"] and st.button("撤销上一回合"):advance(battle["history"][:-1])
    if battle["rounds"]:
        for line in event_lines(battle["rounds"][-1]["events"]):st.write(line)
with advisor:
    if battle["advice"]:
        best=next(m for m in battle["advice"] if not m["disabled"])
        with st.chat_message("assistant",avatar="🦊"):
            st.write(f"这一回合可以先比较{name(best['name'])}。它的命中率是{best['accuracy']}%，命中时预计造成{best['minDamage']}～{best['maxDamage']}点伤害。")
        st.caption("这里只比较当前直接伤害，实际还会受状态、要害和附加效果影响。")
        with st.expander("展开比较其他招式"):
            st.table(move_rows(battle["advice"],detailed=True))
    else:st.write("这局结束啦。可以撤销一回合，或者换个场景继续练。")
with teacher:
    st.write("先看属性和命中，再比较威力。威力更大，不一定更适合当前局面。")
    for move in battle["advice"] or battle["lessons"]:
        with st.expander(name(move["name"])+" · "+name(move["type"])+"属性"):
            st.write(f"这是{name(move['category'])}招式，威力{move['power']}，标称命中率{move['accuracy']}%。")
            st.write(f"与己方属性相同：{'是' if move['sameType'] else '否'}；对方属性造成的伤害倍率：{move['effectiveness']}倍。")
            st.write(calculation(move))
            if not battle["advice"]:st.caption("对局已结束，这里回顾开局数据。")
with replay:
    if battle["rounds"]:
        st.table([{"回合":r["turn"],"你的选择":name(r["selected"]),"计算排序首位":name(r["recommended"]),"你的生命":f"{r['playerHpBefore']} → {r['playerHpAfter']}","对手生命":f"{r['opponentHpBefore']} → {r['opponentHpAfter']}"} for r in battle["rounds"]])
    st.caption("生命净变化可能包括反伤等效果；与计算排序一致也不等于战术最优。")
    st.download_button("下载本局复盘",report(battle),"对战复盘.md",mime="text/markdown")
    with st.expander("面试核验：原始对战日志"):
        st.code(battle["log"],language="text")
        st.markdown("[对战引擎源码](https://github.com/smogon/pokemon-showdown) · [伤害计算器源码](https://github.com/smogon/damage-calc)")
