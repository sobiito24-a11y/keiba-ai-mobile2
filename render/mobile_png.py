from __future__ import annotations

import math
import os
import re
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from core.nar_race_diagnostics import build_full_field_comparison
from core.models import PredictionResult
from core.star_trace import log_star_trace, star_trace_row
from core.version import APP_VERSION, PREDICTION_LOGIC_VERSION


CANVAS_WIDTH = 1080
MAX_CANVAS_HEIGHT = 36000
MARGIN_X = 46
MARGIN_TOP = 42
MARGIN_BOTTOM = 46
CARD_RADIUS = 8

INK = (23, 30, 42)
MUTED = (91, 103, 122)
LIGHT_TEXT = (110, 120, 135)
RULE = (219, 225, 235)
SECTION_BG = (238, 243, 248)
CARD_BG = (255, 255, 255)
ACCENT = (34, 91, 158)
SOFT_ACCENT = (229, 239, 250)
WATCH_BG = (244, 248, 252)
WATCH_RULE = (117, 158, 198)
CONCLUSION_BG = (248, 251, 255)


class MobilePngRenderError(RuntimeError):
    """Raised when the mobile PNG cannot be rendered safely."""


def render_mobile_png(result: PredictionResult) -> bytes:
    """Render a PredictionResult into a single mobile-friendly PNG."""

    _append_png_star_trace(result)
    fonts = _load_fonts()
    canvas = _Canvas(fonts)
    canvas.draw_text_section(
        "会場別試験評価",
        _extract_raw_section(result, ["会場別試験評価", "JRA会場別試験評価"]),
    )
    canvas.draw_text_section("展開予想", _extract_raw_section(result, ["展開予想"]))
    canvas.draw_race_difficulty(result)
    canvas.draw_simple_overall(result)
    canvas.draw_horse_evaluation(result)
    canvas.draw_attention_horses(result)
    canvas.draw_ai_race_review(result)
    canvas.draw_text_section("今回の馬券構成", _strip_section_title(result.betting_structure, "今回の馬券構成"), compact=True)
    canvas.draw_version(result)
    return canvas.to_png()


def render_dummy_png(result: PredictionResult) -> bytes:
    """Backward-compatible alias kept for old Phase2 callers."""

    return render_mobile_png(result)


def _append_png_star_trace(result: PredictionResult) -> None:
    if result.race_mode != "nar":
        return
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        return
    debug_info = getattr(result, "debug_info", None)
    if debug_info is None:
        result.debug_info = {}
        debug_info = result.debug_info
    stage = "10 render/mobile_png.py"
    if debug_info.get(f"_logged_{stage}"):
        return
    rows = []
    for _, row in table.iterrows():
        rows.append(
            star_trace_row(
                horse_no=row.iloc[2] if len(row) > 2 else "",
                horse_name=row.iloc[3] if len(row) > 3 else "",
                year_max_index=_star_trace_value(row, "year_max_index", 23),
                star_max_index=_star_trace_value(row, "star_max_index", 24),
                star_source=row.get("star_max_source"),
            )
        )
    debug_info.setdefault("nar_star_trace", []).extend(log_star_trace(stage, rows))
    debug_info[f"_logged_{stage}"] = True


def _star_trace_value(row, key: str, fallback_pos: int):
    value = row.get(key)
    if value is not None:
        try:
            if pd.notna(value):
                return value
        except TypeError:
            return value
    if len(row) > fallback_pos:
        return row.iloc[fallback_pos]
    return value


