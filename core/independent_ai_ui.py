"""Isolated beta UI; same content in Dashboard and Mobile."""
from html import escape
import json
from .independent_ai import KEY,resolve,from_result,digest
from .independent_ai_odds import provider,evaluate_history

def markup(value):
    e=lambda x:escape(str(x))
    if value.get('status') not in ('reference',):return '<p>'+e(value.get('reason','独立AIは未生成です'))+'</p>'
    parts=['<div class="independent-ai"><p><b>試験版・参考評価</b>　予測信頼度：'+e(value['confidence'])+'</p>',
           '<p>'+e(value['calibration_status'])+'。利益優位性は未確認です。</p>']
    if value.get('origin')=='current_reference':parts.append('<p>保存当時の予想ではなく、現在モデルによる参考生成です。</p>')
    parts.append('<div style="overflow-x:auto"><table style="width:100%;font-size:0.9rem"><thead><tr><th>馬</th><th>勝利</th><th>複勝</th></tr></thead><tbody>')
    for h in value['horses']:
        parts.append(f"<tr><td>{h['horse_no']} {e(h['name'])}</td><td>{h['win']*100:.1f}%</td><td>{h['place']*100:.1f}%</td></tr>")
    parts.append('</tbody></table></div><p>AI注目馬（正式印とは独立）</p>')
    for h in value['horses'][:3]:
        parts.append(f"<p><b>{h['horse_no']} {e(h['name'])}</b><br>"+e('／'.join(h['reasons']) or '明確なプラス寄与はありません')+'<br>'+e('／'.join(h['cautions']) or 'モデル外の不確実性があります')+f"<br>勝利のモデル間範囲 {h['win_range'][0]*100:.1f}〜{h['win_range'][1]*100:.1f}%</p>")
    parts.append('<p>ワイド参考候補</p>')
    for p in value['wide'][:3]:
        parts.append('<p>'+e('－'.join(map(str,p['horses'])))+f"：{p['probability']*100:.1f}%（モデル間 {p['range'][0]*100:.1f}〜{p['range'][1]*100:.1f}%）</p>")
    parts.append('<p>'+e(value['wide_definition'])+'。'+e(value['uncertainty_definition'])+'</p></div>')
    return ''.join(parts)

