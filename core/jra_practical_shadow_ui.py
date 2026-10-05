"""Saved research-only display; no evaluation at render/restore time."""
from html import escape
from .jra_practical_shadow import KEY


def practical_shadow_html(result):
    if result.race_mode != 'jra':
        return ''
    data = (result.debug_info or {}).get(KEY)
    if not data:
        return '<p>未計算（保存時の実戦再評価Shadowなし。旧Snapshotは再評価しません）</p>'
    def esc(value):
        return escape(str(value if value is not None else '—'))
    def paras(items):
        return ''.join('<p>' + esc(item) + '</p>' for item in items)
    def fmt(value):
        if value is None:
            return '—'
        if isinstance(value, (list, tuple)):
            return '〜'.join(fmt(v) for v in value)
        return f'{value:.2f}'.rstrip('0').rstrip('.') if isinstance(value, (float, int)) else str(value)
    horses = data.get('horses', [])
    by_no = {str(h['horse_no']): h for h in horses}
    def names(numbers):
        return ' / '.join(f'{n} {by_no.get(str(n), {}).get("horse_name", "")}' for n in numbers) or '未確定'
    def card(h):
        interval = h['score_interval']
        ranks = h['shadow_rank_range']
        return ('<article class="practical-shadow-horse"><b>' + esc(f'{h["horse_no"]} {h.get("horse_name", "")}｜{h["classification"]}') +
                '</b>' + paras([f'正式 {fmt(h.get("formal_rank"))}位 / {fmt(h.get("formal_score"))}｜純能力 {fmt(h.get("pure_score"))}',
                               f'共通材料での研究順位 {fmt(h.get("comparison_rank"))} / 研究評価 {fmt(h.get("comparison_score"))}',
                               f'全材料の研究順位範囲 {fmt(ranks)} / 評価区間 {fmt(interval)}（勝率ではありません）']) +
                '<div>プラス材料</div>' + paras(h['positive_reasons'] or ['確認できる材料なし']) +
                '<div>不安材料</div>' + paras(h['negative_reasons'] or ['確認できる材料なし（安全の意味ではない）']) +
                '<div>判断条件</div>' + paras(h['decisive_conditions']) +
                '<details><summary>欠損・入力根拠</summary>' + paras(h['missing_reasons']) +
                '<pre>' + esc(__import__('json').dumps({k: h.get(k) for k in ('sources', 'components', 'recent_runs', 'layoff_returns')}, ensure_ascii=False, indent=2)) + '</pre></details></article>')
    out = ('<style>.practical-shadow-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:8px}'
           '.practical-shadow-horse{border:1px solid #94a3b844;border-radius:6px;padding:8px;font-size:12px;overflow-wrap:anywhere}'
           '.practical-shadow-horse p{margin:4px 0}.practical-shadow-horse pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}</style>'
           '<p>研究Shadow・購入推奨ではありません。正式順位・印・勝率・買い方は変更しません。</p>' +
           paras([{'research_only': '独立した研究評価です。', 'excluded_jump': '障害レース：研究対象外',
                   'time_unverified': '発走前データであることを確認できないため、5頭案は保留します。',
                   'input_error': '入力を確認できないため評価を保留します。'}.get(data.get('status'), '評価状態不明'), data.get('reason', '')]) +
           '<details><summary>評価記録</summary>' + paras([data.get('model_version'), '評価日時：' + str(data.get('evaluated_at')),
                   '検証用の参考再計算' if str(data.get('evaluation_context', '')).startswith('retrospective') else '新規予想時の保存評価']) +
           '</details><h4>今回の実戦考察</h4>' + paras(data.get('race_assessment', [])))
    for title, label in [('評価を上げたい馬', '評価上昇'), ('正式上位だが慎重な馬', '正式上位だが慎重'), ('消す前に再確認したい馬', '消す前に再確認')]:
        selected = [h for h in horses if h['classification'] == label]
        out += '<h4>' + title + '</h4><div class="practical-shadow-grid">' + (''.join(card(h) for h in selected) or '<p>該当なし</p>') + '</div>'
    out += '<h4>正式Top5／自由選択5頭／保護付き5頭</h4>'
    for key, title in [('A', 'A 正式Top5'), ('B', 'B 自由選択5頭（全頭共通の取得材料で比較）'), ('C', 'C 保護付き5頭（最大1頭）')]:
        out += paras([title + '：' + names(data.get(key, []))])
        change = data.get('comparison', {}).get(key)
        if change:
            out += paras(['追加：' + (names(change['added']) if change['added'] else 'なし'),
                          '除外：' + (names(change['removed']) if change['removed'] else 'なし')])
    out += paras([data.get('selection_status'), data.get('protection_reason')])
    if data.get('swap'):
        out += paras(data['swap']['reasons'])
    return out + '<h4>全頭の評価理由</h4><div class="practical-shadow-grid">' + ''.join(card(h) for h in horses) + '</div>'


def render_practical_shadow(result):
    if result.race_mode == 'jra':
        import streamlit as st
        with st.expander('JRA実戦再評価Shadow（研究・参考）', expanded=False):
            st.markdown(practical_shadow_html(result), unsafe_allow_html=True)