class _Canvas:
    def __init__(self, fonts: dict[str, ImageFont.ImageFont]) -> None:
        self.fonts = fonts
        self.image = Image.new("RGB", (CANVAS_WIDTH, MAX_CANVAS_HEIGHT), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.y = MARGIN_TOP

    @property
    def content_width(self) -> int:
        return CANVAS_WIDTH - MARGIN_X * 2

    def to_png(self) -> bytes:
        final_height = min(MAX_CANVAS_HEIGHT, max(900, self.y + MARGIN_BOTTOM))
        if self.y + MARGIN_BOTTOM >= MAX_CANVAS_HEIGHT:
            raise MobilePngRenderError(
                "PNGの高さが安全上限を超えました。考察文や表示項目を確認してください。"
            )
        cropped = self.image.crop((0, 0, CANVAS_WIDTH, final_height))
        buffer = BytesIO()
        cropped.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    def draw_header(self, result: PredictionResult) -> None:
        mode_label = "地方競馬" if result.race_mode == "nar" else "中央競馬"
        race_name = _clean(result.race_name) or "レース名未取得"
        info_lines = _race_info_lines(result)

        self.text(mode_label, self.fonts["small"], MUTED, gap_after=4)
        self.text(race_name, self.fonts["title"], INK, gap_after=10)
        if info_lines:
            for line in info_lines:
                self.text(line, self.fonts["body"], INK, gap_after=3)
        else:
            self.text("レース情報：未取得", self.fonts["body"], MUTED)

        chip_lines = []
        confidence = _extract_ai_confidence(result)
        trend = _extract_pace_trend(result)
        if confidence:
            chip_lines.append(f"AI信頼度：{confidence}")
        if trend:
            chip_lines.append(f"展開傾向：{trend}")
        if chip_lines:
            self.y += 6
            for line in chip_lines:
                self.badge(line)
        self.y += 8

    def draw_today_conclusion(self, result: PredictionResult) -> None:
        self.section("本日の結論")
        rows = _conclusion_rows(result)
        if not rows:
            self.text("印付き馬は未取得です。", self.fonts["body"], MUTED)
            return

        x0 = MARGIN_X
        x1 = CANVAS_WIDTH - MARGIN_X
        padding = 18
        line_items: list[tuple[str, bool]] = []
        for row in rows:
            mark = _display_mark(row)
            no = str(_pick(row, "馬番", "馬") or "").strip()
            name = str(_pick(row, "馬名") or "").strip()
            suffix = "（穴候補）" if "✓" in mark else ""
            line_items.append((_join_nonempty([mark, no, name], sep=" ") + suffix, "✓" in mark))

        wrapped: list[tuple[str, bool]] = []
        max_width = self.content_width - padding * 2
        for text, is_watch in line_items:
            for line in _wrap_text(text, self.fonts["body_bold"], max_width, self.draw):
                wrapped.append((line, is_watch))

        height = padding * 2 + len(wrapped) * _line_height(self.fonts["body_bold"])
        self.draw.rounded_rectangle((x0, self.y, x1, self.y + height), radius=CARD_RADIUS, fill=CONCLUSION_BG, outline=RULE)
        y = self.y + padding
        for line, is_watch in wrapped:
            fill = ACCENT if is_watch else INK
            self.draw.text((x0 + padding, y), line, font=self.fonts["body_bold"], fill=fill)
            y += _line_height(self.fonts["body_bold"])
        self.y += height + 10

    def draw_race_difficulty(self, result: PredictionResult) -> None:
        rows = _records(result.overall_table)
        if not rows:
            rows = _records(result.horse_evaluation)
        if not rows:
            return
        first = rows[0]
        gap = _clean(_pick(first, "race_competitiveness_v4", "能力差", "ability_gap_level"))
        difficulty = _clean(_pick(first, "axis_confidence_v4", "レース難易度", "race_difficulty"))
        reason = _clean(_pick(first, "warning_reason", "レース難易度理由", "race_difficulty_reason"))
        if not gap and not difficulty:
            return
        self.section("レース難易度")
        lines = [
            _join_nonempty([f"能力差：{gap}" if gap else "", f"レース難易度：{difficulty}" if difficulty else ""], sep="　"),
            reason,
        ]
        for line in [line for line in lines if _clean(line)]:
            self.text(line, self.fonts["body_bold"] if "レース難易度" in line else self.fonts["body"], INK)

    def draw_simple_overall(self, result: PredictionResult) -> None:
        if _is_jra_result(result):
            self.section("今回の結論（JRA Top5）")
            rows = _jra_comparison_rows(result)
            if not rows:
                self.text("JRA Top5は未取得です。", self.fonts["body"], MUTED)
                return
            for row in rows:
                mark = _display_mark(row, result.race_mode)
                no = _pick(row, "number", "馬番", "馬")
                name = _pick(row, "name", "馬名")
                score = _format_number(_pick(row, "jra_top5_score"))
                ability = _format_number(_pick(row, "jra_pure_ability_score"))
                repro = _clean(_pick(row, "v1_reproducibility")) or "—"
                pace = _clean(_pick(row, "v1_pace_eval")) or "—"
                training = _clean(_pick(row, "jra_training_grade")) or "—"
                warning = _clean(_pick(row, "jra_warning_reason"))
                title = _join_nonempty([mark, str(no), str(name), f"JRA Top5 {score}" if score else ""], sep="  ")
                lines = [
                    _join_nonempty(
                        [
                            f"純能力{ability}" if ability else "",
                            f"再現性{repro} {_signed_bonus(_pick(row, 'jra_repro_bonus'))}",
                            f"展開{pace} {_signed_bonus(_pick(row, 'jra_pace_bonus'))}",
                            f"調教{training} {_signed_bonus(_pick(row, 'jra_training_bonus'))}",
                        ],
                        sep=" / ",
                    ),
                    _clean(_pick(row, "v1_final_role")),
                    f"注意：{warning}" if warning and _truthy_display(_pick(row, "jra_warning_candidate")) else "",
                ]
                self.horse_card(title, [line for line in lines if _clean(line)], is_watch=_truthy_display(_pick(row, "jra_warning_candidate")))
            return
        if _is_nar_result(result):
            self.section("今回の結論（NAR Top5）")
            rows = _nar_comparison_rows(result)
            if not rows:
                self.text("NAR Top5は未取得です。", self.fonts["body"], MUTED)
                return
            purchase = rows[0]
            judgement = _clean(_pick(purchase, "race_purchase_judgement"))
            purchase_label = _clean(_pick(purchase, "race_purchase_label"))
            if judgement or purchase_label:
                self.horse_card(
                    _join_nonempty(["レース購入判定", judgement, purchase_label], sep=" "),
                    [
                        _join_nonempty(
                            [
                                f"◎○差{_format_number(_pick(purchase, 'ability_gap_1_2'))}" if _pick(purchase, "ability_gap_1_2") is not None else "",
                                f"信頼相手{_pick(purchase, 'trusted_partner_count') or 0}頭",
                                f"候補{_clean(_pick(purchase, 'recommended_ticket_mode')) or 'PASS'}",
                            ],
                            sep=" / ",
                        ),
                        _clean(_pick(purchase, "win_bet_block_reason")) or "単勝購入可",
                        f"理由：{_clean(_pick(purchase, 'race_purchase_reason'))}" if _clean(_pick(purchase, "race_purchase_reason")) else "",
                    ],
                    is_watch=judgement in {"C", "D"},
                )
            top5 = [row for row in rows if (_to_float(_pick(row, "nar_top5_rank")) or 999) <= 5] or rows[:5]
            for row in top5:
                mark = _display_mark(row, result.race_mode)
                no = _pick(row, "number", "馬番", "馬")
                name = _pick(row, "name", "馬名")
                score = _format_number(_pick(row, "nar_top5_score"))
                ability = _format_number(_pick(row, "nar_pure_ability_score"))
                title = _join_nonempty([mark, str(no), str(name), f"NAR Top5 {score}" if score else ""], sep="  ")
                lines = [
                    _join_nonempty(
                        [
                            f"純能力{ability}" if ability else "",
                            f"相手信頼度{_clean(_pick(row, 'partner_trust_level')) or '—'}",
                            f"距離補正{_signed_bonus(_pick(row, 'nar_distance_bonus'))}",
                            f"コース補正{_signed_bonus(_pick(row, 'nar_course_bonus'))}",
                            f"展開補正{_signed_bonus(_pick(row, 'nar_pace_bonus'))}",
                            f"近走補正{_signed_bonus(_pick(row, 'nar_recent_bonus'))}",
                        ],
                        sep=" / ",
                    ),
                    _clean(_pick(row, "nar_top5_role")),
                    f"根拠：{_clean(_pick(row, 'nar_top5_reason'))}" if _clean(_pick(row, "nar_top5_reason")) else "",
                ]
                self.horse_card(title, [line for line in lines if _clean(line)], is_watch=False)
            warnings = [row for row in rows if _truthy_display(_pick(row, "nar_warning_candidate")) and (_to_float(_pick(row, "nar_top5_rank")) or 999) > 5]
            if warnings:
                self.section("注意馬")
                for row in warnings:
                    no = _pick(row, "number", "馬番", "馬")
                    name = _pick(row, "name", "馬名")
                    reason = _clean(_pick(row, "nar_warning_reason")) or "Top5外の注意条件に該当"
                    self.horse_card(_join_nonempty([str(no), str(name), "注意馬"], sep=" "), [reason], is_watch=True)
            return
        self.section("レース全体表")
        rows = _records(result.overall_table)
        if not rows:
            self.text("レース全体表は未取得です。", self.fonts["body"], MUTED)
            return

        for row in rows:
            mark = _display_mark(row)
            pace_mark = _pick(row, "展開印")
            no = _pick(row, "馬番", "馬")
            name = _pick(row, "馬名")
            odds = _format_odds(_pick(row, "単勝オッズ", "オッズ", "単勝"))
            style = _display_running_style(row)
            total = _format_number(_pick(row, "horse_score_v4", "総合評価", "総合評価点", "補正AI点"))
            ability_value = _format_number(_pick(row, "horse_score_v4", "能力評価値", "ability_display_score", "raw_score"))
            ability_band = _clean(_pick(row, "能力帯", "ability_band"))
            training_grade = _clean(_pick(row, "調教評価", "追切評価")) if result.race_mode == "jra" else ""
            class_shift = _pick(row, "クラス変動") or "-"
            age = _pick(row, "馬年齢", "性齢", "馬齢")
            weight = _pick(row, "斤量")
            jockey = _pick(row, "騎手") or "―"
            interval = _pick(row, "レース間隔", "間隔")
            going = _pick(row, "馬場実績")
            distance = _format_number(_pick(row, "距離指数"))
            course = _format_number(_pick(row, "コース指数"))
            avg = _format_number(_pick(row, "平均指数"))
            best = _pick(row, "★最高指数")
            best_race = _clean(_pick(row, "★該当走", "star_max_race"))
            best_condition = _clean(_pick(row, "★条件", "star_max_condition"))
            best_detail = "・".join([value for value in (best_race, best_condition) if value])
            best_text = f"★最高{best}"
            if best and best_detail:
                best_text = f"{best_text}（{best_detail}）"
            three_back = _pick(row, "3走前")
            two_back = _pick(row, "2走前")
            last = _pick(row, "前走")
            material = _pick(row, "評価／検討材料", "評価/検討材料", "評価材料")

            title = _join_nonempty([mark, pace_mark, str(no), str(name), odds, style], sep="  ")
            lines = [
                _join_nonempty(
                    [
                        f"総合{total}" if total else "",
                        f"能力評価値{ability_value}" if ability_value else "",
                        f"能力帯{ability_band}" if ability_band else "",
                        f"調教{training_grade}" if training_grade else "",
                    ],
                    sep=" / ",
                ),
                _join_nonempty(
                    [
                        str(age) if age else "",
                        f"斤量{weight}" if weight else "",
                        str(jockey) if jockey else "",
                        f"間隔{interval}" if interval else "",
                        f"クラス{class_shift}",
                    ],
                    sep=" / ",
                ),
                _join_nonempty(
                    [
                        f"馬場{going}" if going else "",
                        f"距離{distance}" if distance else "",
                        f"コース{course}" if course else "",
                        f"平均{avg}" if avg else "",
                        best_text if best else "★最高なし",
                    ],
                    sep=" / ",
                ),
                _join_nonempty(
                    [
                        f"3走前 {three_back}" if three_back else "",
                        f"2走前 {two_back}" if two_back else "",
                        f"前走 {last}" if last else "",
                    ],
                    sep=" / ",
                ),
            ]
            if material:
                lines.append(f"材料：{material}")
            self.horse_card(title, [line for line in lines if line], is_watch="✓" in str(mark))

    def draw_horse_evaluation(self, result: PredictionResult) -> None:
        self.section("馬評価（全頭）")
        if _is_jra_result(result):
            rows = _jra_comparison_rows(result)
            if not rows:
                self.text("馬評価は未取得です。", self.fonts["body"], MUTED)
                return
            for row in rows:
                no = _pick(row, "number", "馬番", "馬")
                mark = _display_mark(row, result.race_mode)
                name = _pick(row, "name", "馬名")
                score = _format_number(_pick(row, "jra_top5_score"))
                ability_value = _format_number(_pick(row, "jra_pure_ability_score"))
                jockey = _pick(row, "jockey_info", "jockey_display", "騎手") or "―"
                style = _display_running_style(row) or "データなし"
                state = _clean(_pick(row, "v1_state_eval")) or "判定なし"
                title = _join_nonempty([str(mark), str(no), str(name)], sep=" ")
                lines = [
                    f"JRA Top5スコア：{score}" if score else "",
                    f"純能力：{ability_value}" if ability_value else "",
                    _join_nonempty(
                        [
                            f"再現性{_clean(_pick(row, 'v1_reproducibility')) or '—'} {_signed_bonus(_pick(row, 'jra_repro_bonus'))}",
                            f"展開{_clean(_pick(row, 'v1_pace_eval')) or '—'} {_signed_bonus(_pick(row, 'jra_pace_bonus'))}",
                            f"調教{_clean(_pick(row, 'jra_training_grade')) or '—'} {_signed_bonus(_pick(row, 'jra_training_bonus'))}",
                        ],
                        sep="　",
                    ),
                    f"状態：{state}（参考表示・スコア加点なし）",
                    f"騎手：{jockey}",
                    f"脚質：{style}",
                    f"理由：{_clean(_pick(row, 'v1_final_reason'))}" if _clean(_pick(row, "v1_final_reason")) else "",
                ]
                self.horse_card(title, [line for line in lines if _clean(line)], is_watch=_truthy_display(_pick(row, "jra_warning_candidate")))
            return
        if _is_nar_result(result):
            rows = _nar_comparison_rows(result)
            if not rows:
                self.text("馬評価は未取得です。", self.fonts["body"], MUTED)
                return
            for row in rows:
                no = _pick(row, "number", "馬番", "馬")
                mark = _display_mark(row, result.race_mode)
                name = _pick(row, "name", "馬名")
                score = _format_number(_pick(row, "nar_top5_score"))
                ability_value = _format_number(_pick(row, "nar_pure_ability_score"))
                jockey = _pick(row, "jockey_info", "jockey_display", "騎手") or "―"
                style = _display_running_style(row) or "データなし"
                title = _join_nonempty([str(mark), str(no), str(name)], sep=" ")
                lines = [
                    f"NAR Top5スコア：{score}" if score else "",
                    f"純能力：{ability_value}" if ability_value else "",
                    f"相手信頼度：{_clean(_pick(row, 'partner_trust_level')) or '—'}",
                    _join_nonempty(
                        [
                            f"距離補正{_signed_bonus(_pick(row, 'nar_distance_bonus'))}",
                            f"コース補正{_signed_bonus(_pick(row, 'nar_course_bonus'))}",
                            f"展開補正{_signed_bonus(_pick(row, 'nar_pace_bonus'))}",
                            f"近走補正{_signed_bonus(_pick(row, 'nar_recent_bonus'))}",
                        ],
                        sep="　",
                    ),
                    f"騎手：{jockey}",
                    f"脚質：{style}",
                    f"理由：{_clean(_pick(row, 'nar_top5_reason'))}" if _clean(_pick(row, "nar_top5_reason")) else "",
                ]
                self.horse_card(title, [line for line in lines if _clean(line)], is_watch=_truthy_display(_pick(row, "nar_warning_candidate")))
            return
        rows = _records(result.horse_evaluation)
        if not rows:
            self.text("馬評価は未取得です。", self.fonts["body"], MUTED)
            return

        is_nar = result.race_mode == "nar"
        for row in rows:
            no = _pick(row, "馬番", "馬")
            mark = _display_mark(row)
            name = _pick(row, "馬名")
            group = _display_group(row)
            horse_age = _pick(row, "馬年齢", "性齢", "馬齢") or "データなし"
            jockey = _pick(row, "騎手", "jockey") or "―"
            style = _display_running_style(row) or "データなし"
            weight_detail = _pick(row, "斤量詳細")
            jockey_detail = _pick(row, "騎手詳細") or jockey
            odds = _format_odds(_pick(row, "単勝オッズ", "オッズ", "単勝"))
            ability_value = _format_number(_pick(row, "horse_score_v4", "能力評価値", "ability_display_score", "raw_score"))
            state = _clean(_pick(row, "状態", "form_state", "近3走傾向", "recent3_trend")) or "判定なし"
            star = _format_number(_pick(row, "★最高指数", "star_max_index"))
            distance = _format_number(_pick(row, "距離指数"))
            course = _format_number(_pick(row, "コース指数"))
            class_shift = _pick(row, "クラス変動") or "-"
            material = _pick(row, "評価／検討材料", "評価/検討材料", "評価材料") or "-"
            material = _limit_materials(material)
            horse_type = _pick(row, "馬タイプ") or "-"
            comment = _pick(row, "表示コメント", "display_comment", "一言コメント", "コメント") or ""
            support_label = "対戦" if is_nar else "調教"
            support_value = (
                _pick(row, "対戦評価", "対戦材料", "対戦") if is_nar else _pick(row, "調教評価", "調教/評価/検討材料", "状態材料")
            ) or ("未評価" if is_nar else "未取得")
            stable_comment = _pick(row, "厩舎コメント", "新聞コメント") if not is_nar else ""
            audit_labels = _join_nonempty(
                [
                    "穴候補：該当" if _truthy_display(_pick(row, "穴候補", "hole_candidate")) else "",
                    "注意馬：該当" if _truthy_display(_pick(row, "注意馬", "watch_horse")) else "",
                ],
                sep="　",
            )

            title = _join_nonempty([f"【{group}】", str(mark), str(no), str(name)], sep=" ")
            lines = [
                f"馬年齢：{horse_age}",
                f"脚質：{style}",
                f"斤量：{weight_detail}" if weight_detail else "",
                f"騎手：{jockey_detail}",
                f"単勝：{odds}" if odds else "単勝：―",
                _join_nonempty(
                    [
                        f"★{star}" if star else "★該当なし",
                        f"距離{distance}" if distance else "距離—",
                        f"コース{course}" if course else "コース—",
                        f"状態：{state}",
                    ],
                    sep="　",
                ),
                f"能力評価値：{ability_value}" if ability_value else "",
                audit_labels,
                _join_nonempty([f"クラス：{class_shift}", f"{support_label}：{support_value}"], sep="　"),
                f"材料：{material}",
                f"タイプ：{horse_type}",
            ]
            if stable_comment:
                lines.append(f"厩舎コメント：{_shorten(stable_comment, 58)}")
            if comment:
                lines.append(f"コメント：{comment}")
            self.horse_card(title, lines, is_watch="✓" in str(mark))

    def draw_attention_horses(self, result: PredictionResult) -> None:
        self.section("注目馬")
        blocks = [str(block).strip() for block in result.attention_horses if str(block).strip()]
        if not blocks:
            self.text("注目馬は未取得です。", self.fonts["body"], MUTED)
            return
        for block in blocks[:5]:
            lines = _compact_lines(block, max_lines=4)
            if not lines:
                continue
            title = lines[0]
            self.attention_card(title, lines[1:] or ["確認材料あり"])

    def draw_ai_race_review(self, result: PredictionResult) -> None:
        self.section("AIレース考察")
        review = _strip_section_title(result.ai_race_review, "AIレース考察")
        body = _clean_multiline(review)
        if not body:
            self.text("未取得です。", self.fonts["body"], MUTED)
            return
        self.text_block(body, self.fonts["body"], INK, paragraph_gap=8)
        self.y += 2

    def draw_text_section(self, title: str, text: str, *, compact: bool = False) -> None:
        self.section(title)
        body = _clean_multiline(text)
        if not body:
            self.text("未取得です。", self.fonts["body"], MUTED)
            return
        font = self.fonts["body"] if not compact else self.fonts["small"]
        self.text_block(body, font, INK, paragraph_gap=8 if compact else 10)
        self.y += 2

    def draw_version(self, result: PredictionResult) -> None:
        self.y += 14
        self.rule()
        created_at = _format_created_at(result.created_at)
        lines = [
            "Keiba AI Mobile",
            f"Version {APP_VERSION}",
            f"Logic Version {PREDICTION_LOGIC_VERSION}",
            f"作成日時 {created_at}",
        ]
        for line in lines:
            self.text(line, self.fonts["tiny"], LIGHT_TEXT, gap_after=4)

    def section(self, title: str) -> None:
        self.y += 8
        x0 = MARGIN_X
        x1 = CANVAS_WIDTH - MARGIN_X
        height = 48
        self.draw.rounded_rectangle((x0, self.y, x1, self.y + height), radius=8, fill=SECTION_BG)
        self.draw.text((x0 + 18, self.y + 10), title, font=self.fonts["section"], fill=ACCENT)
        self.y += height + 12

    def subheading(self, title: str) -> None:
        self.text(title, self.fonts["body_bold"], ACCENT, gap_after=4)

    def rule(self) -> None:
        self.draw.line((MARGIN_X, self.y, CANVAS_WIDTH - MARGIN_X, self.y), fill=RULE, width=2)
        self.y += 14

    def badge(self, text: str) -> None:
        font = self.fonts["small_bold"]
        padding_x = 14
        padding_y = 6
        width = min(self.content_width, math.ceil(self.draw.textlength(text, font=font)) + padding_x * 2)
        height = _line_height(font) + padding_y * 2
        x0 = MARGIN_X
        self.draw.rounded_rectangle((x0, self.y, x0 + width, self.y + height), radius=8, fill=SOFT_ACCENT)
        self.draw.text((x0 + padding_x, self.y + padding_y), text, font=font, fill=ACCENT)
        self.y += height + 6

    def overall_card(self, title: str, subtitle: str, *, is_watch: bool = False) -> None:
        x0 = MARGIN_X
        x1 = CANVAS_WIDTH - MARGIN_X
        padding = 13
        fill = WATCH_BG if is_watch else CARD_BG
        outline = WATCH_RULE if is_watch else RULE
        title_lines = _wrap_text(title, self.fonts["body_bold"], self.content_width - padding * 2, self.draw)
        subtitle_lines = _wrap_text(subtitle, self.fonts["small_bold"], self.content_width - padding * 2, self.draw) if subtitle else []
        height = padding * 2 + len(title_lines) * _line_height(self.fonts["body_bold"]) + len(subtitle_lines) * _line_height(self.fonts["small_bold"]) + 2
        self.draw.rounded_rectangle((x0, self.y, x1, self.y + height), radius=CARD_RADIUS, fill=fill, outline=outline)
        if is_watch:
            self.draw.rounded_rectangle((x0, self.y, x0 + 8, self.y + height), radius=4, fill=WATCH_RULE)
        y = self.y + padding
        for line in title_lines:
            self.draw.text((x0 + padding + (6 if is_watch else 0), y), line, font=self.fonts["body_bold"], fill=INK)
            y += _line_height(self.fonts["body_bold"])
        y += 1
        for line in subtitle_lines:
            self.draw.text((x0 + padding + (6 if is_watch else 0), y), line, font=self.fonts["small_bold"], fill=ACCENT)
            y += _line_height(self.fonts["small_bold"])
        self.y += height + 6

    def horse_card(self, title: str, lines: list[str], *, is_watch: bool = False) -> None:
        x0 = MARGIN_X
        x1 = CANVAS_WIDTH - MARGIN_X
        padding = 14
        max_width = self.content_width - padding * 2 - (8 if is_watch else 0)
        fill = WATCH_BG if is_watch else CARD_BG
        outline = WATCH_RULE if is_watch else RULE
        wrapped_title = _wrap_text(title, self.fonts["body_bold"], max_width, self.draw)
        wrapped_lines: list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]] = []
        for line in lines:
            font = self.fonts["small_bold"] if line.startswith(("能力", "AI")) else self.fonts["small"]
            color = INK if font == self.fonts["small_bold"] else MUTED
            for wrapped in _wrap_text(str(line), font, max_width, self.draw):
                wrapped_lines.append((wrapped, font, color))
        height = padding * 2 + len(wrapped_title) * _line_height(self.fonts["body_bold"]) + 3
        height += sum(_line_height(font) for _, font, _ in wrapped_lines)
        self.draw.rounded_rectangle((x0, self.y, x1, self.y + height), radius=CARD_RADIUS, fill=fill, outline=outline)
        if is_watch:
            self.draw.rounded_rectangle((x0, self.y, x0 + 8, self.y + height), radius=4, fill=WATCH_RULE)
        y = self.y + padding
        x_text = x0 + padding + (8 if is_watch else 0)
        for line in wrapped_title:
            self.draw.text((x_text, y), line, font=self.fonts["body_bold"], fill=INK)
            y += _line_height(self.fonts["body_bold"])
        y += 3
        for line, font, color in wrapped_lines:
            self.draw.text((x_text, y), line, font=font, fill=color)
            y += _line_height(font)
        self.y += height + 7

    def attention_card(self, title: str, lines: list[str]) -> None:
        x0 = MARGIN_X
        x1 = CANVAS_WIDTH - MARGIN_X
        padding = 15
        max_width = self.content_width - padding * 2
        wrapped_title = _wrap_text(title, self.fonts["body_bold"], max_width, self.draw)
        wrapped_lines: list[str] = []
        for line in lines:
            wrapped_lines.extend(_wrap_text(str(line), self.fonts["small_bold"], max_width, self.draw))
        height = padding * 2 + len(wrapped_title) * _line_height(self.fonts["body_bold"]) + 3
        height += len(wrapped_lines) * _line_height(self.fonts["small_bold"])
        self.draw.rounded_rectangle((x0, self.y, x1, self.y + height), radius=CARD_RADIUS, fill=CARD_BG, outline=RULE)
        y = self.y + padding
        for line in wrapped_title:
            self.draw.text((x0 + padding, y), line, font=self.fonts["body_bold"], fill=INK)
            y += _line_height(self.fonts["body_bold"])
        y += 3
        for line in wrapped_lines:
            self.draw.text((x0 + padding, y), line, font=self.fonts["small_bold"], fill=MUTED)
            y += _line_height(self.fonts["small_bold"])
        self.y += height + 8

    def text(self, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int], gap_after: int = 7) -> None:
        for line in _wrap_text(str(text), font, self.content_width, self.draw):
            self.draw.text((MARGIN_X, self.y), line, font=font, fill=fill)
            self.y += _line_height(font)
        self.y += gap_after

    def text_block(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple[int, int, int],
        paragraph_gap: int = 8,
    ) -> None:
        for paragraph in text.splitlines():
            paragraph = paragraph.strip()
            if not paragraph:
                self.y += paragraph_gap
                continue
            for line in _wrap_text(paragraph, font, self.content_width, self.draw):
                self.draw.text((MARGIN_X, self.y), line, font=font, fill=fill)
                self.y += _line_height(font)
            self.y += paragraph_gap



