"""One scene, one conversation, one primary action for each learning stage."""
from html import escape
import json
import uuid

import streamlit as st

from rococoach.battle import SCENARIOS, simulate
from rococoach.agent import branch_summary
from rococoach.companion import coach_reply
from rococoach.llm import ModelUnavailable, configuration
from rococoach.live_ui import LiveOutput
from rococoach.memory import Memory
from rococoach.routing import route_query
from rococoach.session import select_context, dialogue_history
from rococoach.tutor import make_context, next_quiz, review
from rococoach.zh import name, text, dialogue, move_rows, calculation, stat_rows, matchup_rows, event_lines

st.set_page_config(page_title="洛洛 · 对战搭子",page_icon="🦊",layout="wide")
st.html("""<style>
:root{--sage:#3e6556;--ink:#243c33;--quiet:#78827a}
.stApp{background:#f6f7f3;color:var(--ink)}
.block-container{max-width:1040px;padding:2.8rem 2rem 1.3rem}
header[data-testid="stHeader"]{background:transparent;height:0}
[data-testid="stToolbar"],#MainMenu,[data-testid="stDecoration"]{display:none!important}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none!important}
[data-testid="stVerticalBlock"]{gap:0.9rem}
[data-testid="stForm"]{border:0;padding:0}
[data-testid="stChatMessage"]{background:transparent;padding:.5rem 0;border:0}
[data-testid="stChatMessageAvatarAssistant"],[data-testid="stChatMessageAvatarUser"]{display:none}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"]{background:#edf2eb;border-radius:4px 18px 18px 18px;padding:13px 16px}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"]{background:#fff;border:1px solid #e3e8df;border-radius:18px 4px 18px 18px;padding:12px 16px}
[data-testid="stChatMessage"] p{font-size:.94rem;line-height:1.8}
[data-testid="stChatInput"]{border:1px solid #d5ded2;border-radius:16px;background:white}
[data-testid="stExpander"]{border:0;border-top:1px solid #e4e9e0;border-radius:0}
[data-testid="stExpander"] summary p{font-size:.83rem;color:var(--quiet)}
[data-testid="stBaseButton-primary"]{border-radius:11px;background:var(--sage);border-color:var(--sage);min-height:43px;box-shadow:none}
[data-testid="stBaseButton-secondary"]{border-radius:10px}
[data-testid="stTextInput"] input,[data-baseweb="select"]>div{background:#fff;border-radius:10px}
[data-testid="stProgressBar"]{margin-top:0}
.brand{display:flex;gap:12px;align-items:center;margin-bottom:5px}
.brand-mark{width:43px;height:43px;background:#e6ecdf;border-radius:15px;display:grid;place-items:center;font-size:21px;color:#4c6954}
.brand-name{font-size:23px;font-weight:650;letter-spacing:2px;line-height:1.4}
.brand-sub{font-size:12px;letter-spacing:1px;color:#7c877c;margin-top:2px}
.top-line{height:1px;background:#dfe6da;margin:16px 0 22px}
.eyebrow{font-size:11px;letter-spacing:2px;color:#7e8d79;margin-bottom:10px}
.scene-title{font-size:23px;font-weight:600;line-height:1.5;margin-bottom:5px}
.scene-sub{font-size:12px;color:#7b867d;margin-bottom:18px;line-height:1.8}
.st-key-practice_card{background:#fff;border-color:#e1e7dd!important;border-radius:18px!important;padding:22px!important}
.pet-name{font-size:15px;font-weight:600}.pet-tag{font-size:11px;color:#7e897e;margin-left:6px}
.section-name{font-size:16px;font-weight:600;margin:0 0 10px}
.lolo-label{font-size:11px;letter-spacing:2px;color:#7b8b76;margin-bottom:10px}
.footer-note{font-size:11px;color:#8b9488;text-align:center;margin-top:25px;letter-spacing:.5px}
@media(max-width:700px){.block-container{padding:1.3rem 1rem}.scene-title{font-size:20px}}
</style>""")
store=Memory()
try:ready=configuration()
except ModelUnavailable:ready=None


def new_lesson(scenario,seed):
    return {"id":uuid.uuid4().hex,"before":simulate(scenario,seed),"messages":[]}


def message(lesson,speaker,content,kind="chat",role=None,tool_summary=None):
    lesson.setdefault("messages",[]).append({"speaker":speaker,"text":content,"kind":kind,"role":role,"tool_summary":tool_summary})


