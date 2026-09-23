"""Compact JRA final-purchase table. Prediction values are read-only."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


def jra_purchase_navigation_html(navigation: Mapping[str, Any]) -> str:
    if not navigation.get("show"):
        return ""

    def text(value: Any) -> str:
        return escape(str(value), quote=True)

    def horses(items, empty="該当なし") -> str:
        return " / ".join(
            f'<span style="display:inline-block;max-width:100%;">{text(h["number"])}番 {text(h["name"])}</span>'
            for h in items
        ) or empty

    grade = navigation.get("purchase_grade") or "D"
    label = navigation.get("purchase_label") or "見送り"
    style = navigation.get("purchase_style") or "見送り"
    reasons = list(navigation.get("purchase_reason_lines") or [])
    groups = navigation.get("buy_groups") or {k: [] for k in ("中心", "本線", "狙い", "押さえ参考")}

    parts = [
        '<section class="ka-dashboard-card" aria-label="JRA 最終購入判断" style="overflow-wrap:anywhere;">',
        '<div class="ka-dashboard-title">JRA 最終購入判断</div>',
        f'<p><strong style="font-size:1.1rem;">{text(grade)} {text(label)}</strong></p>',
        f'<p><strong>買い方</strong>：{text(style)}</p>',
        f'<p><strong>中心</strong>：{horses(groups.get("中心") or [])}</p>',
        f'<p><strong>本線</strong>：{horses(groups.get("本線") or [])}</p>',
        f'<p><strong>狙い</strong>：{horses(groups.get("狙い") or [], empty="なし")}</p>',
        f'<p><strong>押さえ参考</strong>：{horses(groups.get("押さえ参考") or [], empty="なし")}</p>',
        f'<p><strong>穴注意</strong>：{horses(navigation.get("hole_attention") or [], empty="なし")}</p>',
    ]
    if reasons:
        parts.append(f'<p class="ka-note">根拠：{text(" / ".join(str(x) for x in reasons))}</p>')

    parts.append('<details><summary>詳細を見る</summary>')
    visible = []
    for role in ("中心", "本線", "狙い", "押さえ参考"):
        visible.extend(groups.get(role) or [])
    if visible:
        parts.append('<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:.82rem;min-width:650px;">')
        parts.append('<thead><tr><th>役割</th><th>馬</th><th>印</th><th>Top5</th><th>Score</th><th>再現性</th><th>展開</th><th>調教</th></tr></thead><tbody>')
        for horse in visible:
            rank = horse.get("top5_rank")
            score = horse.get("top5_score")
            parts.append(
                '<tr>'
                f'<td>{text(horse.get("role") or "")}</td>'
                f'<td>{text(horse.get("number") or "")} {text(horse.get("name") or "")}</td>'
                f'<td>{text(horse.get("mark") or "")}</td>'
                f'<td>{text(f"{rank}位" if rank else "—")}</td>'
                f'<td>{text(f"{score:.1f}" if isinstance(score, (int, float)) else "—")}</td>'
                f'<td>{text(horse.get("reproducibility") or "—")}</td>'
                f'<td>{text(horse.get("pace") or "—")}</td>'
                f'<td>{text(horse.get("training") or "—")}</td>'
                '</tr>'
            )
        parts.append('</tbody></table></div>')

    for horse in navigation.get("layoff_warnings", []):
        parts.append(f'<p class="ka-note">⚠️ {horses([horse])} 長期休養明け：{text(horse["days"])}日</p>')

        if horse.get("is_top1"):
            parts.append('<p class="ka-note">軸評価は高いが、休養明けのため固定は慎重</p>')

    status = navigation.get("status") or "判定材料不足"
    description = navigation.get("description") or ""
    parts.append(f'<p><strong>{text(status)}</strong>：{text(description)}</p>')
    if navigation.get("leaders_match") is not None:
        parts.append(
            '<div class="ka-note">'
            + f'純能力1位とTop5 1位：{"一致" if navigation.get("leaders_match") else "不一致"} / '
            + f'Top5 2位差：{navigation.get("top5_score_gap", 0):.2f} / '
            + f'純能力2位差：{navigation.get("ability_gap", 0):.2f} / '
            + f'Top5入替：{navigation.get("swap_count", 0)}頭'
            + '</div>'
        )
    for role in ("CORE", "ABILITY", "SETUP"):
        parts.append(f'<p><strong>{role}</strong>：{horses((navigation.get("groups") or {}).get(role) or [])}</p>')
    if navigation.get("axis"):
        parts.append(f'<p>補助構造の軸候補：{horses([navigation["axis"]])}<br>相手候補：{horses(navigation.get("partners") or [])}</p>')
    parts.append('<strong>運用ガイド</strong><ul>' + ''.join(f'<li>{text(g)}</li>' for g in navigation.get("guides") or []) + '</ul>')
    parts.append('<div class="ka-note">最終購入判断はJRA最終印を主役にし、Top5・再現性・展開・調教を軸信頼の補助材料として使用します。純能力順位は購入役割を変更しません。取得時オッズ・人気は購入判定に使用しません。</div>')
    parts.append('</details></section>')
    return ''.join(parts)