def _load_fonts() -> dict[str, ImageFont.ImageFont]:
    for font_path in _candidate_font_paths():
        loaded = _try_load_font_family(font_path)
        if loaded:
            return loaded
    raise MobilePngRenderError(
        "日本語フォントを取得できませんでした。assets/fonts/NotoSansJP-Regular.ttf を配置するか、"
        "Cloud環境からGoogle Fontsへアクセスできるか確認してください。"
    )


def _candidate_font_paths() -> list[str]:
    paths: list[str] = []

    bundled_noto = _bundled_noto_font_path()
    paths.append(str(bundled_noto))

    env_path = os.environ.get("KEIBA_AI_FONT_PATH", "").strip()
    if env_path:
        paths.append(env_path)

    paths.extend(_asset_font_paths(prefer_noto=True))
    downloaded = _download_noto_sans_jp_once()
    if downloaded:
        paths.append(downloaded)
    paths.extend(_system_noto_font_paths())
    paths.extend(_asset_font_paths(prefer_noto=False))
    paths.extend(_system_japanese_font_paths())

    seen: set[str] = set()
    unique_paths: list[str] = []
    for path in paths:
        text = str(path or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if Path(text).exists():
            unique_paths.append(text)
    return unique_paths


def _bundled_noto_font_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansJP-Regular.ttf"


def _asset_font_paths(*, prefer_noto: bool) -> list[str]:
    assets_dir = Path(__file__).resolve().parents[1] / "assets"
    if not assets_dir.exists():
        return []
    fonts: list[Path] = []
    for pattern in ("*.ttf", "*.otf", "*.ttc"):
        fonts.extend(assets_dir.glob(pattern))
        fonts.extend((assets_dir / "fonts").glob(pattern))
    if prefer_noto:
        fonts = [path for path in fonts if "noto" in path.name.lower()]
    else:
        fonts = [path for path in fonts if "noto" not in path.name.lower()]
    return [str(path) for path in sorted(fonts)]


def _system_noto_font_paths() -> list[str]:
    return [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/usr/local/share/fonts/NotoSansJP-Regular.ttf",
        "/usr/local/share/fonts/NotoSansJP-VariableFont_wght.ttf",
    ]


def _system_japanese_font_paths() -> list[str]:
    return [
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/meiryob.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/YuGothR.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4\u30b7\u30c3\u30af W3.ttc",
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4\u30b7\u30c3\u30af W6.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ]


@lru_cache(maxsize=1)
def _download_noto_sans_jp_once() -> str:
    for cache_dir in _font_cache_dirs():
        cached = _find_cached_noto_font(cache_dir)
        if cached:
            return cached

    writable_dirs: list[Path] = []
    for cache_dir in _font_cache_dirs():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            test_file = cache_dir / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            writable_dirs.append(cache_dir)
        except Exception:
            continue
    if not writable_dirs:
        return ""

    for url in _noto_sans_jp_download_urls():
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 KeibaAIMobile/0.3",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
            for cache_dir in writable_dirs:
                font_path = _save_downloaded_font(payload, cache_dir, url)
                if font_path:
                    return font_path
        except Exception:
            continue
    return ""


def _font_cache_dirs() -> list[Path]:
    dirs = [_bundled_noto_font_path().parent]
    configured = os.environ.get("KEIBA_AI_FONT_CACHE_DIR", "").strip()
    if configured:
        dirs.append(Path(configured))
    home = Path.home()
    if str(home) and home.exists():
        dirs.append(home / ".cache" / "keiba_ai_mobile" / "fonts")
    dirs.append(Path(tempfile.gettempdir()) / "keiba_ai_mobile_fonts")

    seen: set[str] = set()
    unique_dirs: list[Path] = []
    for directory in dirs:
        text = str(directory)
        if text in seen:
            continue
        seen.add(text)
        unique_dirs.append(directory)
    return unique_dirs


def _find_cached_noto_font(cache_dir: Path) -> str:
    if not cache_dir.exists():
        return ""
    patterns = (
        "NotoSansJP*.ttf",
        "NotoSansJP*.otf",
        "NotoSansJP*.ttc",
        "NotoSansCJK*.otf",
        "NotoSansCJK*.ttc",
    )
    for pattern in patterns:
        for path in sorted(cache_dir.glob(pattern)):
            if path.is_file() and path.stat().st_size > 10000 and _is_loadable_font_path(path):
                return str(path)
    return ""


def _noto_sans_jp_download_urls() -> list[str]:
    return [
        "https://fonts.google.com/download?family=Noto%20Sans%20JP",
        "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
    ]


def _save_downloaded_font(payload: bytes, cache_dir: Path, url: str) -> str:
    if not payload:
        return ""
    if zipfile.is_zipfile(BytesIO(payload)):
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".ttf", ".otf", ".ttc"))
                and "notosansjp" in name.replace("_", "").replace("-", "").lower()
            ]
            names.sort(key=_font_archive_priority)
            for name in names:
                data = archive.read(name)
                if len(data) <= 10000:
                    continue
                target = cache_dir / Path(name).name
                target.write_bytes(data)
                if _is_loadable_font_path(target):
                    return str(target)
                target.unlink(missing_ok=True)
        return ""

    suffix = ".ttf"
    if ".otf" in url.lower():
        suffix = ".otf"
    target = cache_dir / f"NotoSansJP-Downloaded{suffix}"
    if len(payload) > 10000:
        target.write_bytes(payload)
        if _is_loadable_font_path(target):
            return str(target)
        target.unlink(missing_ok=True)
    return ""


