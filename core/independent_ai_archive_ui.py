"""Read-only saved race viewer for the independent AI, also usable by acquisition tools."""
def render_archive_panel():
    import streamlit as st
    from .independent_ai_odds_io import read_archive,restore_race
    from .independent_ai_ui import render
    with st.expander('保存.keibaからAI独立判断・オッズを開く'):
        uploaded=st.file_uploader('保存レースを選択',key='independent_archive_upload')
        if uploaded is None:return
        try:
            _,event=read_archive(uploaded.getvalue())
            races=event['races']
            index=st.selectbox('独立AIの対象レース',range(len(races)),format_func=lambda i: str(races[i].get('race_id'))+' '+str(races[i].get('race_name','')),key='independent_archive_race')
            race=races[index]
            result=restore_race(race)
            st.caption('保存済み正式予想は再計算しません。独立AI未保存の場合は現行モデルの参考生成です。')
            render(result)
        except (ValueError,TypeError,KeyError) as exc:st.error(str(exc))
