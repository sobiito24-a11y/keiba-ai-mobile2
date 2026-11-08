"""Dashboard research view: yesterday's fixed inference × today's user-entered odds.

No price scraping, no betting action and no 'recommended' label. Models are
uncalibrated. Users explicitly select one observation; no mixture of old odds.
"""
from __future__ import annotations

from . import race_odds
from .race_value_research import evaluate_reference


def current_observation(result, session_state):
    try:
        ident = race_odds.identity_from_result(result)
        saved = race_odds.state_for(result)
    except (ValueError, TypeError, KeyError):
        return None
    key = "race_prices_" + race_odds.digest(dict(identity=ident,saved=saved))
    state = session_state.get(key, saved)
    runtime = session_state.get(key + "_observation_runtime_v3") or {}
    active = runtime.get("active_observation")
    if not active:
        return None
    return next((q for q in (state.get("saved", []) + state.get("history", []))
                 if q.get("observation_id") == active), None)


def render(result):
    import streamlit as st
    from .independent_ai import resolve

    st.caption("前日予測は変更せず、研究用の勝率・3着以内率を直前オッズと比較します。"
               "確率モデルの校正・収益性は未検証で、購入推奨ではありません。")
    try:
        prediction = resolve(result)
        chosen = current_observation(result, st.session_state)
        report = evaluate_reference(prediction, chosen,
                                    start_time=race_odds.start_from_result(result))
    except (ValueError, TypeError, KeyError, ArithmeticError):
        st.warning("必要な確率またはオッズの整合性を確認できません。購入価値は判定しません。")
        return
    st.caption(f"モデル：{report.get('model_id') or '未取得'}｜{report['status']}")
    st.caption(f"選択した価格：{report['price_state']}")
    if chosen:
        st.caption("価格の確認元：" + str(chosen.get("source", "不明")))
        if chosen.get("acquisition_method") == "manual_user_checked":
            st.caption("入力時刻は利用者が目視確認した時刻です。提供元の更新時刻とは異なります。")

    if prediction.get("status") != "reference":
        st.info("このレースでは確率の必要な材料が揃っていないため、研究値を表示しません。")
        return

    rows = []
    for item in report["horses"]:
        rows.append({
            "馬番":item["no"],
            "馬名":item["name"],
            "参考勝率":f"{item['win']*100:.1f}%" if item["win"] is not None else "未取得",
            "参考3着内率":f"{item['place']*100:.1f}%" if item["place"] is not None else "未取得",
            "勝率からの単勝損益分岐":f"{1/item['win']:.1f}倍" if item["win"] and item["win"]>0 else "計算不可",
        })
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.caption("参考勝率・参考3着内率は過去モデルによる未校正の確率推定。"
               "『何%なら買う価値がある』と証明された数値ではありません。")

    tickets = report["tickets"]
    if not chosen:
        st.info("先に『買い目検討用・手動オッズ取込』で外部サイトの表示オッズを入力・選択すると比較できます。")
        return
    if not tickets:
        st.info("選んだ観測に、有効な単勝・複勝・ワイド・馬連オッズがありません。")
        return
    if len(tickets) > 60:
        st.caption("価格行が多いため先頭60件を表示します。欠損値を古い観測から補充しません。")
    labels = race_odds.LABELS
    pricing=[]
    for t in tickets[:60]:
        pricing.append({
            "券種": labels[t["kind"]],
            "馬番": "-".join(map(str,t["horses"])),
            "表示オッズ": f"{t['low']:.1f}" if t["low"]==t["high"]
                         else f"{t['low']:.1f}〜{t['high']:.1f}",
            "必要的中率":f"{t['break_even_pct']:.1f}%",
            "研究用推定的中率": f"{t['model_prob_pct']:.1f}%" if t["model_prob_pct"] is not None else "計算不可",
            "モデル上の期待回収率": f"{t['model_gross_pct']:.1f}%" if t["model_gross_pct"] is not None else "計算不可",
            "備考": "馬連は近似・未校正" if t["kind"]=="quinella" else "未校正",
        })
    st.dataframe(pricing, hide_index=True, use_container_width=True)
    st.caption("必要的中率＝100÷オッズ下限、研究上の期待回収率＝推定的中率×オッズ下限。"
               "同一観測の価格のみ比較し、ワイド・複勝は表示下限を使用。"
               "推定確率には信頼できる下限が確立しておらず、100%超でも購入推奨にはしません。")
    if report["price_state"] != "利用者が5分以内に確認（提供元の更新時刻は未確認）" and report["price_state"] != "発走前の観測価格（変動します）":
        st.warning("この価格は最新の購入可能オッズとして確認できません。再確認が必要です。")
    st.caption("馬券購入を自動実行しません。1R予算上限1,000円、不要なレースは見送りを優先。")
