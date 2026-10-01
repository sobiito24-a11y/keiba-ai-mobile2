"""Frozen shadow display, shared desktop/mobile layout. Never evaluates a race."""
from html import escape


def newspaper_v2_html(result):
    mode = result.race_mode
    payload = (result.debug_info or {}).get(mode + "_newspaper_v2_shadow")
    if not payload:
        return '<p>未計算（保存時のV2データなし。再計算しません）</p>'
    if payload.get("status") == "excluded_jump":
        return '<p>障害戦：対象外／専用モデル未検証</p>'
    if payload.get("status") != "ok":
        return '<p>V2未評価：' + escape(str(payload.get("error", payload.get("status")))) + '</p>'
    prefix = mode + "_v2_"
    def fmt(v):
        return "—" if v is None else str(int(v))
    cards = []
    for h in sorted(payload["horses"], key=lambda r: (r.get(prefix + "win_candidate_rank") or 999, int(r["horse_no"]))):
        reasons = h.get(prefix + "positive_reasons", []) + h.get(prefix + "negative_reasons", [])
        missing = h.get(prefix + "missing_reasons", [])
        cards.append('<article class="newspaper-v2-horse"><b>' + escape(f'{h["horse_no"]} {h["horse_name"]}') + '</b><br>' +
                     escape(f'純能力順位 {fmt(h.get("pure_ability_rank"))} / 現行Top5順位 {fmt(h.get("official_top5_rank"))}') + '<br>' +
                     escape(f'V2勝ち馬候補 {fmt(h.get(prefix+"win_candidate_rank"))}位 / V2 Top5候補 {fmt(h.get(prefix+"top5_candidate_rank"))}位') +
                     '<br><small>' + escape(' / '.join(reasons) or '補助材料なし') + '</small>' +
                     ('<details><summary>データ品質・不足理由</summary>' + escape(' / '.join(missing)) + '</details>' if missing else '') + '</article>')
    ctx = payload.get("class_context", {})
    return ('<style>.newspaper-v2-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:8px}'
            '.newspaper-v2-horse{border:1px solid #8893a540;border-radius:6px;padding:8px;font-size:12px;overflow-wrap:anywhere}</style>'
            '<p>研究用・正式予想には不使用。V2スコアは勝率ではありません。</p><p>' +
            escape(f'クラス：{ctx.get("class_label_v2", "不明")} / {ctx.get("age_restriction_v2", "不明")}') +
            '</p><div class="newspaper-v2-grid">' + ''.join(cards) + '</div>')


def render_newspaper_v2_shadow(result):
    import streamlit as st
    with st.expander("新聞型V2研究比較（参考）", expanded=False):
        st.markdown(newspaper_v2_html(result), unsafe_allow_html=True)