def _font_archive_priority(name: str) -> tuple[int, str]:
    lower = name.lower()
    if "regular" in lower:
        return (0, lower)
    if "variable" in lower or "wght" in lower:
        return (1, lower)
    return (2, lower)


def _try_load_font_family(font_path: str) -> dict[str, ImageFont.ImageFont] | None:
    try:
        return {
            "title": ImageFont.truetype(font_path, 38),
            "section": ImageFont.truetype(font_path, 27),
            "body": ImageFont.truetype(font_path, 25),
            "body_bold": ImageFont.truetype(font_path, 26),
            "small": ImageFont.truetype(font_path, 21),
            "small_bold": ImageFont.truetype(font_path, 22),
            "tiny": ImageFont.truetype(font_path, 18),
        }
    except Exception:
        return None


def _is_loadable_font_path(path: Path) -> bool:
    try:
        ImageFont.truetype(str(path), 16)
        return True
    except Exception:
        return False

def _is_jra_result(result: PredictionResult) -> bool:
    return _clean(getattr(result, "race_mode", "")).lower() == "jra"


def _is_nar_result(result: PredictionResult) -> bool:
    return _clean(getattr(result, "race_mode", "")).lower() == "nar"


def _jra_row_sort_key(row: dict[str, Any]) -> tuple[int, float, float, int]:
    rank = _to_float(_pick(row, "v1_final_rank", "jra_top5_rank"))
    score = _to_float(_pick(row, "jra_top5_score"))
    ability = _to_float(_pick(row, "jra_pure_ability_score"))
    no = _to_float(_pick(row, "number", "馬番", "馬"))
    return (
        int(rank) if rank is not None else 999,
        -(score if score is not None else -9999.0),
        -(ability if ability is not None else -9999.0),
        int(no) if no is not None else 999,
    )