def keep_review(lesson):
    result=lesson["result"];answer=result["answer"]
    store.add(lesson["id"],"review",{"topic":lesson["before"]["title"],"mode":result["metadata"]["mode"],"focus_status":"待下一次练习验证","focus":result["metadata"].get("agent",{}).get("practice_plan",{}).get("focus",answer["next_practice"]),"result":result})
    if not any(m["kind"]=="review" for m in lesson.setdefault("messages",[])):
        message(lesson,"assistant",dialogue(answer["feedback"]["text"]),"review")
        lesson["last_agent_trace"]=result["metadata"].get("agent")
    if "quiz" not in lesson:
        lesson["quiz"]=next_quiz(lesson["before"]["scenario"],lesson["before"]["seed"])


def generate_review(lesson,mode):
    if mode!='live':return review(lesson['context'],mode)
    view=LiveOutput(review_area,[ready.model] if ready else [])
    try:
        result=review(lesson['context'],mode,on_event=view)
        result['metadata']['stream']=view.complete(result['answer']['feedback']['text'])
        return result
    except (RuntimeError,ValueError):
        view.reject();raise


brand,settings=st.columns([8,1],vertical_alignment="center")
with brand:
    st.html('<div class="brand"><div class="brand-mark">洛</div><div><div class="brand-name">洛洛</div><div class="brand-sub">陪你，把下一步想清楚。</div></div></div>')
with settings:
    with st.popover("设置",type="tertiary",icon=":material/tune:"):
        with st.expander("我的偏好"):
            profile=store.profile()
            with st.form("profile"):
                nickname=st.text_input("称呼",profile["nickname"],max_chars=30)
                preference=st.text_input("希望我怎么讲",profile["preference"],max_chars=200)
                mood=st.selectbox("心情",["平静","有点挫败","想挑战"],index=["平静","有点挫败","想挑战"].index(profile["mood"]))
                if st.form_submit_button("保存偏好"):
                    store.save_profile(nickname,preference,mood);st.success("记住了。")
        with st.expander("练习设置"):
            scenario=st.selectbox("场景",list(SCENARIOS),format_func=lambda s:text(SCENARIOS[s]),key="studio_scenario")
            seed=st.number_input("练习编号",0,65535,42,key="studio_seed")
            if st.button("开始新的练习"):
                try:st.session_state["lesson"]=new_lesson(scenario,int(seed));st.rerun()
                except (RuntimeError,ValueError) as exc:st.error(str(exc))
        with st.expander("学习记录与回答依据"):
            st.caption("学习记录：保存练习、测验和聊天，方便回看；不是玩家水平认证。")
            st.caption("回答依据：查看教练实际查了什么、返回了什么，帮助核对建议；引用存在不等于解释一定正确。")
            st.markdown("**教练现在能记住什么**")
            st.caption("本次练习的近期对话：普通回应最多6轮，工具教练最多4轮。开始新的练习会重置这段对话。")
            st.caption("当前局面与学习阶段：区分出招前、实际回合和新场景小测；回指上一招时尝试选择对应证据，仍可能理解错。")
            st.caption("本机长期记录：保存明确偏好，提供最多5条近期学习摘要；工具教练需查学习记录后读取摘要。旧聊天可回看，但不会全部自动恢复到新对话，也没有自动提炼长期偏好。")
            st.markdown("**最近的本机记录**")
            for item in store.summary()["recent"][:3]:st.caption(text(item["topic"]))
            for item in store.chat_history(2):
                st.caption("你："+item["user"])
                st.caption("洛洛："+dialogue(item["assistant"],allowed_identifiers=[ready.model] if ready else []))
            st.caption("历史单回合练习页；当前主入口已改为整局陪练。")
            old=st.session_state.get("lesson",{})
            if old.get("failed_agent_trace"):
                st.json({"上次未完成的查证":old["failed_agent_trace"],"已返回的用量与预算统计":old.get("failed_agent_metadata")})
            route=old.get("last_routing",{})
            if route:
                sources={"lesson":"当前练习","previous_turn":"上一回合","transfer_quiz":"进行中的新场景小测","transfer_quiz_completed":"已完成的新场景小测"}
                st.caption("上次聊天选用的场景："+sources.get(route.get("context_source"),"当前练习")+"。场景选择与表达方式分别记录。")
            trace=old.get("last_agent_trace") if "last_agent_trace" in old else old.get("result",{}).get("metadata",{}).get("agent")
            if trace:
                st.caption("教练查证记录：实际工具请求与观察，不是内部思维链。")
                labels={"inspect_battle":"读取局面","compare_moves":"比较招式","search_rules":"检索规则","recall_learning":"查学习记录","inspect_review":"核对实际回合","simulate_alternative":"独立验证另一招","plan_practice":"安排练习重点"}
                for step in trace["trace"]:
                    if "tool" in step:st.caption(labels.get(step["tool"],"请求被拒绝"))
                st.json(trace,expanded=False)
            elif "last_agent_trace" in old:st.caption("最近一次回复没有调用工具；不把更早的查证冒充本轮依据。")
            if "result" in old:
                st.download_button("导出本次记录",json.dumps(old,ensure_ascii=False,indent=2),"学习记录.json",mime="application/json")
                st.json({"metadata":old["result"]["metadata"],"evidence":old["result"]["evidence"],"最近路由":old.get("last_routing")},expanded=False)
        with st.expander("模型与隐私"):
            mode_label=st.radio("回答来源",["智能教练","离线演示"],index=0 if ready else 1,key="studio_mode")
            st.caption("智能回答会发送本轮问题、近期对话、明确偏好，以及任务所需的对局和学习摘要。陪聊不发送当前伤害计算表。记录保存在本机。")
            if not ready:st.caption("模型未配置，当前可使用离线演示。")