def render(result):
    import streamlit as st
    if not from_result(result)['horses']:return
    import inspect
    expander_args={'key':'independent_ai_section_'+digest(from_result(result))} if 'key' in inspect.signature(st.expander).parameters else {}
    with st.expander('AI独立判断（試験版）',expanded=False,**expander_args):
        try:
            cache_key="independent_ai_reference_"+digest(from_result(result))
            if KEY in (result.debug_info or {}):value=resolve(result)
            else:
                if cache_key not in st.session_state:st.session_state[cache_key]=resolve(result)
                value=st.session_state[cache_key]
            from .independent_ai_commentary import build,context,decision_text
            commentary=value.get('commentary') or build(value,context(result))
            st.markdown(markup(value),unsafe_allow_html=True)
            st.markdown('**新AIのレース考察**')
            if not value.get('commentary'):st.caption('旧独立予測の保存値に基づく参考考察。元の保存文は変更しません。')
            for paragraph in commentary['paragraphs']:st.write(paragraph)
            if value.get('status')!='reference':return
            try:config=dict(st.secrets.get('independent_ai_odds',{}))
            except Exception:config={}
            try:p=provider(config)
            except ValueError:
                p=provider();st.caption('オッズ接続設定を確認できません。管理者による確認が必要です。')
            state_key='independent_ai_price_'+str(value.get('race_id'))+'_'+value.get('input_hash','')
            history_key=state_key+'_history'
            from .independent_ai_odds_io import KEY as ODDS_KEY,merge,import_file,attach_archive
            if history_key not in st.session_state:st.session_state[history_key]=merge([], (result.debug_info or {}).get(ODDS_KEY,[]),value)
            if st.button('最新オッズ更新',key=state_key+'_button',disabled=not p.available):
                try:
                    fetched=p.fetch(value['race_id']);st.session_state[state_key]=fetched
                    st.session_state[history_key]=merge(st.session_state[history_key],[fetched],value)
                except Exception:st.warning('オッズ取得に失敗しました。既存予想と独立AIの参考予測は利用できます。')
            upload=st.file_uploader('オッズHTML・価格履歴JSONを取り込む',type=['html','htm','json'],key=state_key+'_html')
            st.caption('ご自身で保存したHTMLをこのセッション内で解析します。予想オッズ・価格時刻不明・未発売は最新扱いしません。新聞に複勝・ワイドがなければ補完しません。')
            if upload is not None and st.button('オッズだけ取り込む',key=state_key+'_import'):
                try:
                    st.session_state.pop(state_key+'_archive_bytes',None)
                    imported=import_file(upload.getvalue(),upload.name,value)
                    st.session_state[history_key]=merge(st.session_state[history_key],imported,value)
                    st.success(f'価格履歴 {len(st.session_state[history_key])}件。予測は再計算していません。')
                except ValueError as exc:st.warning(str(exc))
            from .independent_ai_manual_odds import render as manual_odds
            manual=manual_odds(value,state_key+'_manual')
            if manual:
                st.session_state[history_key]=merge(st.session_state[history_key],[manual],value)
                st.session_state.pop(state_key+'_archive_bytes',None)
            history=st.session_state[history_key]
            quote=history[-1] if history else None
            decision=evaluate_history(value,history)
            decision['commentary']=commentary
            decision['commentary_decision']=decision_text(value,decision)
            st.info(decision['reason'])
            for line in decision['commentary_decision'][1:]:st.write(line)
            for ticket in decision['candidates']:
                st.write(f"仮想購入候補：{ticket['kind']} {'－'.join(map(str,ticket['horses']))} / 仮想100円 / 参考払戻倍率 {ticket['reference_gross_return']:.2f}")
            st.caption('実証済み推奨：なし。実購入は行いません。')
            if quote:st.caption('提供元：'+str(quote.get('source',''))+' ／ 価格時刻：'+str(quote.get('observed_at','')))
            if quote and not quote.get('prices'):st.warning('レース識別成功・有効発売オッズ0件。空欄は補完しません。')
            if quote and quote.get('missing_kinds'):st.caption('未取得券種：'+'・'.join(quote['missing_kinds']))
            if quote and quote.get('prices'):
                st.caption('取込価格（鮮度確認とは別）')
                for row in quote['prices'][:6]:st.write(f"{row['kind']} {'－'.join(map(str,row['horses']))}：{row['low']:g}〜{row['high']:g}倍")
            if decision['price_evaluations']:
                for row in decision['price_evaluations'][:6]:
                    st.write(f"{row['kind']} {'－'.join(map(str,row['horses']))}：オッズ {row['odds_low']:g}〜{row['odds_high']:g} / 参考払戻倍率 {row['reference_gross_return']:.2f}（未校正なら期待利益の根拠にはできません）")
            from .independent_ai_html_odds import saved_odds
            export=dict(prediction=value,virtual_decision=decision,original_saved_odds=saved_odds(result),odds_history=st.session_state.get(history_key,[]))
            st.download_button('独立AIの予測・価格判断を保存',json.dumps(export,ensure_ascii=False,indent=2).encode('utf-8'),
                file_name=f"independent_ai_{value.get('race_id','race')}.json",mime='application/json',key=state_key+'_download')
            with st.expander('価格履歴を.keibaのコピーに関連付けて保存'):
                archive=st.file_uploader('元の.keibaを選択',key=state_key+'_archive')
                if archive is not None and st.button('価格履歴付きコピーを作る',key=state_key+'_archive_build'):
                    try:
                        st.session_state.pop(state_key+'_archive_bytes',None)
                        st.session_state[state_key+'_archive_bytes']=attach_archive(archive.getvalue(),value,history)
                    except ValueError as exc:st.warning(str(exc))
                if state_key+'_archive_bytes' in st.session_state:
                    st.download_button('価格履歴付き.keibaを保存',st.session_state[state_key+'_archive_bytes'],file_name=f"{value['race_id']}_with_odds.keiba",key=state_key+'_archive_download')
                st.caption('元ファイル・保存済み予想は変更せず、価格履歴だけを追加したコピーを作成します。')
            from .independent_ai_review_ui import render as render_review
            render_review(state_key)
            from .independent_ai_registry import freeze
            try:
                frozen=freeze(value,decision)
                st.download_button('未来検証用に発走前固定して保存',json.dumps(frozen,ensure_ascii=False,indent=2).encode('utf-8'),
                    file_name=f"independent_ai_fixed_{value['race_id']}.json",mime='application/json',key=state_key+'_freeze')
                st.caption('ダウンロードした固定記録を保管してください。Cloudの一時領域だけには保存しません。')
            except ValueError as exc:st.caption('未来検証への登録：'+str(exc))
        except Exception:
            st.warning('独立AIの表示を一時的に利用できません。既存予想には影響しません。')
