"""Race-wide price controls, independent of prediction/model execution."""
from datetime import datetime
import json
from . import race_odds as odds


def render(result, view):
    import streamlit as st
    from html import escape
    def caption(value):
        st.markdown('<p style="color:#bbcee5;font-size:13px;line-height:1.5;overflow-wrap:anywhere">'+escape(str(value))+'</p>', unsafe_allow_html=True)
    from .independent_ai_odds import provider
    try:
        identity = odds.identity_from_result(result)
        initial = odds.state_for(result)
    except (ValueError, TypeError, KeyError):
        caption('オッズ更新不可：レース・出走馬情報を照合できません。保存時表示を維持します。')
        return view
    key = 'race_prices_' + odds.digest(dict(identity=identity, saved=initial))
    state = st.session_state.setdefault(key, initial)
    try:
        config = dict(st.secrets.get('race_odds', st.secrets.get('independent_ai_odds', {})))
    except Exception:
        config = {}
    try:
        connection = provider(config)
    except (ValueError, TypeError):
        connection = provider()
    st.markdown('#### オッズ')
    if getattr(result, '_race_odds_error', None): st.warning(result._race_odds_error)
    if st.button('オッズ更新', key=key+'_fetch', disabled=not connection.available):
        last = st.session_state.get(key+'_last_request')
        now = datetime.now(odds.JST)
        if last and (now-last).total_seconds() < 30:
            st.session_state[key+'_status'] = '連続更新を抑止しました。30秒後に再試行できます。'
        else:
            st.session_state[key+'_last_request'] = now
            try:
                with st.spinner('全頭のオッズを照合中…'):
                    quote = odds.validate(connection.fetch(identity['race_id']), identity)
                    quote['acquisition_method'] = 'authorized_json'
                    history = odds.merge(state['history'], [quote], identity)
                count = len(history)-len(state['history'])
                state['history'] = history
                st.session_state[key+'_status'] = (
                    f"取得：{quote['horse_count']}／{quote['expected_horses']}頭。" +
                    ('有効価格未取得。' if not quote['prices'] else '全頭対象の照合完了。') +
                    ('同一観測のため履歴追加なし。' if not count else ''))
            except Exception:
                # Never expose authentication/endpoint details in a user-facing error.
                st.session_state[key+'_status'] = '更新失敗：現在オッズ取得不可。以前の履歴と保存時オッズは保持しています。'
    if not connection.available:
        caption('オンライン更新は未設定です。取得・転送・表示が許諾された提供元の接続設定が必要です。HTML・JSONを一括取込できます。')
    from .race_odds_screenshot_ui import render as render_screenshot
    render_screenshot(identity, state, key)
    with st.expander('オッズファイルを一括取込・履歴を保存', expanded=False):
        files = st.file_uploader('同じレースのオッズHTML／JSON', type=['html','htm','json'],
                                 accept_multiple_files=True, key=key+'_files')
        if st.button('全頭分をまとめて取り込む', disabled=not files, key=key+'_import'):
            try:
                incoming = odds.import_files([(f.name, f.getvalue()) for f in files], identity)
                history = odds.merge(state['history'], incoming, identity)
                added = len(history)-len(state['history'])
                state['history'] = history
                st.session_state[key+'_status'] = f'照合済み観測を{added}件追加。有効価格なしの観測は未取得として記録します。'
            except (ValueError, TypeError, KeyError, UnicodeError):
                st.session_state[key+'_status'] = '取込失敗：レースID・馬番・馬名・価格・日時形式を確認してください。全ファイルの反映を中止しました。'
        caption('セッション内の履歴はCloudへ永続保存されません。必要な履歴を含むコピーをダウンロードしてください。元ファイルは上書きしません。')
        source = st.session_state.get('game_archive_upload') or st.session_state.get('dashboard_saved_prediction')
        if source is not None and state['history']:
            try:
                copied = odds.export_copy(source.getvalue(), identity, state)
                st.download_button('オッズ履歴付き.keibaコピーを保存', copied,
                                   file_name=identity['race_id']+'_with_odds.keiba', key=key+'_copy')
            except (ValueError, TypeError, KeyError):
                caption('現在の読込元と一致する.keibaが確認できないため、コピー出力を保留しています。')
        st.download_button('オッズ履歴JSONを保存', json.dumps(dict(odds_history=state['history']), ensure_ascii=False, indent=2),
                           file_name=identity['race_id']+'_odds.json', key=key+'_json')
    if st.session_state.get(key+'_status'):
        st.info(st.session_state[key+'_status'])
    choices = [('保存時オッズ', q) for q in state['saved']] + [('更新オッズ', q) for q in state['history']]
    if not choices:
        return odds.overlay(view, None, 'オッズ未取得')
    # Explicit observation selection: never silently mix different price clocks.
    index = st.selectbox('表示するオッズ観測', range(len(choices)), index=len(choices)-1,
                         format_func=lambda i: f"{i+1}. {choices[i][0]} · 取得 {odds.format_time(choices[i][1].get('received_at'))}",
                         key=key+'_observation_'+str(len(choices)))
    label, quote = choices[index]
    start_at = odds.start_from_result(result)
    caption(f"{label}｜{odds.received_label(quote)}：{odds.format_time(quote.get('received_at'))}｜提供元更新：{odds.format_time(quote.get('observed_at'))}｜情報源：{quote['source']}")
    if quote.get('acquisition_method') == 'manual_html':
        caption('HTML取込日時はサイトから価格を取得した日時ではありません。価格の鮮度はHTML内の提供元更新時刻で確認します。')
    caption(f"{quote['horse_count']}／{quote['expected_horses']}頭（単勝または複勝）｜" + odds.freshness(quote, start_at))
    caption(' · '.join(f"{odds.LABELS[k]} {v['count']}／{v['expected']}件" for k,v in quote['coverage'].items()))
    pairs = [dict(券種=odds.LABELS[p['kind']], 馬番='－'.join(map(str,p['horses'])), オッズ=odds.price_text(p))
             for p in quote['prices'] if p['kind'] in ('wide','quinella')]
    if pairs:
        with st.expander('馬連・ワイドの組み合わせオッズ', expanded=False):
            st.dataframe(pairs, hide_index=True, use_container_width=True)
    return odds.overlay(view, quote, label)
