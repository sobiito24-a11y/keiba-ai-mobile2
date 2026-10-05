"""One-way snapshot and UI boundary for evidence badges / reconsideration."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from html import escape
from .condition_material_v2 import key_for as condition_key, evaluate_condition_materials, unique_reasons


def key_for(mode):
    return mode + '_material_reconsideration_shadow'


def attach_material_reconsideration(result):
    mode=result.race_mode;key=key_for(mode)
    if mode not in ('jra','nar') or key in (result.debug_info or {}) or getattr(result,'_jra_snapshot_restored',False) or getattr(result,'_material_snapshot_restored',False):
        return result
    result.debug_info={**(result.debug_info or {}),key:_evaluate_materials(result)}
    ensure_condition_materials(result)
    return result


def _evaluate_materials(result):
    """Only the material layer. Never call formal producers or other Shadows."""
    mode=result.race_mode
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
    return payload


def current_jst_date():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def ensure_current_material_reference(result, *, today=None):
    """Fill today's missing diagnostics from frozen inputs, never historical forecasts.

    Original prediction time must still precede post time (input adapter gate).
    The evaluation time is recorded separately, even when read after the race.
    """
    mode=result.race_mode
    if mode not in ('jra','nar'):
        return result
    info=result.race_info or {}
    day=str(info.get('race_date') or info.get('date') or '')[:10]
    if day != (str(today) if today is not None else current_jst_date()):
        return result
    key=key_for(mode)
    saved=(result.debug_info or {}).get(key)
    if isinstance(saved,dict) and (saved.get('horses') or saved.get('calculation_context')=='same_day_saved_inputs_reference'):
        ensure_condition_materials(result)
        return result
    payload=_evaluate_materials(result)
    payload.update(calculation_context='same_day_saved_inputs_reference',
                   source_prediction_created_at=result.created_at,
                   source_race_date=day, reference_only=True)
    if saved is not None:
        payload['previous_uncomputed']=deepcopy(saved)
    result.debug_info={**(result.debug_info or {}),key:payload}
    ensure_condition_materials(result)
    return result


def ensure_condition_materials(result):
    """Version B from frozen A inputs; never overwrite A or read new race features."""
    mode=result.race_mode
    key=condition_key(mode)
    debug=result.debug_info or {}
    if mode not in ('jra','nar') or key in debug:
        return result
    saved=debug.get(key_for(mode))
    if not isinstance(saved,dict) or not saved.get('horses'):
        return result
    payload=evaluate_condition_materials(saved,mode)
    payload.update(evaluated_at=datetime.now(timezone.utc).isoformat(),
                   calculation_context='conditions_only_from_saved_material_inputs',
                   source_model_version=saved.get('model_version'),
                   source_evaluated_at=saved.get('evaluated_at'),
                   purpose='shadow_only_no_formal_feedback')
    result.debug_info={**debug,key:payload}
    return result


def display_material_payload(result):
    ensure_condition_materials(result)
    return (result.debug_info or {}).get(condition_key(result.race_mode)) or {}


def material_snapshot(result):
    return {key:deepcopy(result.debug_info[key])
            for key in (key_for(result.race_mode),condition_key(result.race_mode))
            if isinstance((result.debug_info or {}).get(key),dict)}


def saved_materials(result):
    payload=display_material_payload(result)
    return {str(h['horse_no']):h for h in payload.get('horses',[])}


def material_cell(horse,positive=True):
    if not horse:
        return '未計算'
    label=horse['good' if positive else 'concern']
    reasons=unique_reasons(horse['good_reasons' if positive else 'concern_reasons'])
    return label+' '+(' / '.join(reasons.values()) if reasons else '取得材料に該当なし')


def reconsideration_html(result):
    payload=display_material_payload(result)
    swap=payload.get('reconsideration')
    if not swap:
        return ''
    horses={str(h['horse_no']):h for h in payload.get('horses',[])}
    added=horses[swap['added']];removed=horses[swap['removed']]
    def esc(v):return escape(str(v))
    return ('<section class="top5-reconsideration" style="border:1px solid #94a3b855;border-radius:6px;padding:10px;font-size:13px;overflow-wrap:anywhere">'
            '<b>🔄 Top5再検討候補（研究・参考）</b><p>'+esc(added['horse_no']+' '+str(added['horse_name']))+
            '<br>今回プラス '+esc(material_cell(added))+'</p><p>比較対象：'+esc(removed['horse_no']+' '+str(removed['horse_name']))+
            '<br>今回注意 '+esc(material_cell(removed,False))+'</p><p>'+esc(added['horse_no'])+
            '番との比較材料です。正式Top5の変更・購入推奨ではありません。</p>'
            '<details><summary>Shadow Top5を見る</summary>'+esc(' / '.join(payload['shadow_top5']))+'</details></section>')


def render_reconsideration(result):
    html=reconsideration_html(result)
    if html:
        import streamlit as st
        st.markdown(html,unsafe_allow_html=True)
