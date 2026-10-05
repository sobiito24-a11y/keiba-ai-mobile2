"""One-way snapshot and UI boundary for evidence badges / reconsideration."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from html import escape


def key_for(mode):
    return mode + '_material_reconsideration_shadow'


def attach_material_reconsideration(result):
    mode=result.race_mode;key=key_for(mode)
    if mode not in ('jra','nar') or key in (result.debug_info or {}) or getattr(result,'_jra_snapshot_restored',False) or getattr(result,'_material_snapshot_restored',False):
        return result
    try:
        if mode=='nar':
            from .material_evidence_inputs import nar_material_inputs
            from .nar_material_evidence import evaluate_nar_materials
            data,error=nar_material_inputs(result)
            payload=evaluate_nar_materials(data) if data is not None else {'status':'uncomputed','reason':error,'horses':[]}
        else:
            from .jra_practical_inputs import practical_inputs
            from .jra_material_evidence import evaluate_jra_materials
            data=practical_inputs(result)
            payload=evaluate_jra_materials(data)
        if data is not None:
            payload['input_hash']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        payload['evaluated_at']=datetime.now(timezone.utc).isoformat()
        payload['purpose']='shadow_only_no_formal_feedback'
    except (ValueError,TypeError,KeyError) as exc:
        payload={'status':'input_error','reason':str(exc),'horses':[]}
    result.debug_info={**(result.debug_info or {}),key:payload}
    return result


def material_snapshot(result):
    key=key_for(result.race_mode);saved=(result.debug_info or {}).get(key)
    return {key:deepcopy(saved)} if isinstance(saved,dict) else {}


def saved_materials(result):
    payload=(result.debug_info or {}).get(key_for(result.race_mode)) or {}
    return {str(h['horse_no']):h for h in payload.get('horses',[])}


def material_cell(horse,positive=True):
    if not horse:
        return '未計算'
    label=horse['good' if positive else 'concern']
    reasons=horse['good_reasons' if positive else 'concern_reasons']
    return label+' '+(' / '.join(reasons.values()) if reasons else '取得材料に該当なし')


def reconsideration_html(result):
    payload=(result.debug_info or {}).get(key_for(result.race_mode)) or {}
    swap=payload.get('reconsideration')
    if not swap:
        return ''
    horses={str(h['horse_no']):h for h in payload.get('horses',[])}
    added=horses[swap['added']];removed=horses[swap['removed']]
    def esc(v):return escape(str(v))
    return ('<section class="top5-reconsideration" style="border:1px solid #94a3b855;border-radius:6px;padding:10px;font-size:13px;overflow-wrap:anywhere">'
            '<b>🔄 Top5再検討候補（研究・参考）</b><p>'+esc(added['horse_no']+' '+str(added['horse_name']))+
            '<br>好材料 '+esc(material_cell(added))+'</p><p>比較対象：'+esc(removed['horse_no']+' '+str(removed['horse_name']))+
            '<br>不安材料 '+esc(material_cell(removed,False))+'</p><p>'+esc(added['horse_no'])+
            '番との比較材料です。正式Top5の変更・購入推奨ではありません。</p>'
            '<details><summary>Shadow Top5を見る</summary>'+esc(' / '.join(payload['shadow_top5']))+'</details></section>')


def render_reconsideration(result):
    html=reconsideration_html(result)
    if html:
        import streamlit as st
        st.markdown(html,unsafe_allow_html=True)
