import streamlit as st

from rococoach.coach import GOALS, build_plan
from rococoach.config import get_mode

st.set_page_config(page_title="洛洛教练 · 智能教练", page_icon="🧭", layout="centered")
st.title("🧭 洛洛教练")
st.caption("面向《洛克王国：世界》的 智能教练 面试原型 · 非官方项目")
st.markdown("[进入宠物对战：军师 · 陪练 · 老师](/battle)")
try:
    get_mode()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.info("当前为离线规则演示，无需 API 密钥。训练建议为通用练习框架，不包含已核实的游戏机制或数值。")
with st.sidebar:
    st.header("今天练什么？")
    st.write("1. 明确目标\n2. 完成一次练习\n3. 留下可验证的复盘")
    st.caption("三天开发：跑通流程 → 接入资料与模型 → 评测和演示")

with st.form("coach_form"):
    goal = st.selectbox("训练目标", GOALS)
    minutes = st.slider("可用时间（分钟）", 10, 120, 30, 5)
    obstacle = st.text_area("你现在卡在哪里？", placeholder="例如：每次对战结束，我不知道应该复盘哪一步。", max_chars=1000)
    submitted = st.form_submit_button("生成训练计划", type="primary")

if submitted:
    try:
        plan = build_plan(goal, minutes, obstacle)
    except ValueError as exc:
        st.warning(str(exc))
    else:
        st.session_state["plan"] = plan.markdown()
        st.session_state["reflection"] = ""

if "plan" in st.session_state:
    st.markdown(st.session_state["plan"])
    reflection = st.text_area("练习后的复盘", key="reflection", placeholder="实际做了什么？结果如何？下次改变什么？", max_chars=3000)
    report = st.session_state["plan"] + "\n\n## 我的复盘\n\n" + (reflection or "尚未填写")
    st.download_button("下载计划与复盘", report, "rococoach-plan.md", mime="text/markdown")
    st.caption("内容仅保留在当前网页会话中，刷新或关闭前请下载保存。")
