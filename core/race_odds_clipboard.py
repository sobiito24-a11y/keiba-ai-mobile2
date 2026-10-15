"""User-initiated paste only; validate browser bytes again on the server."""
import base64
import binascii
from pathlib import Path
from .race_odds_screenshot import image_data


def decode_images(value):
    if value is None: return []
    if not isinstance(value, dict) or not isinstance(value.get('images'), list):
        raise ValueError('貼り付け画像の形式が不正です')
    if len(value['images'])>5: raise ValueError('画像は最大5枚です')
    files=[]
    for index,item in enumerate(value['images']):
        if not isinstance(item,dict): raise ValueError('貼り付け画像が不正です')
        mime=item.get('mime');data=item.get('base64')
        if mime not in ('image/png','image/jpeg','image/webp') or not isinstance(data,str) or len(data)>20_000_000:
            raise ValueError('PNG・JPEG・WebP、1枚15MB以下にしてください')
        try: raw=base64.b64decode(data,validate=True)
        except (ValueError,binascii.Error): raise ValueError('貼り付け画像を復号できません') from None
        image_data(raw)
        files.append((f'貼付{index+1}.'+{'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime],raw))
    return files


def render(key):
    import streamlit as st
    import streamlit.components.v1 as components
    component=components.declare_component('race_odds_clipboard',path=str(Path(__file__).with_name('race_odds_clipboard_assets')))
    value=component(key=key,default=None,initial_images=st.session_state.get(key+'_last',[]))
    files=decode_images(value)
    if value is not None: st.session_state[key+'_last']=value['images']
    return files
