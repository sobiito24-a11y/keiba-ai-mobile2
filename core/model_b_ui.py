"""A/B UI projection. Never mutates model A, buying inputs, or saved results."""
from copy import deepcopy
from .model_b import resolve
from .prediction_table_ui import number

def project(view, report):
    if report.get('status')!='ready':return deepcopy(view)
    by={h['no']:h for h in report['horses']}
    if set(by)!={h['no'] for h in view}:raise ValueError('研究Bの馬番が一致しません')
    output=deepcopy(view)
    for h in output:
        b=by[h['no']]
        h['model_a']=dict(score=h['score'],rank=h['rank'],mark=h['mark'])
        h['model_b']=deepcopy(b);h['active_model']='B'
        h['score']=f"{b['score']:.3f}";h['internal_score']=b['score'];h['rank']=str(b['rank']);h['score_label']='研究B総合スコア'
        h['formal_member']=b['rank']<=5;h['member']=h['formal_member']
        h['mark']=b['mark'] or (h['mark'] if h['mark']=='✓' else '—')
        h['candidate_group']='研究B Top5' if h['formal_member'] else 'A由来参考✓' if h['mark']=='✓' else '無印'
        if not h['formal_member'] and (h['model_a']['mark'] not in ('','—','-') or h.get('additional_reference')):
            h['additional_reference']=True
            h['reference_facts']=list(h.get('reference_facts') or [])+['A由来候補を保持（B本印とは別）']
        h['mark_reasons']=['研究B '+report['model_version']+'（4角補正なし）']
        for k in ('focus_label','focus_reason','display_scale','reference_score'):h.pop(k,None)
        h['sort_values'].update(score=b['score'],mark=b['rank']-1 if b['rank']<=5 else 15 if h['mark']=='✓' else 37)
    return output

def render(view, race_id, result=None):
    import streamlit as st
    mode=view[0]['mode'] if view else 'jra'
    report=resolve(result) if result is not None else dict(status='unavailable',fallback_reason='元の予想データ未取得')
    if report.get('status')=='ready':
        st.caption('研究B：全'+str(len(report['horses']))+'頭を計算済み / '+report['model_version']+' / 係数ID '+report['config_sha256'][:12])
    # No unverified model is made the default merely because it can compute.
    options=['現行A：従来の正式評価','研究B：4角補正なし']
    selected=st.radio('表示モデル',options,horizontal=True,key='prediction_model_'+race_id,index=1 if report.get('default_allowed') else 0)
    if selected==options[1] and report['status']!='ready':
        st.warning(report['fallback_reason']+'。現行Aへフォールバックしています。')
    elif selected==options[1]:
        st.caption('過去日の再計算は探索用です。学習終了日：'+str(report.get('train_end','不明'))+'。時系列未使用データでの最終性能は未検証です。')
        st.caption('研究B '+report['model_version']+' / '+report['config'].get('coefficient_status','固定係数・探索研究')+'。評価点は勝率ではありません。買い目判断は従来Aのままです。')
        return project(view,report)
    else:st.caption('現行Aを表示中。研究Bの入力または凍結モデルが不足しています。' if report['status']!='ready' else '現行Aを表示中。保存済み正式値を維持します。')
    return view
