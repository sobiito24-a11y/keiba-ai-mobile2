"""Read-only access to the existing saved prediction, without independent AI UI."""
def render_saved_game(render_result):
    import streamlit as st
    from .independent_ai_odds_io import read_archive, restore_race
    with st.expander('保存した予想を開く', expanded=False):
        uploaded=st.file_uploader('予想データ（.keiba／研究データ付きZIP）',key='game_archive_upload')
        if uploaded is None:
            st.session_state.pop('research_loaded',None)
            return False
        try:
            from .research_bundle import attach_upload
            _,event=attach_upload(uploaded.getvalue(),st.session_state,allow_local=False)
            races=event['races']
            if not races:
                st.info('保存レースがありません。');return False
            index=st.selectbox('表示するレース',range(len(races)),format_func=lambda i:str(races[i].get('race_id',''))+' '+str(races[i].get('race_name','')),key='game_archive_race')
            result=restore_race(races[index])
        except (ValueError,TypeError,KeyError) as exc:
            st.error(str(exc));return False
    render_result(result)
    return True