mode="live" if mode_label=="智能教练" else "mock"
if mode=="mock":st.caption("离线演示 · 对话来自规则模板")
st.html('<div class="top-line"></div>')
if "lesson" not in st.session_state:
    try:st.session_state["lesson"]=new_lesson("electric",42)
    except (RuntimeError,ValueError) as exc:st.error(str(exc));st.stop()
lesson=st.session_state["lesson"]
lesson.setdefault("messages",[])
if "result" in lesson:keep_review(lesson)
before=lesson["before"]
shown=lesson.get("after",before)
board,conversation=st.columns([1,1.12],gap="large")
review_area=conversation.empty()

with board:
    with st.container(border=True,key="practice_card"):
        st.html('<div class="eyebrow">一 次 小 练 习</div>')
        if "result" not in lesson:
            st.html('<div class="scene-title">这一回合，怎么选？</div><div class="scene-sub">先试一招，再一起看看为什么。</div>')
        elif "quiz_result" not in lesson:
            st.html('<div class="scene-title">换个场景，你来判断。</div><div class="scene-sub">把刚才学到的，用在下一次选择里。</div>')
        else:
            st.html('<div class="scene-title">又想明白了一点。</div><div class="scene-sub">这次学习已记下，按自己的节奏继续。</div>')
        display=lesson["quiz"] if "result" in lesson else shown
        for label,mon in [("你的伙伴",display["player"]),("对手",display["opponent"])]:
            st.html(f'<div class="pet-name">{escape(name(mon["name"]))}<span class="pet-tag">{label} · {escape(" / ".join(name(t) for t in mon["types"]))}</span></div>')
            st.progress(mon["hp"]/mon["maxHp"],text=f"{mon['hp']} / {mon['maxHp']}")
        if "result" not in lesson and "after" not in lesson:
            moves=sorted(before["advice"],key=lambda m:m["choice"])
            with st.form("decision_"+lesson["id"]):
                choice=st.selectbox("这回合用哪招",[m["choice"] for m in moves],format_func=lambda c:name(next(m["name"] for m in moves if m["choice"]==c)))
                reason=st.text_input("你的想法",placeholder="为什么选它？拿不准也可以直说",max_chars=1000,label_visibility="collapsed")
                execute=st.form_submit_button("出招",type="primary",width="stretch")
            if lesson.get("review_error"):st.error(lesson["review_error"])
            if execute:
                try:
                    after=simulate(before["scenario"],before["seed"],before["history"]+[choice])
                    # Commit the executed turn before the model request, so retries never replay it.
                    context=make_context(before,after,choice,reason.strip() or "我还拿不准，想先试一招再理解。",store.summary())
                    lesson.update(after=after,context=context)
                    lesson["requested_mode"]=mode
                    lesson["review_routing"]=route_query("",event="review").as_dict()
                    message(lesson,"user",f"我选{name(next(m['name'] for m in moves if m['choice']==choice))}。"+(reason.strip() or "我还拿不准，想先试试。"),"decision")
                    lesson["result"]=generate_review(lesson,mode)
                    keep_review(lesson);st.rerun()
                except (RuntimeError,ValueError) as exc:
                    lesson["review_error"]=str(exc)
                    if hasattr(exc,"trace"):
                        lesson["failed_agent_trace"]=exc.trace
                        lesson["failed_agent_metadata"]=getattr(exc,"metadata",{})
                    st.rerun()
        elif "result" not in lesson:
            st.caption("已完成出招，复盘暂时没有生成。")
            if lesson.get("review_error"):st.error(lesson["review_error"])
            if st.button("重试复盘",type="primary",width="stretch"):
                try:
                    lesson["result"]=generate_review(lesson,mode)
                    keep_review(lesson);st.rerun()
                except (RuntimeError,ValueError) as exc:lesson["review_error"]=str(exc);st.error(str(exc))
        elif "quiz_result" not in lesson:
            quiz=lesson["quiz"]
            focus=lesson["result"]["metadata"].get("agent",{}).get("practice_plan")
            if focus:st.caption("这次先练："+focus["focus"])
            st.caption("比较规则：平均预计伤害 × 标称命中率")
            if lesson.get("quiz_assisted"):st.caption("已使用提示，本题只作为练习。")
            with st.form("quiz_"+lesson["id"]):
                prediction=st.selectbox("你会选哪招",[m["choice"] for m in quiz["options"]],format_func=lambda c:name(next(m["name"] for m in quiz["options"] if m["choice"]==c)))
                submitted=st.form_submit_button("确认判断",type="primary",width="stretch")
            if submitted:
                correct=prediction==quiz["correct_choice"]
                lesson["quiz_result"]={"correct":correct,"selected":prediction}
                store.add(lesson["id"]+":quiz","quiz",{"topic":quiz["title"],"correct":correct,"selected":prediction,"expected":quiz["correct_choice"],"mode":lesson["result"]["metadata"]["mode"],"assisted":lesson.get("quiz_assisted",False)})
                message(lesson,"user","新场景我选"+name(next(m["name"] for m in quiz["options"] if m["choice"]==prediction))+"。","quiz")
                best=name(next(m["name"] for m in quiz["options"] if m["choice"]==quiz["correct_choice"]))
                message(lesson,"assistant",("这次判断和计算一致。" if correct else f"按这次比较规则，{best}排在前面。")+"记住：一起比较伤害和命中率，不能只看威力。这不是整场最优策略的证明。","quiz")
                st.rerun()
        else:
            st.caption("判断与计算一致。" if lesson["quiz_result"]["correct"] else "发现了一个还可以练习的点。")
            if st.button("再练一局",type="primary",width="stretch"):
                q=lesson["quiz"]
                st.session_state["lesson"]=new_lesson(q["scenario"],q["seed"]);st.rerun()
        with st.expander("规则与招式说明"):
            st.caption("固定的50级单挑教学局，采用宝可梦第九世代公开规则；不代表洛克王国实际机制。双方配置固定，对手从可用招式中随机选招。")
            st.markdown("**先分清三件事**")
            st.write("① 属性是克制关系：看招式属性对对手属性的倍率；×2表示属性克制，×0.5表示抵抗，×0表示属性免疫。本系加成是另一项：招式属性与自己相同，通常还有伤害加成。")
            st.write("② 防御与特防不同：物理招式看自己的攻击和对方的防御；特殊招式看自己的特攻和对方的特防。威力是招式参数，不等于扣掉的生命值。")
            st.write("③ 命中和先后手不同：标称命中率决定能否命中的基础概率；通常先比招式优先度，同优先度再比速度，其他机制也可能影响顺序。")
            snapshot=lesson["quiz"]["snapshot"] if "result" in lesson else before
            active_quiz="result" in lesson and "quiz_result" not in lesson
            st.markdown("**这组招式分别怎么算**")
            st.caption("当前新场景小测的数据。" if "result" in lesson else "本次出招前的数据；不是出招后的剩余生命。")
            st.table(move_rows(sorted(snapshot["advice"],key=lambda m:m["choice"])))
            for row in matchup_rows(snapshot,show_damage=not active_quiz):
                st.write(f"**{row['招式']} · {row['类别']}**")
                st.caption(f"对照对方{row['对方抵挡能力']}；属性倍率{row['属性倍率']}；本系加成：{row['本系加成']}。"+
                           (f"命中时伤害 {row['命中时伤害']}。" if "命中时伤害" in row else ""))
            if active_quiz:st.caption("先自己判断，小测提交前不在这里展示伤害结果或排序。")
            for label,mon in [("你的伙伴",snapshot["player"]),("对手",snapshot["opponent"])]:
                st.caption(label+"："+name(mon["name"])+" · 面板能力（不含能力等级变化）")
                st.table(stat_rows(mon))
            st.markdown("**教练的比较标准**")
            st.write("伤害区间由现成计算器按双方配置计算，已计入属性、攻防等机制，不能再乘一次属性倍率。当前教学排序＝伤害区间两端的均值 × 标称命中率。")
            st.caption("这是直接伤害的简化比较，不是胜率或整场最优解；没有把先手、控制、附加效果和对手策略的价值算进分值。伤害区间指命中且没有击中要害时的计算值；实际结算以对战引擎为准。")
            if "after" in lesson:
                for line in event_lines(lesson["after"]["rounds"][-1]["events"]):st.caption(line)
            if "result" in lesson:
                answer=lesson["result"]["answer"]
                st.caption("上一回合的复盘依据")
                st.write(dialogue(answer["explanation"]["text"]))
                chosen=next(m for m in before["advice"] if m["choice"]==answer["suggested_choice"])
                st.caption(calculation(chosen))
                st.caption(dialogue(answer["uncertainty"]))