def _nar_row_sort_key(row: dict[str, Any]) -> tuple[int, float, float, int]:
    rank = _to_float(_pick(row, "nar_top5_rank"))
    score = _to_float(_pick(row, "nar_top5_score"))
    ability = _to_float(_pick(row, "nar_pure_ability_score", "market_ability_score", "ability_value", "saved_ability_value"))
    number = _to_float(_pick(row, "number", "馬番", "馬"))
    return (
        int(rank) if rank is not None else 999,
        -(score if score is not None else -9999.0),
        -(ability if ability is not None else -9999.0),
        int(number) if number is not None else 999,
    )


def _jra_comparison_rows(result: PredictionResult) -> list[dict[str, Any]]:
    source_rows = _records(result.overall_table)
    if not source_rows:
        source_rows = _records(result.horse_evaluation)
    if not source_rows:
        return []
    comparison = build_full_field_comparison(
        source_rows,
        race_mode="jra",
        sort_mode="current",
        race_info=getattr(result, "race_info", {}) or {},
    )
    rows = [row for row in comparison.get("rows", []) if isinstance(row, dict)]
    return sorted(rows, key=_jra_row_sort_key)


def _nar_comparison_rows(result: PredictionResult) -> list[dict[str, Any]]:
    source_rows = _records(result.overall_table)
    if not source_rows:
        source_rows = _records(result.horse_evaluation)
    if not source_rows:
        return []
    comparison = build_full_field_comparison(
        source_rows,
        race_mode="nar",
        sort_mode="current",
        race_info=getattr(result, "race_info", {}) or {},
    )
    rows = [row for row in comparison.get("rows", []) if isinstance(row, dict)]
    return sorted(rows, key=_nar_row_sort_key)


