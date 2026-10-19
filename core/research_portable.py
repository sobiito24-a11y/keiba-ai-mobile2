"""Explicit portable research import; no local DB or network required on mobile."""
import hashlib,json
from .new_ai_research import digest,VERSION

def validate(data,keiba_bytes):
    envelope=json.loads(data);payload=envelope['payload']
    if digest(payload)!=envelope['payload_sha256']:raise ValueError('研究JSONハッシュ不一致')
    if payload['keiba_sha256']!=hashlib.sha256(keiba_bytes).hexdigest():raise ValueError('元.keibaハッシュ不一致')
    if payload['version']!=VERSION:raise ValueError('未対応モデル版')
    if payload['config_sha256']!=digest(payload['config']):raise ValueError('係数設定ハッシュ不一致')
    return payload

def upload(race_key):
    import streamlit as st
    with st.expander('研究JSONを読み込む（PC・iPhone共通）',expanded=True):
        st.caption('研究JSONと、その計算に使った元.keibaを選択してください。正式予想は変更しません。')
        j=st.file_uploader('研究JSON',type=['json'],key='research_json_'+race_key)
        k=st.file_uploader('照合用の元.keiba',type=['keiba'],key='research_keiba_'+race_key)
        if j is not None and k is not None:
            try:
                f=validate(j.getvalue(),k.getvalue())
                if f['race_id']!=race_key:raise ValueError('表示レースと研究JSONのレースID不一致')
                st.success('研究JSON・元データハッシュ・モデル版を照合しました')
                return f
            except Exception as exc:st.error(str(exc))
    return None