with conversation:
    st.html('<div class="lolo-label">和 洛 洛 说 说</div>')
    transcript=st.container(height=390,border=False,autoscroll=True)
    with transcript:
        if not lesson["messages"]:
            with st.chat_message("assistant"):
                st.write("我在。拿不准就问我，想先自己试一招也可以。")
        for item in lesson["messages"][-8:]:
            with st.chat_message(item["speaker"]):
                st.write(dialogue(item["text"],allowed_identifiers=[ready.model] if ready else []))
                if item.get("tool_summary"):st.caption(item["tool_summary"])
    typed=st.chat_input("怎么选、为什么，或只是聊聊……",max_chars=500,key="coach_query")
    if typed:
        history=dialogue_history(lesson)
        message(lesson,"user",typed)
        # While the transfer question is active, chat must see that scene rather than the old fight.
        selection=select_context(lesson,typed)
        view=None
        if mode=='live':
            with transcript:
                with st.chat_message('user'):st.write(typed)
                view=LiveOutput(st.chat_message('assistant'),[ready.model] if ready else [])
        try:
            reply=coach_reply(typed,selection.battle,store.summary(),history,mode,lesson_context=selection.lesson_context,practice_result=selection.practice_result,**({'on_event':view} if view else {}))
            reply["routing"].update(context_source=selection.source,context_reason=selection.reason)
            lesson["last_agent_trace"]=reply["metadata"].get("agent")
            lesson["last_routing"]=reply["routing"]
            if selection.source=="transfer_quiz" and reply["role"] in {"军师","老师"}:lesson["quiz_assisted"]=True
            summary=branch_summary(reply["metadata"])
            visible_reply=reply["reply"]+("\n\n"+summary if summary else "")
            if view:reply['metadata']['stream']=view.complete(visible_reply)
            message(lesson,"assistant",reply["reply"],role=reply["role"],tool_summary=summary)
            store.add(uuid.uuid4().hex,"chat",{"topic":"和洛洛聊聊","user":typed,"assistant":visible_reply,"role":reply["role"],"mode":mode,"metadata":reply["metadata"],"routing":reply["routing"],"evidence_ids":reply["evidence_ids"]})
            lesson.pop("chat_error",None);st.rerun()
        except (ValueError,RuntimeError) as exc:
            if view:view.reject()
            lesson["chat_error"]=str(exc)
            if hasattr(exc,"trace"):
                lesson["failed_agent_trace"]=exc.trace
                lesson["failed_agent_metadata"]=getattr(exc,"metadata",{})
            st.rerun()
    if lesson.get("chat_error"):st.error(lesson["chat_error"]+" 可在输入框重新提问。")

st.html('<div class="footer-note">宠物对战教学原型 · 宝可梦公开规则 · 学习记录保存在本机</div>')