def _signed_bonus(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "±0.0"
    if abs(number) < 0.0001:
        return "±0.0"
    return f"{number:+.1f}"


def _conclusion_rows(result: PredictionResult) -> list[dict[str, Any]]:
    if _is_jra_result(result):
        return _jra_comparison_rows(result)[:7]
    if _is_nar_result(result):
        return _nar_comparison_rows(result)[:7]
    rows = _records(result.overall_table)
    if not rows:
        rows = _records(result.horse_evaluation)
    selected: list[dict[str, Any]] = []
    for row in rows:
        mark = _display_mark(row, result.race_mode)
        if mark:
            selected.append(row)
    return selected[:7]


def _nar_top5_mark_from_rank(rank: Any) -> str:
    value = _to_float(rank)
    if value is None:
        return ""
    return {1: "◎", 2: "○", 3: "▲", 4: "△1", 5: "△2"}.get(int(value), "")


def _display_mark(row: dict[str, Any], race_mode: str = "") -> str:
    if _clean(race_mode).lower() == "jra":
        mark = _clean(_pick(row, "v1_final_mark"))
        if mark:
            return mark
        fallback = _clean(_pick(row, "ver3_final_mark"))
        if fallback:
            return fallback
    if _clean(race_mode).lower() == "nar":
        return _nar_top5_mark_from_rank(_pick(row, "nar_top5_rank"))
    if "mark_v4" in row:
        return _clean(row.get("mark_v4"))
    if "表示印" in row:
        return _clean(row.get("表示印"))
    if "display_mark" in row:
        return _clean(row.get("display_mark"))
    return _clean(_pick(row, "印", "最終印"))


def _display_group(row: dict[str, Any]) -> str:
    group = _clean(_pick(row, "group_v4", "グループ", "display_group"))
    if group in {"SS", "A", "B", "C", "Z"}:
        return group
    mark = _display_mark(row)
    if mark == "◎":
        return "SS"
    if mark in {"○", "▲"}:
        return "A"
    if mark == "△":
        return "B"
    if mark in {"✓", "✔"}:
        return "C"
    return "Z"


def _display_running_style(row: dict[str, Any]) -> str:
    text = _clean(_pick(row, "脚質表示", "running_style_display", "脚質", "running_style", "style"))
    if not text:
        return ""
    if "逃" in text:
        return "逃げ"
    if "先" in text:
        return "先行"
    if "差" in text:
        return "差し"
    if "追" in text:
        return "追込"
    return text


def _race_info_lines(result: PredictionResult) -> list[str]:
    info = result.race_info or {}
    lines: list[str] = []
    venue = _first_value(info, "venue", "place", "track_name", "会場")
    race_no = _first_value(info, "race_no", "race_number", "R")
    race_class = _first_value(info, "class", "race_class", "クラス")
    if venue or race_no or race_class:
        lines.append(_join_nonempty([venue, f"{race_no}R" if race_no and not str(race_no).endswith("R") else race_no, race_class], sep="　"))

    race_data = _first_value(info, "race_data", "race_info", "条件")
    if race_data:
        lines.append(str(race_data))
    else:
        start = _first_value(info, "start_time", "発走")
        distance = _first_value(info, "distance", "距離")
        course = _first_value(info, "course", "コース")
        weather = _first_value(info, "weather", "天候")
        going = _first_value(info, "ground_state", "馬場", "going")
        line1 = _join_nonempty([f"{start}発走" if start and "発走" not in str(start) else start, distance, course], sep="　")
        line2 = _join_nonempty([f"天候：{weather}" if weather else "", f"馬場：{going}" if going else ""], sep="　")
        if line1:
            lines.append(line1)
        if line2:
            lines.append(line2)
    return [_clean(line) for line in lines if _clean(line)]


def _extract_ai_confidence(result: PredictionResult) -> str:
    info = result.race_info or {}
    for key in ("AI信頼度", "ai_confidence", "confidence"):
        value = info.get(key)
        if value:
            return str(value)
    text = "\n".join([result.raw_output or "", result.ai_race_review or "", result.betting_structure or ""])
    match = re.search(r"AI信頼度\s*[:：]?\s*([★☆]{5})", text)
    return match.group(1) if match else ""


def _extract_pace_trend(result: PredictionResult) -> str:
    text = "\n".join([result.raw_output or "", result.ai_race_review or ""])
    for pattern in (r"展開傾向\s*[:：]\s*(.+)", r"脚質構成\s*[:：]\s*(.+)"):
        match = re.search(pattern, text)
        if match:
            return _shorten(match.group(1).strip(), 34)

    rows = _records(result.overall_table)
    if not rows:
        return ""
    style_counts = {"逃": 0, "先": 0, "差": 0, "追": 0}
    for row in rows:
        style = str(_pick(row, "脚質") or "")
        for key in style_counts:
            if key in style:
                style_counts[key] += 1
                break
    if sum(style_counts.values()) == 0:
        return ""
    return f"逃{style_counts['逃']} 先{style_counts['先']} 差{style_counts['差']} 追{style_counts['追']}"


def _build_review_summary(result: PredictionResult, review: str) -> list[str]:
    text = _clean_multiline(review)
    rows = _conclusion_rows(result)
    top_rows = rows[:3]
    watch_rows = [row for row in rows if "✓" in _display_mark(row)]
    summary: list[str] = []

    if "先行" in text or "前" in text:
        summary.append("先行勢の位置取りを確認")
    elif "逃げ" in text:
        summary.append("逃げ馬のペースが焦点")
    elif "差し" in text:
        summary.append("差し届くかが焦点")

    if top_rows:
        labels = []
        for row in top_rows[:2]:
            mark = _display_mark(row)
            no = _pick(row, "馬番", "馬")
            labels.append(_join_nonempty([mark, no], sep=""))
        if labels:
            summary.append(f"{'・'.join(labels)}を中心に確認")

    if watch_rows:
        row = watch_rows[0]
        no = _pick(row, "馬番", "馬")
        name = _pick(row, "馬名")
        summary.append(f"✓{no} {name}は穴候補")

    if "能力" in text:
        summary.append("能力上位馬と展開材料を照合")
    if "BOX" in text or "混戦" in text:
        summary.append("広げすぎず候補を整理")

    if not summary and text:
        summary.append(_shorten(text.split("。")[0], 34))
    return summary[:4]


def _records(table: Any) -> list[dict[str, Any]]:
    if table is None:
        return []
    if hasattr(table, "to_dict"):
        try:
            return list(table.to_dict("records"))
        except Exception:
            return []
    if isinstance(table, list):
        return [dict(item) for item in table if isinstance(item, dict)]
    return []


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = row.get(name)
            if not _is_missing(value):
                return value
    return ""


def _first_value(info: dict[str, Any], *names: str) -> str:
    for name in names:
        value = info.get(name)
        text = _clean(value)
        if text:
            return text
    return ""


def _format_odds(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    if "倍" in text:
        return text
    number = _to_float(text)
    if number is None:
        return text
    return f"{number:g}倍"


def _format_number(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return _clean(value)
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _to_float(value: Any) -> float | None:
    try:
        if _is_missing(value):
            return None
        text = str(value).replace(",", "").replace("倍", "").strip()
        if not text or text.lower() == "nan":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _limit_materials(value: Any, limit: int = 4) -> str:
    text = _clean(value)
    if not text:
        return "-"
    parts = [part.strip() for part in re.split(r"[／/、,]", text) if part.strip()]
    if not parts:
        return text
    unique: list[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    return "／".join(unique[:limit])


def _join_nonempty(parts: Iterable[Any], sep: str = " ") -> str:
    cleaned = [_clean(part) for part in parts if _clean(part)]
    return sep.join(cleaned)


def _clean(value: Any) -> str:
    if _is_missing(value):
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truthy_display(value: Any) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y", "○", "あり"}


def _clean_multiline(value: Any) -> str:
    if _is_missing(value):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and compact:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()


def _strip_section_title(text: str, title: str) -> str:
    cleaned = _clean_multiline(text)
    patterns = [f"【{title}】", title]
    for pattern in patterns:
        if cleaned.startswith(pattern):
            return cleaned[len(pattern) :].strip()
    return cleaned


def _extract_raw_section(result: PredictionResult, titles: list[str]) -> str:
    raw = _clean_multiline(result.raw_output)
    if not raw:
        return ""
    escaped_titles = "|".join(re.escape(title) for title in titles)
    pattern = re.compile(
        rf"【(?P<title>{escaped_titles})】\s*\n?(?P<body>.*?)(?=\n【[^】]+】|\Z)",
        re.DOTALL,
    )
    match = pattern.search(raw)
    if not match:
        return ""
    return _clean_multiline(match.group("body"))


def _compact_lines(text: str, max_lines: int) -> list[str]:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return lines
    kept = lines[: max_lines - 1]
    kept.append(_shorten(" ".join(lines[max_lines - 1 :]), 58))
    return kept


def _shorten(text: str, max_len: int) -> str:
    text = _clean(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _format_created_at(value: str) -> str:
    if not value:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    text = _clean(text)
    if not text:
        return [""]
    result: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            result.append("")
            continue
        result.extend(_wrap_single_line(line, font, max_width, draw))
    return result


def _wrap_single_line(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    if draw.textlength(text, font=font) <= max_width:
        return [text]

    tokens = re.findall(r"[A-Za-z0-9_./:%+-]+|\s+|.", text)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = current + token
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current.strip():
            lines.append(current.strip())
        current = token.strip()
        if draw.textlength(current, font=font) > max_width:
            broken = _break_long_token(current, font, max_width, draw)
            lines.extend(broken[:-1])
            current = broken[-1] if broken else ""
    if current.strip():
        lines.append(current.strip())
    return lines or [text]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
        try:
            if bool(missing):
                return True
        except (TypeError, ValueError):
            pass
    except (TypeError, ValueError):
        pass
    return str(value).strip() in {"", "None", "none", "nan", "NaN", "<NA>", "NaT"}


def _break_long_token(
    token: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox("あいうえおABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return max(17, bbox[3] - bbox[1] + 7)
