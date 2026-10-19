"""Explicit portable research import; no local DB or network required on mobile."""
import hashlib,json
from .new_ai_research import digest,VERSION

def validate(data,keiba_bytes):
    from .research_bundle import event_bytes,validate_envelope
    event=event_bytes(keiba_bytes)
    return validate_envelope(data,hashlib.sha256(keiba_bytes).hexdigest(),{r['race_id']:r for r in event['races']})

def upload(race_key):
    import streamlit as st
    loaded=st.session_state.get('research_loaded',{})
    automatic=loaded.get('reports',{}).get(race_key)
    with st.expander('詳細設定・研究JSONの手動復旧',expanded=False):
        st.caption('研究JSONと、その計算に使った元.keibaを選択してください。正式予想は変更しません。')
        j=st.file_uploader('研究JSON',type=['json'],key='research_json_'+race_key)
        k=st.file_uploader('照合用の元.keiba',type=['keiba'],key='research_keiba_'+race_key)
        if j is not None and k is not None:
            try:
                f=validate(j.getvalue(),k.getvalue())
                if loaded and f['keiba_sha256']!=hashlib.sha256(loaded['original']).hexdigest():raise ValueError('読み込み中の予想データと不一致')
                if f['race_id']!=race_key:raise ValueError('表示レースと研究JSONのレースID不一致')
                st.success('研究JSON・元データハッシュ・モデル版を照合しました')
                return f
            except Exception as exc:st.error(str(exc))
    return automatic
