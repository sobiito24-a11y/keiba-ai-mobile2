"""Manual transcription UI, no remote collection or timestamp inference."""
def render(prediction,key):
    import streamlit as st
    from datetime import datetime
    from .independent_ai import JST,number
    from .independent_ai_odds_io import validate
    with st.expander('ブラウザで確認した価格を手入力'):
        st.caption('単勝・複勝・ワイドの表示価格を転記できます。サイトの更新日時が不明なら空欄のままにしてください。入力値・時刻は利用者の申告であり、自動取得による証明ではありません。')
        kind=st.selectbox('券種',['win','place','wide'],format_func=lambda v:{'win':'単勝','place':'複勝','wide':'ワイド'}[v],key=key+'_kind')
        horses={h['horse_no']:h['name'] for h in prediction['horses']}
        n1=st.selectbox('馬',list(horses),format_func=lambda n:f'{n} {horses[n]}',key=key+'_n1')
        n2=st.selectbox('相手馬',[n for n in horses if n!=n1],format_func=lambda n:f'{n} {horses[n]}',key=key+'_n2') if kind=='wide' else None
        lo=st.text_input('オッズ下限（単勝は表示値）',key=key+'_low')
        hi=st.text_input('オッズ上限（単勝は空欄可）',key=key+'_high')
        source=st.text_input('確認したページURL',key=key+'_source')
        observed=st.text_input('サイトの更新日時（例 2026-10-13T14:30:00+09:00、不明なら空欄）',key=key+'_observed')
        if st.button('この価格を履歴に追加',key=key+'_submit'):
            try:
                from bs4 import BeautifulSoup
                from html import escape
                from .independent_ai_html_odds import identity
                from .independent_ai_odds import timestamp
                rid,mode,_=identity(BeautifulSoup('<link rel="canonical" href="'+escape(source,quote=True)+'">','html.parser'))
                if observed and not timestamp(observed):raise ValueError('更新日時はタイムゾーン付き日時で入力してください')
                ns=[n1,n2] if n2 else [n1]
                q=dict(race_id=rid,mode=mode,source='user_transcribed_browser',source_url=source,
                    authorization_reference='user private transcription; no redistribution permission',
                    timestamp_evidence='user reported site update time',received_at=datetime.now(JST).isoformat(),observed_at=observed or None,
                    identities={str(n):horses[n] for n in ns},prices=[dict(kind=kind,horses=ns,low=number(lo),high=number(hi or lo) if kind=='win' else number(hi))])
                return validate(q,prediction)
            except ValueError as exc:st.warning(str(exc))
    return None
