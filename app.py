import streamlit as st

pages = [
    st.Page("pages/0_AI教练.py", title="洛洛教练", icon="🦊", default=True),
    st.Page("pages/1_宠物对战.py", title="自由对战", icon="⚔️", url_path="battle"),
    st.Page("pages/2_训练计划.py", title="早期训练计划", icon="📝", url_path="plan"),
]
st.navigation(pages, position="hidden").run()
