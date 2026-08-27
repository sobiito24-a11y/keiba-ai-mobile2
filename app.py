from __future__ import annotations

import html
import json
import re
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
import streamlit as st

from core.audit_features import (
    audit_table_to_csv_bytes,
    audit_table_to_json_bytes,
    audit_table_to_markdown,
    build_audit_export_table,
)
from core.ability_watch import attach_ability_watch_columns
from core.betting_recommendation import (
    LAST_MATCH_AUDIT,
    BettingRecommendation,
    adoption_map_from_recommendations,
    build_betting_recommendations,
)
from core.condition_fit import condition_fit_badge_text, resolved_condition_fit
from core.course_materials import four_corner_rates_display
from core.investment_decision import (
    InvestmentDecision,
    build_investment_decision,
    confidence_label,
)
from core.purchase_conditions import build_purchase_condition_recommendations, horse_no
from core.research_bets import build_research_bet
from core.prediction_input import predict_from_html_inputs
from core.html_classifier import (
    DISPLAY_ORDER,
    classify_html,
    classify_many,
    kind_label,
    required_kinds,
    validate_upload_bundle,
)
from core.models import ClassifiedHtml, PredictionResult, RaceMode, UploadBundleValidation
from core.market_compare import (
    build_race_summary as build_market_race_summary,
    freeze_market_prediction,
    price_band_rows,
    race_pace_snapshot,
)
from core.nar_race_diagnostics import (
    build_full_field_comparison,
    build_nar_full_field_comparison,
    build_nar_race_diagnostics,
    category_reason,
    comparison_position_icon,
    diagnostic_line,
    position_group_label,
)
from core.nar_json_input import (
    NarJsonDataError,
    NarJsonPredictionInput,
    build_nar_prediction_inputs_from_uploads,
)
from core.prediction_history import (
    prediction_zip_bytes,
    prediction_zip_filename,
    save_prediction_history,
)
from core.practical_validation import (
    freeze_practical_prediction,
    practical_validation_summary,
    settle_practical_result,
)
from core.recent_races import (
    recent_races_detail_text as rich_recent_races_detail_text,
    recent_races_summary_text,
)
from core.star_trace import log_star_trace, star_trace_row
from core.value_support import (
    VALUE_FIELD_NAMES,
    attach_value_signals,
    course_material_display,
    current_mark_reference,
    stable_comment_display,
    training_display,
    value_reference_rows,
)
from core.version import APP_VERSION
from core.ver4_engine import prediction_logic_version as normalize_prediction_logic_version
from render.mobile_png import MobilePngRenderError, render_mobile_png


st.set_page_config(
    page_title="Keiba AI Mobile",
    layout="centered",
    initial_sidebar_state="collapsed",
)


MOBILE_CSS = """
<style>
  .block-container {
    max-width: 560px;
    padding: 1.2rem 0.9rem 2.5rem;
  }
  h1 {
    font-size: 1.55rem !important;
    line-height: 1.25 !important;
    margin-bottom: 0.35rem !important;
  }
  h2, h3 {
    letter-spacing: 0 !important;
  }
  .ka-muted {
    color: #687385;
    font-size: 0.92rem;
  }
  .ka-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 0.85rem 0.9rem;
    margin: 0.65rem 0;
    background: #ffffff;
  }
  .ka-ok {
    color: #067647;
    font-weight: 700;
  }
  .ka-ng {
    color: #b42318;
    font-weight: 700;
  }
  .ka-file {
    color: #344054;
    font-size: 0.9rem;
    overflow-wrap: anywhere;
  }
  .ka-section {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 0.8rem 0.85rem;
    margin: 0.55rem 0 1rem;
    background: #ffffff;
    white-space: pre-wrap;
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  .ka-dashboard-card {
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    padding: 0.85rem 0.9rem;
    margin: 0.55rem 0 0.9rem;
    background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  }
  .ka-dashboard-title {
    font-size: 0.78rem;
    color: #667085;
    font-weight: 700;
    letter-spacing: 0 !important;
    margin-bottom: 0.25rem;
  }
  .ka-dashboard-value {
    font-size: 1.1rem;
    color: #101828;
    font-weight: 800;
    margin-bottom: 0.2rem;
  }
  .ka-chip {
    display: inline-block;
    border-radius: 999px;
    padding: 0.16rem 0.48rem;
    margin: 0.08rem 0.18rem 0.08rem 0;
    font-size: 0.78rem;
    font-weight: 700;
    border: 1px solid #d0d5dd;
    color: #344054;
    background: #f9fafb;
  }
  .ka-chip.ss { background: #fff1f3; border-color: #fecdd6; color: #b42318; }
  .ka-chip.a { background: #fff7ed; border-color: #fed7aa; color: #b45309; }
  .ka-chip.b { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .ka-chip.c { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
  .ka-chip.z { background: #f2f4f7; border-color: #d0d5dd; color: #667085; }
  .ka-power-group {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 0.75rem;
    margin: 0.55rem 0;
    background: #ffffff;
  }
  .ka-power-row {
    padding: 0.28rem 0;
    border-top: 1px solid #f2f4f7;
    font-size: 0.9rem;
    line-height: 1.45;
  }
  .ka-power-row:first-of-type { border-top: none; }
  .ka-horse-card details summary {
    cursor: pointer;
    list-style: none;
  }
  .ka-horse-card details summary::-webkit-details-marker {
    display: none;
  }
  .ka-horse-title-line {
    display: flex;
    gap: 0.35rem;
    align-items: baseline;
    flex-wrap: wrap;
    font-weight: 800;
    color: #101828;
  }
  .ka-horse-quick {
    margin-top: 0.35rem;
    color: #344054;
    font-size: 0.92rem;
    line-height: 1.55;
  }
  .ka-ability-wrap {
    margin-top: 0.5rem;
  }
  .ka-ability-head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    color: #344054;
    font-size: 0.84rem;
    font-weight: 800;
  }
  .ka-ability-track {
    width: 100%;
    height: 9px;
    margin-top: 0.2rem;
    border-radius: 999px;
    overflow: hidden;
    background: #eef2f6;
  }
  .ka-ability-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #3563e9 0%, #4ea1ff 100%);
  }
  .ka-material-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.24rem;
    margin-top: 0.45rem;
  }
  .ka-material-badge {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.1rem 0.42rem;
    font-size: 0.76rem;
    font-weight: 800;
    border: 1px solid #d0d5dd;
    color: #475467;
    background: #f9fafb;
    white-space: nowrap;
  }
  .ka-material-badge.plus { color: #047857; background: #ecfdf3; border-color: #abefc6; }
  .ka-material-badge.minus { color: #b42318; background: #fff1f3; border-color: #fecdd6; }
  .ka-material-badge.info { color: #175cd3; background: #eff8ff; border-color: #b2ddff; }
  .ka-material-badge.neutral { color: #475467; background: #f9fafb; border-color: #d0d5dd; }
  .ka-horse-detail {
    margin-top: 0.65rem;
    padding-top: 0.55rem;
    border-top: 1px solid #eef2f6;
    color: #344054;
    font-size: 0.9rem;
    line-height: 1.55;
  }
  .ka-horse-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 0.75rem 0.8rem;
    margin: 0.55rem 0;
    background: #ffffff;
    line-height: 1.55;
  }
  .ka-horse-card.watch {
    border-left: 4px solid #6f98c5;
    background: #f8fbff;
  }
  .ka-horse-title {
    font-weight: 700;
    margin-bottom: 0.35rem;
    color: #172033;
  }
  .ka-horse-meta {
    color: #344054;
    font-size: 0.92rem;
  }
  .ka-note {
    color: #344054;
    font-size: 0.92rem;
    line-height: 1.55;
  }
  .ka-market-band {
    display: grid;
    grid-template-columns: 2.4rem 1fr;
    gap: 0.55rem;
    align-items: start;
    border-top: 1px solid #eef2f6;
    padding: 0.5rem 0;
  }
  .ka-market-band:first-child { border-top: none; }
  .ka-market-band-label {
    font-weight: 900;
    color: #101828;
    font-size: 1rem;
  }
  .ka-market-price {
    display: inline-block;
    margin: 0 0.35rem 0.25rem 0;
    font-weight: 800;
    color: #1d2939;
    white-space: nowrap;
  }
  .ka-market-fair { color: #667085; font-weight: 500; font-size: 0.78rem; }
  .ka-market-card-title { font-size: 1rem; font-weight: 900; color: #101828; }
  .ka-market-card-line { color: #344054; font-size: 0.88rem; line-height: 1.55; }
  .ka-market-plus { color: #047857; }
  .ka-market-minus { color: #b42318; }
  .ka-nar-diagnostic-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.55rem;
    margin: 0.55rem 0 0.9rem;
  }
  .ka-nar-diagnostic-card {
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    padding: 0.7rem 0.75rem;
    background: #ffffff;
    min-height: 100%;
  }
  .ka-nar-diagnostic-card.win { border-color: #fed7aa; background: #fffbeb; }
  .ka-nar-diagnostic-card.partner { border-color: #bbf7d0; background: #f0fdf4; }
  .ka-nar-diagnostic-card.pace { border-color: #b2ddff; background: #eff8ff; }
  .ka-nar-diagnostic-card.outside { border-color: #fed7aa; background: #fff7ed; }
  .ka-nar-diagnostic-card.insufficient { border-color: #d9d6fe; background: #f4f3ff; }
  .ka-nar-diagnostic-title {
    font-weight: 900;
    color: #101828;
    font-size: 0.92rem;
    margin-bottom: 0.35rem;
  }
  .ka-nar-diagnostic-item {
    border-top: 1px solid rgba(16,24,40,0.08);
    padding: 0.34rem 0;
    color: #344054;
    font-size: 0.86rem;
    line-height: 1.45;
  }
  .ka-nar-diagnostic-item:first-of-type { border-top: none; }
  .ka-position-stage {
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    padding: 0.7rem 0.75rem;
    margin: 0.35rem 0;
    background: #ffffff;
  }
  .ka-position-line {
    display: grid;
    grid-template-columns: 2.8rem 1fr;
    gap: 0.35rem;
    align-items: start;
    font-size: 0.86rem;
    color: #344054;
    padding: 0.12rem 0;
  }
  .ka-horse-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.55rem;
    height: 1.55rem;
    border-radius: 999px;
    margin: 0 0.16rem 0.16rem 0;
    background: #f2f4f7;
    color: #344054;
    font-weight: 900;
    font-size: 0.78rem;
  }
  .ka-comparison-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 0.45rem 0 1rem;
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    background: #ffffff;
  }
  .ka-comparison-table {
    border-collapse: separate;
    border-spacing: 0;
    min-width: 760px;
    width: max-content;
    font-size: 0.82rem;
    line-height: 1.35;
  }
  .ka-comparison-table th,
  .ka-comparison-table td {
    border-right: 1px solid #eef2f6;
    border-bottom: 1px solid #eef2f6;
    padding: 0.42rem 0.5rem;
    vertical-align: top;
    min-width: 7.2rem;
    color: #344054;
    background: #ffffff;
  }
  .ka-comparison-table th.ka-sticky-metric,
  .ka-comparison-table td.ka-sticky-metric {
    position: sticky;
    left: 0;
    z-index: 3;
    min-width: 7.4rem;
    background: #f8fafc;
    color: #101828;
    font-weight: 900;
  }
  .ka-comparison-table th.ka-sticky-no,
  .ka-comparison-table td.ka-sticky-no,
  .ka-comparison-table th.ka-sticky-name,
  .ka-comparison-table td.ka-sticky-name,
  .ka-comparison-table th.ka-sticky-mark,
  .ka-comparison-table td.ka-sticky-mark {
    position: sticky;
    z-index: 3;
    background: #f8fafc;
    font-weight: 900;
  }
  .ka-comparison-table th.ka-sticky-no,
  .ka-comparison-table td.ka-sticky-no {
    left: 0;
    min-width: 3.4rem;
  }
  .ka-comparison-table th.ka-sticky-name,
  .ka-comparison-table td.ka-sticky-name {
    left: 3.4rem;
    min-width: 8.4rem;
  }
  .ka-comparison-table th.ka-sticky-mark,
  .ka-comparison-table td.ka-sticky-mark {
    left: 11.8rem;
    min-width: 3.4rem;
  }
  .ka-comparison-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f8fafc;
    color: #101828;
    font-weight: 900;
  }
  .ka-comparison-table th:first-child,
  .ka-comparison-table td:first-child {
    color: #101828;
  }
  .ka-comparison-table thead th.ka-sticky-no,
  .ka-comparison-table thead th.ka-sticky-name,
  .ka-comparison-table thead th.ka-sticky-mark,
  .ka-comparison-table thead th.ka-sticky-metric { z-index: 5; }
  .ka-comparison-cell-front { color: #047857; font-weight: 900; }
  .ka-comparison-cell-back { color: #b42318; font-weight: 800; }
  .ka-comparison-tag {
    display: inline-block;
    border-radius: 999px;
    padding: 0.08rem 0.34rem;
    margin: 0.06rem 0.08rem 0.06rem 0;
    font-size: 0.72rem;
    font-weight: 800;
    white-space: nowrap;
  }
  .ka-comparison-tag.plus {
    color: #047857;
    background: #ecfdf3;
    border: 1px solid #abefc6;
  }
  .ka-comparison-tag.minus {
    color: #b42318;
    background: #fff1f3;
    border: 1px solid #fecdd6;
  }
  .ka-comparison-vs {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 0.6rem;
    align-items: stretch;
  }
  .ka-comparison-vs-card {
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    padding: 0.65rem 0.7rem;
    background: #ffffff;
    font-size: 0.86rem;
    line-height: 1.45;
  }
  .ka-comparison-vs-mid {
    align-self: center;
    font-weight: 900;
    color: #667085;
  }
  @media (max-width: 640px) {
    .ka-comparison-table {
      min-width: 680px;
      font-size: 0.78rem;
    }
    .ka-comparison-table th,
    .ka-comparison-table td {
      min-width: 6.4rem;
      padding: 0.36rem 0.42rem;
    }
    .ka-comparison-vs {
      grid-template-columns: 1fr;
    }
    .ka-comparison-vs-mid {
      text-align: center;
    }
  }
  div[data-testid="stRadio"] label {
    align-items: flex-start;
  }
</style>
"""


FETCH_TIMEOUT_SECONDS = 20
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class GeneratedHtmlSpec:
    kind: str
    label: str
    url: str
    required: bool = True


class HtmlFetchError(RuntimeError):
    def __init__(self, failures: list[dict[str, str]]) -> None:
        super().__init__("必要HTMLを取得できませんでした。")
        self.failures = failures


def main() -> None:
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)
    _init_state()

    st.title("Keiba AI Mobile")
    st.markdown(
        f'<div class="ka-muted">v{APP_VERSION} / iPhone向けPNG生成</div>',
        unsafe_allow_html=True,
    )

    mode_label = st.radio(
        "地方／中央",
        options=["地方", "中央"],
        index=0,
        horizontal=True,
        key="mode_label",
    )
    mode: RaceMode = "nar" if mode_label == "地方" else "jra"

    logic_label = st.radio(
        "予想ロジック",
        options=[
            "能力×価格比較（推奨）",
            "実戦モード（Ver3印＋保守的BUY）",
            "Ver3（従来）",
            "Ver4.1（研究用）",
            "Ver4（baseline）",
        ],
        index=0,
        horizontal=False,
        key="prediction_logic_label",
        help="能力×価格比較はVer3能力を固定し、オッズ・条件・展開を独立表示します。自動BUYは行いません。",
    )
    if logic_label.startswith("能力×価格"):
        selected_logic_version = "market"
    elif logic_label.startswith("実戦"):
        selected_logic_version = "practical"
    elif logic_label.startswith("Ver4.1"):
        selected_logic_version = "v4.1"
    elif logic_label.startswith("Ver4"):
        selected_logic_version = "v4"
    else:
        selected_logic_version = "v3"
    if st.session_state.prediction_logic_version != selected_logic_version:
        clear_prediction_state(keep_input=True)
    st.session_state.prediction_logic_version = selected_logic_version

    if mode == "nar":
        render_nar_json_flow()
    else:
        render_upload_flow("jra")

    if st.session_state.prediction_result is not None and st.session_state.png_bytes is not None:
        render_result_area(st.session_state.prediction_result, st.session_state.png_bytes)


def _init_state() -> None:
    st.session_state.setdefault("url_input_key", 0)
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("prediction_result", None)
    st.session_state.setdefault("png_bytes", None)
    st.session_state.setdefault("fetch_failures", [])
    st.session_state.setdefault("fetch_race_id", "")
    st.session_state.setdefault("input_signature", "")
    st.session_state.setdefault("prediction_logic_version", "market")


def render_nar_json_flow() -> None:
    st.subheader("地方データ追加")
    st.caption("iPhoneショートカットで保存した3ファイルをまとめて選択してください。")
    st.caption("出走表ページ → JSON（または競馬新聞HTML） / タイム指数ページ → JSON / コース分析の脚質ページ → HTMLまたはJSON")
    uploaded_files = st.file_uploader(
        "iPhoneショートカットで保存した地方競馬ファイルを選択",
        type=["json", "html"],
        accept_multiple_files=True,
        help="ファイル名や拡張子ではなく、中身で自動判定します。entry JSONが無い場合は地方競馬新聞HTMLから出走表相当データを生成します。",
        key=f"nar_json_upload_{st.session_state.uploader_key}",
    )

    package: NarJsonPredictionInput | None = None
    current_input_signature = "nar:json"
    if uploaded_files:
        current_input_signature += ":" + "|".join(
            f"{file.name}:{getattr(file, 'size', 0)}" for file in uploaded_files
        )
    if st.session_state.input_signature != current_input_signature:
        clear_prediction_state()
        st.session_state.input_signature = current_input_signature

    st.subheader("認識結果")
    if not uploaded_files:
        st.info("出走表JSONまたは競馬新聞HTML、タイム指数JSON、コース脚質HTML/JSONを追加してください。")
    else:
        try:
            package = build_nar_prediction_inputs_from_uploads(
                [(file.name, file.getvalue()) for file in uploaded_files]
            )
            render_nar_json_status(package)
        except NarJsonDataError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"地方データ入力の確認中に失敗しました: {exc}")
            with st.expander("開発者向け詳細", expanded=False):
                st.code(traceback.format_exc())

    fallback_selected: dict[str, ClassifiedHtml] = {}
    fallback_grouped: dict[str, list[ClassifiedHtml]] = {}
    fallback_ready = False
    with st.expander("詳細設定：HTMLを直接アップロード", expanded=False):
        st.caption("JSONを作れない場合だけ使用してください。競馬新聞HTML、タイム指数HTML、脚質分析HTMLをまとめて選択します。")
        (
            fallback_selected,
            fallback_grouped,
            has_fallback_uploads,
            fallback_missing,
            fallback_validation,
        ) = render_upload_input(
            "nar",
            key_prefix="nar_json_direct",
        )
        fallback_ready = (
            has_fallback_uploads
            and not fallback_missing
            and fallback_validation.is_valid
            and bool(fallback_selected)
        )
        if fallback_ready:
            st.info("直接アップロードHTMLを使用して予想できます。JSONが揃っている場合はJSONを優先します。")

    st.subheader("予想")
    can_predict = package is not None or fallback_ready
    if st.button("予想する", disabled=not can_predict, type="primary", use_container_width=True, key="predict_nar_json"):
        clear_prediction_state(keep_input=True)
        if package is not None:
            result, png_bytes = run_nar_json_prediction_with_progress(package)
            if result is not None and png_bytes is not None:
                st.session_state.prediction_result = result
                st.session_state.png_bytes = png_bytes
        elif fallback_ready:
            result, png_bytes = run_upload_prediction_with_progress(
                "nar",
                fallback_selected,
                fallback_grouped,
            )
            if result is not None and png_bytes is not None:
                st.session_state.prediction_result = result
                st.session_state.png_bytes = png_bytes

    with st.expander("詳細設定：旧URL入力モード", expanded=False):
        st.caption("通常はJSONアップロード方式を使用してください。URL方式はCloudからnetkeibaへ取得できる場合のみ使えます。")
        use_legacy_url = st.checkbox("旧URL入力モードを使う", value=False, key="use_legacy_nar_url")
        if use_legacy_url:
            render_nar_legacy_url_flow()


def render_nar_json_status(package: NarJsonPredictionInput) -> None:
    st.success(f"{package.race_id} のデータを読み込みました")
    entry_label = "競馬新聞HTMLから生成" if package.entry_source == "nar_newspaper_html" else "JSON"
    st.write(f"出走表：{package.entry_count}頭（{entry_label}）")
    st.write(f"タイム指数：{package.speed_count}頭")
    st.write(f"各馬脚質：{package.horse_style_count}頭")
    if package.running_styles:
        st.write("コース脚質：" + "・".join(package.running_styles))
    else:
        st.write("コース脚質：未取得")
    render_nar_previous_jockey_upload_trace(package)
    render_nar_star_upload_trace(package)


def render_nar_previous_jockey_upload_trace(package: NarJsonPredictionInput) -> None:
    rows = list(getattr(package, "debug_logs", ()) or ())
    if not rows:
        return
    with st.expander("地方前走騎手診断（アップロード解析）", expanded=False):
        st.caption("HTML全文は表示せず、前走騎手の抽出・統合経路だけを表示します。")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_nar_star_upload_trace(package: NarJsonPredictionInput) -> None:
    rows = list(getattr(package, "star_debug_logs", ()) or ())
    if not rows:
        return
    with st.expander("地方★最高指数診断（アップロード〜HTML生成）", expanded=False):
        st.caption("JSON読込直後、speed疑似HTML生成時、courseanalysis生成時のyear_max_index / star_max_indexです。")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_nar_legacy_url_flow() -> None:
    st.subheader("出馬表URL")
    race_url = st.text_input(
        "地方競馬の出馬表URL",
        placeholder="https://nar.netkeiba.com/race/shutuba.html?race_id=202644072012",
        help="出馬表URLを1つ貼るだけで、出馬表・タイム指数・脚質分析を自動取得します。",
        key=f"race_url_{st.session_state.url_input_key}",
    )
    current_input_signature = f"nar:{race_url.strip()}"
    if st.session_state.input_signature != current_input_signature:
        clear_prediction_state()
        st.session_state.input_signature = current_input_signature

    race_id = extract_race_id(race_url)
    specs = build_nar_generated_url_specs(race_id) if race_id else []

    st.subheader("認識結果")
    if not race_url.strip():
        st.info("出馬表URLを入力してください。")
    elif not race_id:
        st.error("URLから race_id を取得できませんでした。netkeiba地方競馬の出馬表URLを入力してください。")
    else:
        st.success(f"race_id を取得しました: {race_id}")
        render_generated_url_cards(specs)

    if (
        st.session_state.fetch_failures
        and st.session_state.fetch_race_id == race_id
    ):
        render_fetch_failures(st.session_state.fetch_failures)

    fallback_selected: dict[str, ClassifiedHtml] = {}
    fallback_grouped: dict[str, list[ClassifiedHtml]] = {}
    fallback_ready = False
    with st.expander("詳細設定：HTMLを直接アップロード", expanded=False):
        st.caption("URL自動取得に失敗する場合だけ使用してください。")
        fallback_selected, fallback_grouped, has_uploads, missing, validation = render_upload_input(
            "nar",
            key_prefix="nar_fallback",
        )
        fallback_ready = has_uploads and not missing and validation.is_valid and bool(fallback_selected)
        if fallback_ready:
            st.info("直接アップロードHTMLを使用して予想します。")

    st.subheader("予想")
    can_predict = fallback_ready or bool(race_id)
    if st.button("予想する", disabled=not can_predict, type="primary", use_container_width=True):
        clear_prediction_state(keep_input=True)
        if fallback_ready:
            result, png_bytes = run_upload_prediction_with_progress(
                "nar",
                fallback_selected,
                fallback_grouped,
            )
        else:
            result, png_bytes = run_nar_url_prediction_with_progress(race_id or "", specs)
        if result is not None and png_bytes is not None:
            st.session_state.prediction_result = result
            st.session_state.png_bytes = png_bytes


def render_upload_flow(mode: RaceMode) -> None:
    current_input_signature = f"{mode}:upload"
    if st.session_state.input_signature != current_input_signature:
        clear_prediction_state()
        st.session_state.input_signature = current_input_signature

    st.subheader("中央データ追加" if mode == "jra" else "HTML追加")
    if mode == "jra":
        st.caption("iPhone Safariで保存した中央競馬HTMLをまとめて選択してください。")
        st.caption("タイム指数 / 競馬新聞 / 脚質分析が必須です。調教HTMLは任意で反映します。")
    selected, grouped, has_uploads, missing, validation = render_upload_input(mode, key_prefix=mode)

    st.subheader("予想")
    can_predict = has_uploads and not missing and validation.is_valid and bool(selected)
    if st.button("予想する", disabled=not can_predict, type="primary", use_container_width=True):
        clear_prediction_state(keep_input=True)
        result, png_bytes = run_upload_prediction_with_progress(mode, selected, grouped)
        if result is not None and png_bytes is not None:
            st.session_state.prediction_result = result
            st.session_state.png_bytes = png_bytes


def render_upload_input(
    mode: RaceMode,
    key_prefix: str,
) -> tuple[
    dict[str, ClassifiedHtml],
    dict[str, list[ClassifiedHtml]],
    bool,
    list[str],
    UploadBundleValidation,
]:
    uploader_label = "iPhoneショートカットで保存した中央競馬ファイルを選択" if mode == "jra" and key_prefix == "jra" else "HTMLを直接アップロード"
    uploaded_files = st.file_uploader(
        uploader_label,
        type=["html", "htm"],
        accept_multiple_files=True,
        help="必要なHTMLをまとめて選択してください。内容から自動判定します。",
        key=f"html_upload_{key_prefix}_{st.session_state.uploader_key}",
    )

    grouped: dict[str, list[ClassifiedHtml]] = {}
    has_uploads = bool(uploaded_files)
    if uploaded_files:
        grouped = classify_many([(file.name, file.getvalue()) for file in uploaded_files], mode)
    validation = validate_upload_bundle(grouped, mode)

    st.markdown("#### 認識結果")
    allow_expanders = "fallback" not in key_prefix
    selected = render_recognition(
        grouped,
        mode,
        allow_expanders=allow_expanders,
        key_prefix=key_prefix,
    )
    missing = [kind for kind in required_kinds(mode) if kind not in selected]

    if not uploaded_files:
        st.info("HTMLを追加してください。")
    elif missing:
        for kind in missing:
            st.markdown(
                f'<div class="ka-card"><span class="ka-ng">× {kind_label(kind)}HTMLが不足しています</span></div>',
                unsafe_allow_html=True,
            )
    elif selected and validation.is_valid:
        st.success("必要なHTMLが揃いました。")

    if validation.race_id and validation.detected_mode:
        st.caption(
            f"検証済み: race_id={validation.race_id} / {validation.detected_mode.upper()}"
        )
    for message in validation.errors:
        st.error(message)
    for message in validation.warnings:
        st.warning(message)

    render_unknown_files(grouped, allow_expander=allow_expanders)
    return selected, grouped, has_uploads, missing, validation


def render_recognition(
    grouped: dict[str, list[ClassifiedHtml]],
    mode: RaceMode,
    allow_expanders: bool = True,
    key_prefix: str = "upload",
) -> dict[str, ClassifiedHtml]:
    selected: dict[str, ClassifiedHtml] = {}
    if not grouped:
        return selected

    for kind in DISPLAY_ORDER[mode]:
        candidates = grouped.get(kind, [])
        label = kind_label(kind)
        if not candidates:
            continue
        if len(candidates) == 1:
            item = candidates[0]
            selected[kind] = item
            render_recognized_item(label, item)
            continue

        st.markdown(
            f'<div class="ka-card"><span class="ka-ng">! {label}</span><br>'
            f'同じ種類のHTMLが{len(candidates)}件あります。自動上書きしません。</div>',
            unsafe_allow_html=True,
        )
        options = list(range(len(candidates)))
        chosen_index = st.radio(
            f"{label}HTMLを選択",
            options=options,
            format_func=lambda index: (
                f"{index + 1}. {candidates[index].file_name} "
                f"(race_id={candidates[index].meta.race_id or '未確認'})"
            ),
            key=f"{key_prefix}_{mode}_{kind}_duplicate",
            label_visibility="visible",
        )
        selected[kind] = candidates[chosen_index]

    extra_kinds = [
        kind
        for kind in grouped
        if kind not in set(DISPLAY_ORDER[mode]) | {"unknown"}
    ]
    if extra_kinds and allow_expanders:
        with st.expander("任意HTML / 今回は補助として使用", expanded=False):
            for kind in extra_kinds:
                for item in grouped[kind]:
                    st.write(f"{kind_label(kind)}: {item.file_name}")
    elif extra_kinds:
        st.markdown("任意HTML / 今回は補助として使用")
        for kind in extra_kinds:
            for item in grouped[kind]:
                st.write(f"{kind_label(kind)}: {item.file_name}")

    return selected


def render_recognized_item(label: str, item: ClassifiedHtml) -> None:
    reason = item.reasons[0] if item.reasons else "分類条件に一致"
    file_name = html.escape(item.file_name)
    reason_text = html.escape(reason)
    st.markdown(
        f"""
        <div class="ka-card">
          <span class="ka-ok">✓ {label}</span>
          <div class="ka-file">{file_name}</div>
          <div class="ka-muted">{reason_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_unknown_files(grouped: dict[str, list[ClassifiedHtml]], allow_expander: bool = True) -> None:
    unknowns = grouped.get("unknown", [])
    if allow_expander:
        with st.expander("不明なHTML（解析しません）", expanded=False):
            if unknowns:
                for item in unknowns:
                    st.write(item.file_name)
            else:
                st.write("なし")
        return

    st.markdown("不明なHTML（解析しません）")
    if unknowns:
        for item in unknowns:
            st.write(item.file_name)
    else:
        st.write("なし")


def clear_prediction_state(keep_input: bool = False) -> None:
    st.session_state.prediction_result = None
    st.session_state.png_bytes = None
    st.session_state.fetch_failures = []
    st.session_state.fetch_race_id = ""
    if not keep_input:
        st.session_state.input_signature = ""


def extract_race_id(value: str) -> str:
    text = clean_text(value)
    if re.fullmatch(r"\d{10,14}", text):
        return text

    try:
        parsed = urlparse(text)
        query_race_ids = parse_qs(parsed.query).get("race_id", [])
        for candidate in query_race_ids:
            if re.fullmatch(r"\d{10,14}", candidate):
                return candidate
    except ValueError:
        pass

    match = re.search(r"race_id=(\d{10,14})", text)
    return match.group(1) if match else ""


def build_nar_generated_url_specs(race_id: str) -> list[GeneratedHtmlSpec]:
    return [
        GeneratedHtmlSpec(
            "shutuba",
            kind_label("shutuba"),
            f"https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}",
        ),
        GeneratedHtmlSpec(
            "speed",
            kind_label("speed"),
            f"https://nar.netkeiba.com/race/speed.html?race_id={race_id}",
        ),
        GeneratedHtmlSpec(
            "style",
            kind_label("style"),
            f"https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=1",
        ),
        GeneratedHtmlSpec(
            "jockey",
            kind_label("jockey"),
            f"https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=2",
            required=False,
        ),
    ]


def render_generated_url_cards(specs: list[GeneratedHtmlSpec]) -> None:
    for spec in specs:
        label = html.escape(spec.label)
        url = html.escape(spec.url)
        required = "必須" if spec.required else "任意"
        st.markdown(
            f"""
            <div class="ka-card">
              <span class="ka-ok">✓ {label}URLを生成しました</span>
              <div class="ka-muted">{required}</div>
              <div class="ka-file">{url}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_fetch_failures(failures: list[dict[str, str]]) -> None:
    st.error("取得できなかったURLがあります。")
    for failure in failures:
        label = html.escape(failure.get("label", "HTML"))
        reason = html.escape(failure.get("reason", "取得失敗"))
        st.markdown(
            f"""
            <div class="ka-card">
              <span class="ka-ng">× {label}: {reason}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def fetch_generated_html(
    specs: list[GeneratedHtmlSpec],
    race_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    html_files: dict[str, str] = {}
    file_names: dict[str, str] = {}
    failures: list[dict[str, str]] = []

    for spec in specs:
        try:
            response = requests.get(
                spec.url,
                headers=REQUEST_HEADERS,
                timeout=FETCH_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                failures.append(
                    {
                        "label": spec.label,
                        "url": spec.url,
                        "reason": f"HTTP {response.status_code}",
                    }
                )
                continue
            if response.apparent_encoding:
                response.encoding = response.apparent_encoding
            html_text = response.text or ""
            if not html_text.strip():
                failures.append(
                    {
                        "label": spec.label,
                        "url": spec.url,
                        "reason": "HTML本文が空です",
                    }
                )
                continue
            invalid_reason = validate_fetched_nar_html(spec, html_text, race_id)
            if invalid_reason:
                failures.append(
                    {
                        "label": spec.label,
                        "url": spec.url,
                        "reason": invalid_reason,
                    }
                )
                continue
            html_files[spec.kind] = html_text
            file_names[spec.kind] = f"{spec.label}_{race_id}.html"
        except requests.RequestException as exc:
            failures.append(
                {
                    "label": spec.label,
                    "url": spec.url,
                    "reason": str(exc),
                }
            )

    required_missing = [failure for failure in failures if _is_required_failure(failure, specs)]
    if required_missing:
        raise HtmlFetchError(required_missing)
    return html_files, file_names


def validate_fetched_nar_html(spec: GeneratedHtmlSpec, html_text: str, race_id: str) -> str:
    text = html_text or ""
    head = text[:160_000]
    if not text.strip():
        return "HTML本文が空です"
    if looks_like_login_page(head):
        return "ログインページが返されました"
    if not fetched_page_matches_race_id(head, race_id):
        return "入力race_idと取得ページのrace_idが一致しません"

    classified = classify_html(spec.url, text, "nar")
    if classified.kind == spec.kind:
        return ""
    if spec.kind in classified.all_matches:
        return ""
    if has_required_nar_page_marker(spec.kind, text):
        return ""
    return "必要なテーブルを取得できませんでした"


def looks_like_login_page(html_text: str) -> bool:
    text = html_text or ""
    lower = text.lower()
    title = simple_title(text)
    if "ログイン" in title or "login" in title.lower():
        return True
    login_markers = (
        'id="login',
        "id='login",
        "loginform",
        "login_form",
        "/account/login",
        "/login?return_url",
    )
    return any(marker in lower for marker in login_markers)


def fetched_page_matches_race_id(html_text: str, race_id: str) -> bool:
    text = html_text or ""
    head_refs = []
    for pattern in (
        r"""<link\b[^>]*rel\s*=\s*['"][^'"]*canonical[^'"]*['"][^>]*>""",
        r"""<meta\b[^>]*(?:property|name)\s*=\s*['"]og:url['"][^>]*>""",
    ):
        head_refs.extend(re.findall(pattern, text, flags=re.I | re.S))
    ids: list[str] = []
    for ref in head_refs:
        ids.extend(re.findall(r"race_id=(\d{10,14})", ref))
    if ids:
        return race_id in ids
    return race_id in text[:300_000]


def has_required_nar_page_marker(kind: str, html_text: str) -> bool:
    text = html_text or ""
    if kind == "jockey":
        normalized = html.unescape(text).lower()
        return bool(
            "mode=courseanalysis" in normalized
            and re.search(r"(?:[?&])cid=2(?:\D|$)", normalized)
            and "table_sort_back" in normalized
            and "複勝率" in text
            and "出走" in text
        )
    markers_by_kind = {
        "shutuba": (
            "Shutuba_Table",
            "RaceTable_Shutuba",
            "NAR_RaceTable",
            "馬番",
            "馬名",
            "斤量",
        ),
        "newspaper": (
            "newspaper.html",
            "競馬新聞",
            "NewsPaper",
            "RaceNewspaper",
            "HorseList",
            "Jockey",
        ),
        "speed": (
            "Speed_List",
            "SpeedIndex_Table",
            "タイム指数",
            "指数",
        ),
        "style": (
            "mode=courseanalysis",
            "CourseAnalysis",
            "RaceData_CourseAnalysis",
            "有利な脚質",
            "脚質傾向",
        ),
    }
    markers = markers_by_kind.get(kind, ())
    return any(marker in text for marker in markers)


def simple_title(html_text: str) -> str:
    match = re.search(r"<title\b[^>]*>(.*?)</title>", html_text or "", flags=re.I | re.S)
    if not match:
        return ""
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", html.unescape(title)).strip()


def _is_required_failure(failure: dict[str, str], specs: list[GeneratedHtmlSpec]) -> bool:
    failed_url = failure.get("url", "")
    return any(spec.url == failed_url and spec.required for spec in specs)


def render_fetch_success(html_files: dict[str, str]) -> None:
    with st.expander("取得したHTML", expanded=False):
        for kind, html_text in html_files.items():
            st.write(f"{kind_label(kind)}: {len(html_text):,}文字")


def run_nar_json_prediction_with_progress(
    package: NarJsonPredictionInput,
) -> tuple[PredictionResult | None, bytes | None]:
    progress = st.progress(0)
    status = st.empty()

    def step(percent: int, message: str) -> None:
        progress.progress(percent)
        status.write(message)

    try:
        step(15, "1. JSON確認中")
        step(35, "2. AI入力データ整理中")
        html_files = dict(package.html_files)
        file_names = dict(package.file_names)
        step(55, "3. AI予想中")
        result = run_prediction("nar", html_files, file_names)
        step(72, "4. 結果整理中")
        validate_result(result)
        step(88, "5. PNG生成中")
        png_bytes = render_mobile_png(result)
        step(100, "6. 完了")
        st.success("スマホ用PNGを生成しました。")
        return result, png_bytes
    except MobilePngRenderError as exc:
        progress.empty()
        status.empty()
        st.error(f"PNG生成に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"予想処理に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None


def run_nar_url_prediction_with_progress(
    race_id: str,
    specs: list[GeneratedHtmlSpec],
) -> tuple[PredictionResult | None, bytes | None]:
    progress = st.progress(0)
    status = st.empty()

    def step(percent: int, message: str) -> None:
        progress.progress(percent)
        status.write(message)

    try:
        st.session_state.fetch_failures = []
        st.session_state.fetch_race_id = race_id
        step(10, "1. URL確認中")
        step(25, "2. HTML取得中")
        html_files, file_names = fetch_generated_html(specs, race_id)
        render_fetch_success(html_files)
        step(45, "3. AI予想中")
        result = run_prediction("nar", html_files, file_names)
        step(60, "4. 結果整理中")
        validate_result(result)
        step(80, "5. PNG生成中")
        png_bytes = render_mobile_png(result)
        step(100, "6. 完了")
        st.success("スマホ用PNGを生成しました。")
        return result, png_bytes
    except MobilePngRenderError as exc:
        progress.empty()
        status.empty()
        st.error(f"PNG生成に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None
    except HtmlFetchError as exc:
        progress.empty()
        status.empty()
        st.session_state.fetch_failures = exc.failures
        st.session_state.fetch_race_id = race_id
        render_fetch_failures(exc.failures)
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"予想処理に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None


def run_upload_prediction_with_progress(
    mode: RaceMode,
    selected: dict[str, ClassifiedHtml],
    grouped: dict[str, list[ClassifiedHtml]],
) -> tuple[PredictionResult | None, bytes | None]:
    progress = st.progress(0)
    status = st.empty()

    def step(percent: int, message: str) -> None:
        progress.progress(percent)
        status.write(message)

    try:
        step(20, "1. HTML整理中")
        html_files = {kind: item.html_text for kind, item in selected.items()}
        file_names = {kind: item.file_name for kind, item in selected.items()}
        step(45, "2. AI予想中")
        result = run_prediction(mode, html_files, file_names)
        step(65, "3. 結果整理中")
        validate_result(result)
        step(85, "4. PNG生成中")
        png_bytes = render_mobile_png(result)
        step(100, "5. 完了")
        st.success("スマホ用PNGを生成しました。")
        return result, png_bytes
    except MobilePngRenderError as exc:
        progress.empty()
        status.empty()
        st.error(f"PNG生成に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"予想処理に失敗しました: {exc}")
        with st.expander("開発者向け詳細", expanded=False):
            st.code(traceback.format_exc())
        return None, None


def run_prediction(
    mode: RaceMode,
    html_files: dict[str, str],
    file_names: dict[str, str],
    prediction_logic_version: str | None = None,
) -> PredictionResult:
    version = prediction_logic_version
    if version is None:
        version = st.session_state.get("prediction_logic_version", "market")
    version = normalize_prediction_logic_version(version)
    return predict_from_html_inputs(
        mode,
        html_files,
        file_names,
        prediction_logic_version=version,
    )
def validate_result(result: PredictionResult) -> None:
    if result.status != "ok":
        raise RuntimeError(result.message or "PredictionResultが正常状態ではありません。")
    if result.overall_table is None:
        raise RuntimeError("レース全体表が取得できませんでした。")
    if result.horse_evaluation is None:
        raise RuntimeError("馬評価が取得できませんでした。")


OVERALL_DETAIL_COLUMNS = [
    "表示印",
    "展開印",
    "馬番",
    "馬名",
    "馬年齢",
    "斤量",
    "騎手",
    "オッズ",
    "脚質",
    "レース間隔",
    "AI点",
    "総合評価",
    "市場反映勝率",
    "単勝期待値",
    "クラス変動",
    "クラス根拠",
    "馬場実績",
    "距離指数",
    "コース指数",
    "3走前",
    "2走前",
    "前走",
    "平均指数",
    "過去1年最高指数",
    "★最高指数",
    "★該当走",
    "★条件",
    "★最高指数の取得元",
    "評価／検討材料",
]

OVERALL_SIMPLE_COLUMNS = [
    "表示印",
    "展開印",
    "馬番",
    "馬名",
    "騎手",
    "オッズ",
    "脚質",
    "能力評価値",
    "能力ランク",
    "勢いランク",
    "近3走傾向",
    "能力帯",
    "総合評価",
    "評価／検討材料",
]

HORSE_EVALUATION_COLUMNS = [
    "馬番",
    "印",
    "表示印",
    "馬名",
    "馬年齢",
    "騎手",
    "脚質",
    "単勝オッズ",
    "斤量詳細",
    "騎手詳細",
    "能力評価値",
    "能力ランク",
    "勢いランク",
    "能力帯",
    "市場評価",
    "クラス変動",
    "対戦評価",
    "調教評価",
    "厩舎コメント",
    "評価／検討材料",
    "馬タイプ",
    "穴候補",
    "注意馬",
    "チェック項目",
    "補足",
    "一言コメント",
]

AUDIT_EVALUATION_COLUMNS = [
    "馬番",
    "馬名",
    "旧AI点",
    "old_ai_score",
    "raw_score",
    "能力評価値",
    "ability_display_score",
    "正規化AI点",
    "normalized_ai_score",
    "AI順位",
    "ai_rank",
    "旧印",
    "old_final_mark",
    "総合評価監査点",
    "final_mark_score",
    "市場評価点",
    "market_score",
    "軸信頼度",
    "axis_confidence",
    "軸信頼度理由",
    "axis_confidence_reason",
    "能力帯",
    "ability_band",
    "能力ランク",
    "ability_rank",
    "能力ランク理由",
    "ability_rank_reason",
    "勢いスコア",
    "momentum_score",
    "勢いランク",
    "momentum_rank",
    "勢い理由",
    "momentum_reason",
    "近3走傾向",
    "recent3_trend",
    "recent3_slope",
    "recent3_volatility",
    "recent3_valid_count",
    "総合ランク",
    "overall_rank",
    "総合ランク理由",
    "overall_rank_reason",
    "勢力図グループ",
    "power_group",
    "勢力図役割",
    "power_group_label",
    "能力差",
    "ability_gap_level",
    "レース難易度",
    "race_difficulty",
    "レース難易度理由",
    "race_difficulty_reason",
    "表示コメント",
    "display_comment",
    "表示印",
    "display_mark",
    "脚質",
    "脚質表示",
    "running_style_display",
    "旧✓",
    "old_watch_mark",
    "穴候補",
    "hole_candidate",
    "注意馬",
    "watch_horse",
    "has_same_course",
    "has_same_distance",
    "has_same_turn",
    "has_heavy_track",
    "チェック項目",
    "check_summary",
    "補足",
    "supplement_note",
    "horse_score_v4",
    "race_rank_v4",
    "base_ability_score",
    "condition_score",
    "jockey_score",
    "age_weight_score",
    "training_score",
    "momentum_score_v4",
    "race_shape_score",
    "condition_fit_mark",
    "condition_fit_level",
    "condition_matched_quality",
    "group_v4",
    "mark_v4",
    "warning_reason",
    "positive_reasons_v4",
    "negative_reasons_v4",
    "watch_reason_v4",
    "axis_score",
    "axis_confidence_v4",
    "ticket_candidate_score",
    "opponent_eligible_v4",
    "opponent_veto_reason_v4",
]


def render_result_area(result: PredictionResult, png_bytes: bytes) -> None:
    investment_decision = render_colab_style_result(result)
    render_audit_details(result)
    render_nar_previous_jockey_result_trace(result)
    render_nar_star_result_trace(result)

    st.divider()
    if getattr(result, "logic_version", "v3") == "market":
        with st.expander("旧評価の互換PNG", expanded=False):
            st.caption("比較モードの主画面は上の能力帯×価格・全頭表・カードです。このPNGは旧評価の研究互換用です。")
            st.image(png_bytes, use_container_width=True)
            st.download_button(
                "互換PNGを保存",
                data=png_bytes,
                file_name=make_download_file_name(result),
                mime="image/png",
                use_container_width=True,
            )
    else:
        st.subheader("スマホ用PNG")
        st.image(png_bytes, use_container_width=True)
        st.download_button(
            "PNGを保存",
            data=png_bytes,
            file_name=make_download_file_name(result),
            mime="image/png",
            use_container_width=True,
        )
    st.download_button(
        "予想結果ファイル出力",
        data=prediction_zip_bytes(result, investment_decision),
        file_name=prediction_zip_filename(result),
        mime="application/zip",
        use_container_width=True,
    )
    if getattr(result, "logic_version", "v3") == "practical":
        if st.button("予想を固定保存（100R検証）", use_container_width=True):
            saved_path = save_prediction_history(result, investment_decision)
            fixed_path = freeze_practical_prediction(result, investment_decision)
            st.success(f"予想を変更不可の状態で固定しました: {fixed_path}")
            st.caption(f"通常履歴: {saved_path}")
        render_practical_validation_status(result)
    elif getattr(result, "logic_version", "v3") == "market":
        if st.button("比較データを固定保存", use_container_width=True):
            fixed_path = freeze_market_prediction(result)
            st.success(f"能力・価格・条件・展開とユーザー選択を固定しました: {fixed_path}")
            st.caption("確定結果はprediction.jsonへ混ぜず、別フェーズで保存してください。")
    elif st.button("予想履歴をローカル保存", use_container_width=True):
        saved_path = save_prediction_history(result, investment_decision)
        st.success(f"予想履歴を保存しました: {saved_path}")

    with st.expander("PredictionResult簡易確認", expanded=False):
        st.write(
            {
                "version": result.version,
                "created_at": result.created_at,
                "mode": result.race_mode,
                "race_name": result.race_name,
                "status": result.status,
                "logic_version": getattr(result, "logic_version", "v3"),
            }
        )

    if st.button("次のレースを予想", use_container_width=True):
        st.session_state.prediction_result = None
        st.session_state.png_bytes = None
        st.session_state.fetch_failures = []
        st.session_state.fetch_race_id = ""
        st.session_state.url_input_key += 1
        st.rerun()


def render_practical_validation_status(result: PredictionResult) -> None:
    summary = practical_validation_summary()
    overall = (summary.get("scopes") or {}).get("ALL", {})
    st.markdown(
        '<div class="ka-dashboard-card">'
        '<div class="ka-dashboard-title">新規100R 固定検証</div>'
        f'<div class="ka-dashboard-value">{int(summary.get("prediction_count") or 0)} / 100R 固定済み</div>'
        f'<div class="ka-note">結果照合 {int(summary.get("settled_count") or 0)}R / '
        f'BUY {int(overall.get("buy_count") or 0)}R / '
        f'投資額 {int(overall.get("investment_yen") or 0):,}円 / '
        f'払戻額 {int(overall.get("payout_yen") or 0):,}円 / '
        f'収支 {int(overall.get("profit_yen") or 0):+,}円 / '
        f'回収率 {format_rate(overall.get("return_rate"))}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    with st.expander("レース終了後のresult.json照合", expanded=False):
        st.caption("先に予想を固定保存してください。結果はprediction.jsonへ上書きせず別ファイルで照合します。")
        uploaded = st.file_uploader(
            "確定着順・単勝払戻を含むresult.json",
            type=["json"],
            accept_multiple_files=False,
            key="practical_result_json",
        )
        if uploaded is not None and st.button("固定予想へ結果を照合", use_container_width=True):
            try:
                payload = json.loads(uploaded.getvalue().decode("utf-8-sig"))
                race_id = clean_text(payload.get("race_id")) or clean_text((result.race_info or {}).get("race_id"))
                settled_path = settle_practical_result(race_id, payload)
                st.success(f"結果を照合しました: {settled_path}")
                st.rerun()
            except Exception as exc:
                st.error(f"結果照合に失敗しました: {exc}")


def format_rate(value: Any) -> str:
    number = to_float(value)
    return "—" if number is None else f"{number:.1f}%"


def render_nar_previous_jockey_result_trace(result: PredictionResult) -> None:
    if result.race_mode != "nar":
        return
    rows = list((getattr(result, "debug_info", {}) or {}).get("nar_previous_jockey_trace", []) or [])
    if not rows:
        return
    with st.expander("地方前走騎手診断（PredictionResult・表示直前）", expanded=False):
        st.caption("PredictionResult作成時の内部列と、app.pyカード表示が参照する騎手詳細です。")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_nar_star_result_trace(result: PredictionResult) -> None:
    if result.race_mode != "nar":
        return
    rows = list((getattr(result, "debug_info", {}) or {}).get("nar_star_trace", []) or [])
    if not rows:
        return
    with st.expander("地方★最高指数診断（予想処理〜表示直前）", expanded=False):
        st.caption("parse_nar_speed_table、star_index.py、add_scores_and_comments、PredictionResult、app.py、PNGの値の流れです。")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_colab_style_result(result: PredictionResult) -> Any:
    if getattr(result, "logic_version", "v3") == "market":
        render_market_compare_result(result)
        return None
    render_race_header(result)
    render_race_summary(result)
    render_power_map(result)
    render_horse_summary_cards(result)
    render_backtest_reference(result)
    render_race_flow(result)
    investment_decision = render_investment_decision(result)
    render_overall_table(result)
    with st.expander("監査・補足情報", expanded=False):
        render_raw_text_section(
            "会場別試験評価",
            extract_raw_section(result, ["会場別試験評価", "JRA会場別試験評価"]),
        )
        render_raw_text_section(
            "展開予想",
            extract_raw_section(result, ["展開予想"]),
        )
    return investment_decision


def render_market_compare_result(result: PredictionResult) -> None:
    """Human-decision-first view: ability, price, conditions, and pace."""

    render_race_header(result)
    table = market_source_table(result)
    if table.empty:
        st.info("能力×価格比較に必要な全頭データを取得できませんでした。")
        return
    st.caption(
        "能力はVer3の6項目（近3走平均15%・★最高30%・近3走最高20%・前走15%・距離10%・コース10%）だけ。"
        "オッズ・人気・騎手・斤量・間隔・展開/コース・＋－材料では能力値・順位・帯を動かしません。"
    )
    render_market_race_facts(result, table)
    if clean_text(result.race_mode).lower() == "nar":
        render_nar_race_diagnostics(table, result.race_mode, race_info=getattr(result, "race_info", {}) or {}, layout="mobile")
    else:
        render_jra_race_diagnostics(table, result.race_mode)
    render_full_field_comparison(table, result.race_mode)
    with st.expander("馬別コンパクトカードを見る", expanded=False):
        render_market_horse_cards(table, result.race_mode)
    with st.expander("研究買いガイド（参考）", expanded=False):
        render_market_research_bet(table, result.race_mode, context="mobile")
    with st.expander("従来の全頭表を見る", expanded=False):
        render_market_full_table(table, result.race_mode)
    render_market_user_selection(result, table)
    render_market_audit_details(result, table)


def market_source_table(result: PredictionResult) -> pd.DataFrame:
    for table in (result.overall_table, result.horse_evaluation):
        if isinstance(table, pd.DataFrame) and not table.empty and "ability_band_v2" in table.columns:
            merged = merge_market_display_supplements(table.copy(), result)
            return attach_ability_watch_columns(merged, race_mode=getattr(result, "race_mode", "jra"))
    return pd.DataFrame()


MARKET_DISPLAY_SUPPLEMENT_COLUMNS = (
    "騎手詳細",
    "jockey_detail",
    "騎手継続/乗替",
    "jockey_change",
    "_display_previous_jockey",
    "_previous_jockey",
    "前走騎手",
    "previous_jockey",
    "_display_current_jockey",
    "_current_jockey",
    "jockey_display_market",
    "_jockey_course_win_rate",
    "_jockey_course_quinella_rate",
    "_jockey_course_place_rate",
    "_jockey_course_starts",
    "_jockey_course_condition",
    "_jockey_course_source",
    "jockey_course_place_rate",
    "騎手コース複勝率",
    "jockey_course_stats_market",
    "jockey_course_sample_market",
    "_display_current_load_weight",
    "_current_load_weight",
    "_display_previous_load_weight",
    "_previous_load_weight",
    "_display_load_weight_change",
    "_load_weight_change",
    "斤量詳細",
    "weight_detail",
    "★最高指数",
    "star_max_index",
    "★最高",
)


def merge_market_display_supplements(table: pd.DataFrame, result: PredictionResult) -> pd.DataFrame:
    """Fill display-only fields from the sibling prediction table by horse number."""

    merged = table.copy()
    sources = [getattr(result, "overall_table", None), getattr(result, "horse_evaluation", None)]
    for source in sources:
        if source is None or not isinstance(source, pd.DataFrame) or source.empty or source is table:
            continue
        supplemental = {
            horse_no(pick(row, "馬番", "馬", "horse_no", "horse_number")): row
            for row in source.to_dict("records")
        }
        for index, row in merged.iterrows():
            key = horse_no(pick(row.to_dict(), "馬番", "馬", "horse_no", "horse_number"))
            if not key or key not in supplemental:
                continue
            extra = supplemental[key]
            for column in MARKET_DISPLAY_SUPPLEMENT_COLUMNS:
                if column not in extra:
                    continue
                if column not in merged.columns:
                    merged[column] = pd.Series([None] * len(merged), index=merged.index, dtype="object")
                current_value = merged.at[index, column]
                extra_value = extra[column]
                prefer_jockey_rate = (
                    column == "jockey_display_market"
                    and "複" not in clean_text(current_value)
                    and "複" in clean_text(extra_value)
                )
                prefer_real_jockey_stats = (
                    column == "jockey_course_stats_market"
                    and clean_text(current_value) in {"", "騎手成績なし", "取得不能"}
                    and clean_text(extra_value) not in {"", "騎手成績なし", "取得不能"}
                )
                if is_missing_value(current_value) or prefer_jockey_rate or prefer_real_jockey_stats:
                    merged.at[index, column] = extra[column]
    return merged


def render_market_band_prices(table: pd.DataFrame) -> None:
    st.subheader("能力帯 × 単勝オッズ")
    rows_by_band = price_band_rows(table)
    blocks = []
    for band in ("AA", "A", "B", "C", "Z"):
        horse_bits = []
        for item in rows_by_band.get(band, []):
            odds = "—" if item.get("odds") is None else f"{float(item['odds']):.1f}倍"
            horse_bits.append(
                '<span class="ka-market-price">'
                f"{plain_text_to_html(item.get('horse_no') or '—')} {plain_text_to_html(odds)}"
                "</span>"
            )
        body = "".join(horse_bits) or '<span class="ka-muted">該当なし</span>'
        blocks.append(
            '<div class="ka-market-band">'
            f'<div class="ka-market-band-label">{band}</div><div>{body}</div>'
            "</div>"
        )
    st.markdown('<div class="ka-dashboard-card">' + "".join(blocks) + "</div>", unsafe_allow_html=True)
    st.caption("帯内はオッズ順です。価格差を数値で示すだけで、買い・VALUE等の判定は行いません。")


def render_market_race_facts(result: PredictionResult, table: pd.DataFrame) -> None:
    st.subheader("レースの事実整理")
    all_debug = getattr(result, "debug_info", {}) or {}
    debug = (all_debug.get("market_compare") or {})
    summary = list(debug.get("race_summary") or build_market_race_summary(table))
    st.markdown(
        '<div class="ka-dashboard-card">' + "<br>".join(plain_text_to_html(line) for line in summary) + "</div>",
        unsafe_allow_html=True,
    )
    course = all_debug.get("course_materials") if isinstance(all_debug.get("course_materials"), dict) else {}
    pace = debug.get("pace") or race_pace_snapshot(table)
    horses = pace.get("horses") or {}
    counts = pace.get("counts") or {}
    provider_pace = clean_text(course.get("pace"))
    pace_label = {"H": "ハイペース", "M": "平均ペース", "S": "スローペース"}.get(provider_pace, "")
    front_count = int(counts.get("逃", 0)) + int(counts.get("先", 0))
    course_lines: list[str] = []
    condition = clean_text(course.get("course_condition"))
    if condition:
        course_lines.append(condition)
    if pace_label:
        course_lines.append(f"想定：{pace_label}")
    else:
        course_lines.append(f"想定：{clean_text(pace.get('scenario')) or '判定保留'}")
    if front_count >= 3:
        course_lines.append("先行馬多数")
        if provider_pace == "H":
            course_lines.append("→ 前半は流れやすく、差し馬に展開利の可能性")
    favorable = clean_text(course.get("favorable_position_label"))
    if favorable:
        course_lines.append(f"4角傾向：{favorable}")
    favorite_numbers = [str(item.get("horse_number")) for item in course.get("favorable_horses", []) if item.get("horse_number")]
    if favorite_numbers:
        course_lines.append("推定有利馬：" + "・".join(favorite_numbers))
    st.markdown(
        '<div class="ka-section"><b>今回のコース/展開</b><br>'
        + "<br>".join(plain_text_to_html(line) for line in course_lines)
        + "</div>",
        unsafe_allow_html=True,
    )
    if result.race_mode == "nar":
        st.caption("NAR Ver4：能力順位を最終印に採用")


def render_nar_race_diagnostics(
    table: pd.DataFrame,
    race_mode: str,
    *,
    race_info: dict[str, Any] | None = None,
    layout: str = "mobile",
) -> None:
    diagnostics = build_nar_race_diagnostics(
        table.to_dict("records"),
        race_mode=race_mode,
        race_info=race_info or {},
    )
    if not diagnostics.get("show"):
        return
    st.subheader("🔍 AIレース診断")
    summary = diagnostics.get("summary") if isinstance(diagnostics.get("summary"), dict) else {}
    summary_lines = [
        f"想定ペース：{clean_text(diagnostics.get('pace')) or '—'}",
        f"勝ち候補：{nar_summary_text(summary.get('win_candidates'))}",
        f"4角前方：{nar_summary_text(summary.get('front_at_4c'))}",
        f"相手本線：{nar_summary_text(summary.get('main_partners'))}",
        f"能力外警戒：{nar_summary_text(summary.get('ability_outside_watch'))}",
        f"データ不足警戒：{nar_summary_text(summary.get('data_insufficient_watch'))}",
    ]
    st.markdown(
        '<div class="ka-dashboard-card">'
        + "<br>".join(plain_text_to_html(line) for line in summary_lines)
        + '<div class="ka-note">研究中の診断です。購入条件ではありません。</div>'
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(nar_diagnostic_unified_html(diagnostics), unsafe_allow_html=True)
    render_nar_position_flow(diagnostics, layout=layout)


def render_jra_race_diagnostics(table: pd.DataFrame, race_mode: str) -> None:
    if clean_text(race_mode).lower() != "jra":
        return
    rows = table.to_dict("records")
    labels: list[str] = []
    warnings: list[str] = []
    for row in rows:
        top_label = clean_text(pick(row, "ability_top_match_label"))
        if top_label:
            labels.append(top_label)
        warning = clean_text(pick(row, "ability_unmarked_warning"))
        if warning:
            horse = join_nonempty([horse_no(pick(row, "馬番", "馬")), pick(row, "馬名")], sep=" ")
            warnings.append(f"{horse}：{warning}")
    if not labels and not warnings:
        return
    body: list[str] = []
    if labels:
        body.append("能力1位確認：" + " / ".join(unique_nonempty(labels)))
    if warnings:
        body.append("既存alert：" + "<br>".join(plain_text_to_html(line) for line in warnings))
    st.subheader("🔍 AIレース診断")
    st.markdown(
        '<div class="ka-dashboard-card">'
        + "<br>".join(line if "<br>" in line else plain_text_to_html(line) for line in body)
        + '<div class="ka-note">保存済みのJRA alertを表示しています。印・評価は変更しません。</div>'
        + "</div>",
        unsafe_allow_html=True,
    )


def nar_summary_text(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "—"
    return " / ".join(clean_text(value) for value in values if clean_text(value)) or "—"


def nar_diagnostic_card_html(
    title: str,
    horses: list[dict[str, Any]],
    category: str,
    empty_text: str,
    *,
    include_title: bool = True,
) -> str:
    blocks = []
    if include_title:
        blocks.append(f'<div class="ka-nar-diagnostic-title">{plain_text_to_html(title)}</div>')
    if not horses:
        blocks.append(f'<div class="ka-nar-diagnostic-item ka-muted">{plain_text_to_html(empty_text)}</div>')
    for horse in horses:
        reason = category_reason(horse, category)
        blocks.append(
            '<div class="ka-nar-diagnostic-item">'
            f'<b>{plain_text_to_html(diagnostic_line(horse))}</b>'
            + (f'<br><span class="ka-muted">{plain_text_to_html(reason)}</span>' if reason else "")
            + "</div>"
        )
    return f'<div class="ka-nar-diagnostic-card {category}">' + "".join(blocks) + "</div>"


def nar_diagnostic_unified_html(diagnostics: dict[str, Any]) -> str:
    category_sets = {
        "勝ち候補": {clean_text(horse.get("number")) for horse in diagnostics.get("win_candidates") or []},
        "相手本線": {clean_text(horse.get("number")) for horse in diagnostics.get("main_partners") or []},
        "4角前": {clean_text(horse.get("number")) for horse in diagnostics.get("pace_watch") or []},
        "能力外警戒": {clean_text(horse.get("number")) for horse in diagnostics.get("ability_outside_watch") or []},
        "データ不足": {clean_text(horse.get("number")) for horse in diagnostics.get("data_insufficient_watch") or []},
    }
    horses = diagnostics.get("horses") or []
    rows: list[str] = []
    for horse in sorted(
        horses,
        key=lambda item: (
            item.get("ability_rank") if item.get("ability_rank") is not None else 999,
            item.get("current_evaluation_rank") if item.get("current_evaluation_rank") is not None else 999,
            to_float(item.get("number")) or 999,
        ),
    ):
        number = clean_text(horse.get("number"))
        badges = [label for label, members in category_sets.items() if number in members]
        if not badges:
            continue
        badge_html = "".join(
            f'<span class="ka-comparison-tag plus">{plain_text_to_html(label)}</span>'
            for label in badges
        )
        rows.append(
            '<div class="ka-nar-diagnostic-item">'
            f'<b>{plain_text_to_html(diagnostic_line(horse))}</b><br>{badge_html}'
            "</div>"
        )
    if not rows:
        rows.append('<div class="ka-nar-diagnostic-item ka-muted">該当馬なし</div>')
    return '<div class="ka-nar-diagnostic-card">' + "".join(rows) + "</div>"


def render_nar_position_flow(diagnostics: dict[str, Any], *, layout: str = "mobile") -> None:
    positions = diagnostics.get("positions") if isinstance(diagnostics.get("positions"), dict) else {}
    if not positions:
        return
    st.subheader("展開イメージ")
    st.caption("保存済み位置予測を表示しています。購入条件ではありません。")
    st.markdown(nar_position_stage_html("4コーナー", positions.get("corner4") or {}), unsafe_allow_html=True)
    with st.expander("スタート・3コーナーを見る", expanded=False):
        st.markdown(nar_position_stage_html("スタート", positions.get("start") or {}), unsafe_allow_html=True)
        st.markdown(nar_position_stage_html("3コーナー", positions.get("corner3") or {}), unsafe_allow_html=True)


def nar_position_stage_html(title: str, groups: dict[str, list[dict[str, str]]]) -> str:
    lines = [f'<div class="ka-nar-diagnostic-title">{plain_text_to_html(title)}</div>']
    for group in ("front", "middle", "back", "unknown"):
        horses = groups.get(group) or []
        if not horses and group == "unknown":
            continue
        pills = "".join(
            f'<span class="ka-horse-pill">{plain_text_to_html(clean_text(item.get("number")) or "—")}</span>'
            for item in horses
            if clean_text(item.get("number"))
        ) or '<span class="ka-muted">—</span>'
        lines.append(
            '<div class="ka-position-line">'
            f'<b>{plain_text_to_html(position_group_label(group))}</b><div>{pills}</div>'
            "</div>"
        )
    return '<div class="ka-position-stage">' + "".join(lines) + "</div>"


def render_full_field_comparison(table: pd.DataFrame, race_mode: str) -> None:
    comparison = build_full_field_comparison(table.to_dict("records"), race_mode=race_mode)
    if not comparison.get("show"):
        return
    st.subheader("全頭横比較")
    labels = comparison.get("sort_labels") if isinstance(comparison.get("sort_labels"), dict) else {}
    mode_by_label = {label: mode for mode, label in labels.items()}
    options = list(mode_by_label.keys()) or ["馬番順"]
    if hasattr(st, "selectbox"):
        selected_label = st.selectbox(
            "表示順",
            options,
            index=0,
            key=f"full_field_comparison_sort_{clean_text(race_mode).lower()}_{id(table)}",
        )
    else:
        selected_label = options[0]
    comparison = build_full_field_comparison(
        table.to_dict("records"),
        race_mode=race_mode,
        sort_mode=mode_by_label.get(selected_label, "horse_number"),
    )
    gap = comparison.get("gap_1_2")
    if gap is not None:
        st.caption(f"能力1位と2位の差：{float(gap):.1f}（参考表示。印・研究買いには反映しません）")
    if comparison.get("transfer_watch"):
        st.markdown(
            '<div class="ka-dashboard-card">'
            '<b>🧪 Ver4.1監視</b><br>'
            '能力1位はJRA→NAR初戦。能力2位との入替候補を未見100R検証中。'
            '<div class="ka-note">研究表示のみで、印は変更しません。</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    st.markdown(full_field_comparison_html(comparison), unsafe_allow_html=True)
    st.caption("保存済み予想情報の横比較です。能力値・印・展開位置・研究買いは再計算していません。")


def render_nar_full_field_comparison(table: pd.DataFrame, race_mode: str) -> None:
    render_full_field_comparison(table, race_mode)


def nar_comparison_top_two_html(comparison: dict[str, Any]) -> str:
    top1 = comparison.get("top1")
    top2 = comparison.get("top2")
    if not isinstance(top1, dict) or not isinstance(top2, dict):
        return ""
    gap = comparison.get("gap_1_2")
    gap_text = f"能力差：{float(gap):.1f}" if gap is not None else "能力差：—"
    return (
        '<div class="ka-dashboard-card">'
        '<div class="ka-dashboard-title">能力1位 vs 能力2位</div>'
        '<div class="ka-comparison-vs">'
        f'{nar_comparison_vs_card_html(top1)}'
        f'<div class="ka-comparison-vs-mid">{plain_text_to_html(gap_text)}</div>'
        f'{nar_comparison_vs_card_html(top2)}'
        '</div>'
        '</div>'
    )


def nar_comparison_vs_card_html(horse: dict[str, Any]) -> str:
    lines = [
        f"{clean_text(horse.get('mark'))}{clean_text(horse.get('number'))} {clean_text(horse.get('name'))}",
        f"能力{rank_display(horse.get('ability_rank'))} / {number_display(horse.get('ability_value'))}",
        f"4角：{clean_text(horse.get('corner4_label')) or comparison_position_icon(clean_text(horse.get('corner4_group')))}",
        f"近走3着内：{'あり' if int(horse.get('recent_top3_count') or 0) > 0 else 'なし'}",
        f"今回評価：{rank_display(horse.get('current_evaluation_rank'))}",
    ]
    if clean_text(horse.get("transfer_status")):
        lines.append(f"転入：{clean_text(horse.get('transfer_status'))}")
    if clean_text(horse.get("training")):
        lines.append(f"調教：{clean_text(horse.get('training'))}")
    return (
        '<div class="ka-comparison-vs-card">'
        + "<br>".join(plain_text_to_html(line) for line in lines if clean_text(line))
        + "</div>"
    )


def full_field_comparison_html(comparison: dict[str, Any], *, include_body_weight: bool = True) -> str:
    rows = comparison.get("rows") or []
    if not rows:
        return '<div class="ka-dashboard-card">比較できる出走馬データがありません。</div>'
    race_mode = clean_text(comparison.get("race_mode")).lower()
    metrics: list[tuple[str, str, Any]] = [
        ("印", "", lambda horse: clean_text(horse.get("mark")) or "—"),
        ("能力順位", "", lambda horse: rank_display(horse.get("ability_rank"))),
        ("能力値", "", lambda horse: number_display(horse.get("ability_value"))),
        ("能力1位との差", "", lambda horse: clean_text(horse.get("ability_gap_text")) or "—"),
        ("今回評価順位", "", lambda horse: rank_display(horse.get("current_evaluation_rank"))),
        ("4角位置", "position", lambda horse: clean_text(horse.get("corner4_display")) or clean_text(horse.get("corner4_label")) or comparison_position_icon(clean_text(horse.get("corner4_group")))),
        ("近3走指数", "", lambda horse: clean_text(horse.get("recent3_indices")) or "—"),
        ("近3走条件", "", lambda horse: clean_text(horse.get("recent3_conditions")) or "—"),
        ("距離指数", "", lambda horse: clean_text(horse.get("distance_index")) or "—"),
        ("コース指数", "", lambda horse: clean_text(horse.get("course_index")) or "—"),
        ("同距離", "", lambda horse: clean_text(horse.get("same_distance")) or "—"),
        ("同コース", "", lambda horse: clean_text(horse.get("same_course")) or "—"),
        ("脚質", "", lambda horse: clean_text(horse.get("running_style")) or "—"),
        ("騎手", "", lambda horse: clean_text(horse.get("jockey_display")) or "—"),
        ("斤量", "", lambda horse: clean_text(horse.get("weight")) or "—"),
        ("レース間隔", "", lambda horse: clean_text(horse.get("interval")) or "—"),
        ("クラス実績", "", lambda horse: clean_text(horse.get("class_record")) or "—"),
        ("対戦", "", lambda horse: clean_text(horse.get("matchup")) or "—"),
        ("プラス材料", "plus", lambda horse: horse.get("positive_tags") or []),
        ("不安材料", "minus", lambda horse: horse.get("negative_tags") or []),
    ]
    if include_body_weight or any(clean_text(horse.get("body_weight")) not in {"", "—"} for horse in rows):
        weight_index = next((index for index, item in enumerate(metrics) if item[0] == "斤量"), len(metrics) - 2)
        metrics.insert(weight_index + 1, ("馬体重", "", lambda horse: clean_text(horse.get("body_weight")) or "—"))
    if race_mode == "nar":
        metrics.insert(-2, ("転入状態", "transfer", lambda horse: clean_text(horse.get("transfer_status")) or "判定不明"))
        metrics.insert(-2, ("地方実績", "", lambda horse: clean_text(horse.get("local_experience")) or "判定不明"))
    if race_mode == "jra":
        course_index = next((index for index, item in enumerate(metrics) if item[0] == "同コース"), 13)
        metrics.insert(course_index + 1, ("同回り", "", lambda horse: clean_text(horse.get("same_turn_display")) or clean_text(horse.get("same_turn")) or "×"))
        metrics.insert(-2, ("乗替/継続", "", lambda horse: clean_text(horse.get("jockey_change")) or "—"))
        metrics.insert(-2, ("調教評価", "", lambda horse: clean_text(horse.get("training")) or "—"))
        metrics.insert(-2, ("厩舎コメント", "", lambda horse: clean_text(horse.get("stable_comment")) or "—"))
    header = ['<th class="ka-sticky-metric">比較項目</th>']
    for horse in rows:
        title = f"{clean_text(horse.get('number'))} {clean_text(horse.get('name'))}".strip() or "—"
        mark = clean_text(horse.get("mark"))
        header.append(
            "<th>"
            f"{plain_text_to_html(title)}"
            + (f'<br><span class="ka-muted">{plain_text_to_html(mark)}</span>' if mark else "")
            + "</th>"
        )
    body_rows = []
    for label, kind, getter in metrics:
        cells = [f'<td class="ka-sticky-metric">{plain_text_to_html(label)}</td>']
        for horse in rows:
            value = getter(horse)
            if kind in {"plus", "minus"}:
                cells.append(f"<td>{nar_comparison_tags_html(value, kind)}</td>")
            elif kind == "position":
                group = clean_text(horse.get("corner4_group"))
                css = "ka-comparison-cell-front" if group == "front" else "ka-comparison-cell-back" if group == "back" else ""
                cells.append(f'<td class="{css}">{plain_text_to_html(clean_text(value) or "—")}</td>')
            elif kind == "transfer" and "JRA" in clean_text(value) and "NAR" in clean_text(value):
                cells.append(f'<td>{nar_comparison_tags_html([value], "minus")}</td>')
            else:
                cells.append(f"<td>{plain_text_to_html(clean_text(value) or '—')}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="ka-comparison-scroll"><table class="ka-comparison-table">'
        "<thead><tr>"
        + "".join(header)
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )


def nar_comparison_tags_html(values: Any, kind: str) -> str:
    if not isinstance(values, list):
        values = [values] if clean_text(values) else []
    values = [clean_text(value) for value in values if clean_text(value)]
    if not values:
        return '<span class="ka-muted">—</span>'
    css = "plus" if kind == "plus" else "minus"
    return "".join(
        f'<span class="ka-comparison-tag {css}">{plain_text_to_html(value)}</span>'
        for value in values
    )


def rank_display(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "未成立"
    return f"{int(number)}位"


def number_display(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "—"
    return f"{number:.1f}"


def render_market_research_bet(table: pd.DataFrame, race_mode: str, *, context: str) -> None:
    if table is None or table.empty:
        return
    research = build_research_bet(table.to_dict("records"), race_mode, context=context)
    if not research.get("show"):
        return
    st.subheader(clean_text(research.get("title")) or "研究買い")
    lines = "<br>".join(plain_text_to_html(line) for line in research.get("lines", []) if clean_text(line))
    note_bits = [
        clean_text(research.get("note")),
        clean_text(research.get("trio_condition")),
        clean_text(research.get("reason")),
        f"research_rule_id：{clean_text(research.get('research_rule_id'))}",
    ]
    monitor_lines = [clean_text(line) for line in research.get("monitor_lines", []) if clean_text(line)]
    if monitor_lines:
        note_bits.extend(["🔎 NAR監視情報", *monitor_lines, clean_text(research.get("monitor_note"))])
    notes = "<br>".join(plain_text_to_html(bit) for bit in note_bits if bit)
    total = int(research.get("total") or 0)
    total_html = f"<br><br>合計：{total:,}円" if total > 0 else ""
    st.markdown(
        '<div class="ka-dashboard-card">'
        f'<div class="ka-dashboard-value">{lines}</div>'
        f'<div class="ka-note">{notes}{total_html}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_market_ai_evaluation(table: pd.DataFrame, race_mode: str = "jra") -> None:
    st.subheader("AI今回評価")
    ordered = table.sort_values(["current_evaluation_rank", "market_ability_rank"], ascending=[True, True])
    records = []
    for row in ordered.to_dict("records"):
        horse_label = join_nonempty([horse_no(pick(row, "馬番", "馬")), pick(row, "馬名")], sep=" ")
        age = market_horse_age_text(row)
        if age:
            horse_label = f"{horse_label}（{age}）"
        records.append(
            {
                "今回評価": f"{clean_text(pick(row, 'current_evaluation_rank'))}位",
                "印": clean_text(pick(row, "ai_current_mark")),
                "馬": horse_label,
                "能力": f"{clean_text(pick(row, 'ability_band_v2'))}・{clean_text(pick(row, 'market_ability_rank'))}位",
                "実オッズ": format_odds(pick(row, "actual_odds")) or "—",
                "判断材料": market_ai_material_text(row, race_mode),
            }
        )
    st.dataframe(pd.DataFrame.from_records(records), use_container_width=True, hide_index=True)
    st.caption("今回評価は能力を土台に条件・状態・展開等を横比較した順位です。実オッズと能力順位は別軸のまま保持します。")


def market_horse_age_text(row: dict[str, Any]) -> str:
    """Return only an uploaded/parser-provided sex/age value."""

    value = clean_text(
        pick(
            row,
            "馬年齢",
            "性齢",
            "sex_age",
            "horse_age",
            "馬齢",
            "age",
            "年齢",
        )
    )
    numeric = re.fullmatch(r"(\d{1,2})(?:\.0+)?", value)
    return f"{numeric.group(1)}歳" if numeric else value


def market_ability_value_text(row: dict[str, Any]) -> str:
    """Display the existing Ver3 ability value without changing the stored value."""

    value = pick(row, "market_ability_score", "能力評価値", "ability_score")
    number = to_float(value)
    if number is None:
        return clean_text(value) or "—"
    return f"{number:.1f}"


def market_training_text(row: dict[str, Any], race_mode: str, *, with_prefix: bool = True) -> str:
    """Display-only training summary; raw workout laps stay in audit data."""

    if clean_text(race_mode).lower() != "jra":
        return ""
    existing = clean_text(pick(row, "training_display"))
    if existing:
        display = existing
    else:
        display = training_display(
            {
                "調教評価": pick(row, "training_market", "調教評価", "追切評価", "training_grade"),
                "調教コメント": pick(row, "training_comment", "調教短評", "追切短評", "調教コメント"),
            },
            race_mode,
        ).get("display", "")
    if not display:
        return ""
    return display if with_prefix else re.sub(r"^調教", "", display)


def market_stable_comment_text(row: dict[str, Any], race_mode: str) -> str:
    if clean_text(race_mode).lower() != "jra":
        return ""
    existing = clean_text(pick(row, "stable_comment_display"))
    if existing:
        return existing
    return stable_comment_display({"厩舎コメント": pick(row, "stable_comment_market", "厩舎コメント", "新聞コメント")}, race_mode)


def market_jockey_display_text(row: dict[str, Any]) -> str:
    display = clean_text(pick(row, "jockey_display_market"))
    detail = clean_text(pick(row, "騎手詳細", "jockey_detail", "騎手継続/乗替", "jockey_change"))
    current = clean_text(pick(row, "jockey_market", "騎手", "jockey"))
    text = display
    if not text or (current and text == current and has_jockey_change_context(detail)):
        text = detail or current
    text = normalize_jockey_display_text(text or current)
    return append_jockey_place_rate(text, jockey_place_rate_text(row))


def market_weight_display_text(row: dict[str, Any]) -> str:
    """Show carried weight and its recorded change without affecting evaluation."""

    weight = clean_text(pick(row, "weight_market"))
    if weight in {"", "未取得"}:
        current = to_float(pick(row, "_display_current_load_weight", "_current_load_weight", "斤量", "weight"))
        weight = f"{current:.1f}kg" if current is not None else ""
    if not weight or "前走比" in weight:
        return weight

    change = to_float(
        pick(
            row,
            "weight_change_market",
            "_display_load_weight_change",
            "_load_weight_change",
            "斤量増減",
            "weight_change",
        )
    )
    if change is None:
        detail = clean_text(pick(row, "斤量詳細", "weight_detail"))
        match = re.search(r"(?:前走比\s*)?([+-−]\d+(?:\.\d+)?|±\s*0)\s*(?:kg)?", detail)
        if match:
            change = to_float(match.group(1).replace("−", "-").replace("±", "").replace(" ", ""))
    if change is None:
        current = to_float(pick(row, "_display_current_load_weight", "_current_load_weight", "斤量", "weight"))
        previous = to_float(pick(row, "_display_previous_load_weight", "_previous_load_weight"))
        if current is not None and previous is not None:
            change = current - previous
    if change is None:
        return weight

    change_text = "±0" if abs(change) < 0.0001 else f"{change:+.1f}"
    return f"{weight}（前走比{change_text}kg）"


def has_jockey_change_context(text: str) -> bool:
    value = clean_text(text)
    return any(token in value for token in ("継続", "乗替", "乗り替", "替", "→"))


def normalize_jockey_display_text(text: str) -> str:
    value = clean_text(text)
    if not value:
        return ""
    value = value.replace("【継続】", "（継続）")
    value = value.replace("（継）", "（継続）")
    value = value.replace("（継・", "（継続・")
    value = value.replace("【乗り替わり】", "（乗替）")
    value = value.replace("【乗替】", "（乗替）")
    value = value.replace("【替】", "（乗替）")
    if "→" in value:
        value = value.replace("（乗替）", "")
    return value


def jockey_place_rate_text(row: dict[str, Any]) -> str:
    rate = to_float(pick(row, "_jockey_course_place_rate", "jockey_course_place_rate", "騎手コース複勝率"))
    if rate is None:
        stats = clean_text(pick(row, "jockey_course_stats_market", "騎手コース成績"))
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", stats)
        if len(matches) >= 3:
            rate = to_float(matches[2])
        elif len(matches) == 1 and "複" in stats:
            rate = to_float(matches[0])
    if rate is None:
        return ""
    label = f"{rate:.0f}" if float(rate).is_integer() else f"{rate:.1f}"
    return f"複{label}%"


def append_jockey_place_rate(text: str, rate: str) -> str:
    if not text or not rate or "複" in text:
        return text
    if text.endswith("）") and "（" in text:
        return f"{text[:-1]}・{rate}）"
    return f"{text}（{rate}）"


def market_position_path_text(row: dict[str, Any]) -> str:
    path = clean_text(pick(row, "position_path_market", "想定位置", "推定位置"))
    if not path:
        return "位置不明"
    if "top=" in path or "left=" in path:
        return "位置不明"
    return path


def market_corner4_label_text(row: dict[str, Any]) -> str:
    label = clean_text(pick(row, "position_corner4_label_market", "_estimated_position_corner4_label", "corner4_evaluation", "4角評価"))
    if label and label not in {"位置不明", "未取得"} and "top=" not in label and "left=" not in label:
        return label
    path = market_position_path_text(row)
    if not path or path == "位置不明":
        return ""
    parts = [part.strip() for part in re.split(r"→|>|/|／", path) if part.strip()]
    return parts[-1] if parts else ""


def market_course_material_text(row: dict[str, Any]) -> str:
    mark = clean_text(pick(row, "course_development_mark"))
    reason = clean_text(pick(row, "course_development_reason"))
    if "推定有利馬" in reason:
        return ""
    if reason == "4角傾向フラット":
        return ""
    if mark in {"◎", "○"} and reason:
        return f"＋ {reason}"
    if mark in {"△", "×"} and reason:
        return f"－ {reason}"
    support = course_material_display(row)
    label = clean_text(support.get("label"))
    if label and "フラット" not in label and "推定有利馬" not in label:
        return label
    return ""


def market_netkeiba_favorable_text(row: dict[str, Any]) -> str:
    reason = clean_text(pick(row, "course_development_reason"))
    if "推定有利馬" in reason:
        return "○ 推定有利馬"
    label = clean_text(course_material_display(row).get("netkeiba_label"))
    return label


def market_pace_material_text(row: dict[str, Any]) -> str:
    text = join_nonempty([pick(row, "pace_mark_market"), pick(row, "pace_reason_market")], sep=" ")
    if not text:
        return ""
    return text.replace("○ ", "＋ ", 1).replace("△ ", "－ ", 1)


def market_ai_material_text(row: dict[str, Any], race_mode: str) -> str:
    parts = [
        clean_text(pick(row, "ai_current_reason")),
        market_pace_material_text(row),
        market_course_material_text(row),
        market_netkeiba_favorable_text(row),
        market_training_text(row, race_mode, with_prefix=False),
        market_stable_comment_text(row, race_mode),
    ]
    return " / ".join(unique_nonempty(parts)) or "—"


def unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def render_market_full_table(table: pd.DataFrame, race_mode: str) -> None:
    st.subheader("全頭横比較表")
    records = []
    for row in table.to_dict("records"):
        no = horse_no(pick(row, "馬番", "馬"))
        state = join_nonempty(
            [clean_text(pick(row, "state_arrow")), clean_text(pick(row, "state_label_market"))],
            sep=" ",
        )
        weight = market_weight_display_text(row)
        record = {
            "馬番": no,
            "馬名": clean_text(pick(row, "馬名")),
            "馬齢": market_horse_age_text(row) or "—",
            "印": clean_text(pick(row, "ai_current_mark")),
            "今回評価順位": clean_text(pick(row, "current_evaluation_rank")) or "—",
            "能力帯": clean_text(pick(row, "ability_band_v2")) or "Z",
            "能力順位": clean_text(pick(row, "market_ability_rank")) or "—",
            "能力値": format_index_value(pick(row, "market_ability_score")),
            "実オッズ": format_odds(pick(row, "actual_odds")) or "—",
            "騎手": market_jockey_display_text(row),
            "斤量": weight,
            "能力注記": clean_text(pick(row, "ability_watch_label")) or "—",
            "クラス": clean_text(pick(row, "current_class_market")),
            "クラス変動": clean_text(pick(row, "class_shift_market")),
            "クラス実績": clean_text(pick(row, "class_basis_market")),
            "間隔": clean_text(pick(row, "race_interval_market")),
            "状態": state,
            "脚質": clean_text(pick(row, "running_style_market")),
            "今回の展開": market_pace_material_text(row) or "—",
            "今回のコース材料": market_course_material_text(row) or "—",
            "netkeiba推定": market_netkeiba_favorable_text(row) or "—",
            "想定位置": market_position_path_text(row),
            "距離": format_index_value(pick(row, "距離指数")),
            "コース": format_index_value(pick(row, "コース指数")),
            "3走前": format_index_value(pick(row, "3走前")),
            "2走前": format_index_value(pick(row, "2走前")),
            "前走": format_index_value(pick(row, "前走")),
            "平均": format_index_value(pick(row, "平均指数", "3走平均")),
            "★": format_star_value(pick(row, "★最高指数", "star_max_index", "★最高")),
            "＋材料": clean_text(pick(row, "plus_materials_display")),
            "－材料": clean_text(pick(row, "minus_materials_display")),
        }
        if race_mode == "jra":
            record["調教"] = market_training_text(row, race_mode, with_prefix=False) or "—"
        records.append(record)
    comparison = pd.DataFrame.from_records(records)
    st.dataframe(comparison, use_container_width=True, hide_index=True)


def render_market_horse_cards(table: pd.DataFrame, race_mode: str) -> None:
    st.subheader("馬別コンパクトカード")
    ordered = market_horse_cards_ordered(table)
    for row in ordered.to_dict("records"):
        st.markdown(market_horse_card_html(row, race_mode), unsafe_allow_html=True)


def market_horse_cards_ordered(table: pd.DataFrame) -> pd.DataFrame:
    """Display cards by existing ability value; do not change prediction ranks."""

    ordered = table.copy()
    ordered["_card_ability_value_sort"] = pd.to_numeric(
        ordered["market_ability_score"] if "market_ability_score" in ordered.columns else pd.Series(pd.NA, index=ordered.index),
        errors="coerce",
    )
    ordered["_card_ability_rank_sort"] = pd.to_numeric(
        ordered["market_ability_rank"] if "market_ability_rank" in ordered.columns else pd.Series(pd.NA, index=ordered.index),
        errors="coerce",
    )
    ordered["_card_current_rank_sort"] = pd.to_numeric(
        ordered["current_evaluation_rank"] if "current_evaluation_rank" in ordered.columns else pd.Series(pd.NA, index=ordered.index),
        errors="coerce",
    )
    ordered = ordered.sort_values(
        ["_card_ability_value_sort", "_card_ability_rank_sort", "_card_current_rank_sort"],
        ascending=[False, True, True],
        na_position="last",
        kind="mergesort",
    )
    return ordered.drop(columns=["_card_ability_value_sort", "_card_ability_rank_sort", "_card_current_rank_sort"])


def market_horse_card_html(row: dict[str, Any], race_mode: str) -> str:
    number = horse_no(pick(row, "馬番", "馬")) or "—"
    name = clean_text(pick(row, "馬名")) or "名称未取得"
    band = clean_text(pick(row, "ability_band_v2")) or "Z"
    odds = format_odds(pick(row, "actual_odds")) or "—"
    mark = clean_text(pick(row, "ai_current_mark"))
    age = market_horse_age_text(row)
    ability_value = market_ability_value_text(row)
    ability_rank = clean_text(pick(row, "market_ability_rank")) or "—"
    current_rank = clean_text(pick(row, "current_evaluation_rank")) or "—"
    state = join_nonempty([pick(row, "state_arrow"), pick(row, "state_label_market")], sep=" ")
    jockey = market_jockey_display_text(row)
    weight = market_weight_display_text(row)
    body_weight = clean_text(pick(row, "body_weight_market"))
    if body_weight == "未取得":
        body_weight = ""
    interval = clean_text(pick(row, "race_interval_market"))
    current_class = clean_text(pick(row, "current_class_market"))
    class_shift = clean_text(pick(row, "class_shift_market"))
    class_basis = clean_text(pick(row, "class_basis_market"))
    corner4_label = market_corner4_label_text(row)
    quick = join_nonempty(
        [
            clean_text(pick(row, "running_style_market")),
            f"4角：{corner4_label}" if corner4_label else "",
            jockey,
            weight,
            body_weight,
            interval,
            f"今回{current_class}" if current_class and current_class != "未取得" else "",
        ],
        sep="｜",
    )
    plus = clean_text(pick(row, "plus_materials_display"))
    minus = clean_text(pick(row, "minus_materials_display"))
    position_path = market_position_path_text(row)
    pace = market_pace_material_text(row)
    course = market_course_material_text(row)
    netkeiba = market_netkeiba_favorable_text(row)
    training_display_text = market_training_text(row, race_mode)
    stable_summary = market_stable_comment_text(row, race_mode)
    ability_watch_label = clean_text(pick(row, "ability_watch_label"))
    ability_watch_warning = clean_text(pick(row, "ability_unmarked_warning"))
    detail_lines = [
        f"能力値：{format_index_value(pick(row, 'market_ability_score'))}（能力順位 {ability_rank}位）",
        f"実オッズ：{odds}",
        f"今回評価：{current_rank}位 {mark}｜{clean_text(pick(row, 'ai_current_reason'))}",
    ]
    if ability_watch_label:
        detail_lines.append(f"能力注記：{ability_watch_label}")
    if state:
        detail_lines.append(f"状態：{state}（{clean_text(pick(row, 'state_transition'))}）")
    if weight:
        detail_lines.append(f"斤量：{weight}")
    if interval and interval not in {"未取得", "未確認"}:
        detail_lines.append(f"レース間隔：{interval}")
    class_parts = [
        current_class if current_class not in {"", "未取得"} else "",
        class_shift if class_shift not in {"", "判定保留"} else "",
    ]
    if any(class_parts):
        detail_lines.append(f"クラス：{'｜'.join(part for part in class_parts if part)}")
    if class_basis and class_basis not in {"取得不能", "未取得"}:
        detail_lines.append(f"クラス実績：{class_basis}")
    if body_weight:
        detail_lines.append(f"馬体重：{body_weight}")
    if position_path:
        detail_lines.append(f"想定位置：{position_path}")
    if corner4_label:
        detail_lines.append(f"4角位置：{corner4_label}")
    if pace:
        detail_lines.append(f"展開：{pace}")
    if course:
        detail_lines.append(f"コース：{course}")
    if netkeiba:
        detail_lines.append(f"netkeiba推定：{netkeiba}")
    detail_lines.append(
        f"距離：{format_index_value(pick(row, '距離指数'))}｜コース：{format_index_value(pick(row, 'コース指数'))}"
    )
    if race_mode == "jra":
        if training_display_text:
            detail_lines.append(f"調教：{training_display_text}")
        stable = clean_text(pick(row, "stable_comment_market"))
        if stable_summary:
            detail_lines.append(stable_summary)
        if stable:
            detail_lines.append(f"厩舎コメント全文：{shorten_text(stable, 120)}")
    detail = "<br>".join(plain_text_to_html(line) for line in detail_lines)
    material_lines = ""
    if plus:
        material_lines += f'<div class="ka-market-card-line ka-market-plus">＋ {plain_text_to_html(plus)}</div>'
    if minus:
        material_lines += f'<div class="ka-market-card-line ka-market-minus">－ {plain_text_to_html(minus)}</div>'
    if course:
        material_lines += f'<div class="ka-market-card-line ka-market-plus">{plain_text_to_html(course)}</div>'
    if netkeiba:
        material_lines += f'<div class="ka-market-card-line ka-market-plus">{plain_text_to_html(netkeiba)}</div>'
    if training_display_text:
        css = "ka-market-minus" if "D↓" in training_display_text else "ka-market-plus"
        sign = "－ " if "D↓" in training_display_text else "＋ "
        material_lines += f'<div class="ka-market-card-line {css}">{plain_text_to_html(sign + training_display_text)}</div>'
    if stable_summary:
        material_lines += f'<div class="ka-market-card-line">{plain_text_to_html(stable_summary)}</div>'
    if ability_watch_label:
        css = "ka-market-minus" if ability_watch_warning else "ka-market-plus"
        material_lines += f'<div class="ka-market-card-line {css}">{plain_text_to_html(ability_watch_label)}</div>'
    main_parts = [
        mark,
        odds,
        age,
        f"能力値{ability_value}",
        f"能力{ability_rank}位・今回{current_rank}位",
    ]
    return (
        '<div class="ka-horse-card"><details>'
        '<summary>'
        f'<div class="ka-market-card-title">{plain_text_to_html(band)} {plain_text_to_html(number)} {plain_text_to_html(name)}</div>'
        f'<div class="ka-market-card-line"><b>{plain_text_to_html("｜".join(part for part in main_parts if clean_text(part)))}</b></div>'
        f'<div class="ka-market-card-line">{plain_text_to_html(quick)}</div>'
        f'{material_lines}'
        '</summary>'
        f'<div class="ka-horse-detail">{detail}<br><b>能力値・能力帯への条件補正：なし</b></div>'
        '</details></div>'
    )


def render_market_audit_details(result: PredictionResult, table: pd.DataFrame) -> None:
    with st.expander("詳細/監査情報", expanded=False):
        all_debug = getattr(result, "debug_info", {}) or {}
        market = all_debug.get("market_compare") if isinstance(all_debug.get("market_compare"), dict) else {}
        course = all_debug.get("course_materials") if isinstance(all_debug.get("course_materials"), dict) else {}
        jockey = all_debug.get("jockey_course_materials") if isinstance(all_debug.get("jockey_course_materials"), dict) else {}
        calibration = market.get("calibration") if isinstance(market.get("calibration"), dict) else {}
        st.caption("ここは取得状況と互換情報の確認用です。能力値・能力順位・能力帯へは加算していません。")
        if calibration:
            st.write(calibration.get("display") or "AI適正オッズは通常表示対象外")
            if calibration.get("reason"):
                st.caption(calibration.get("reason"))
        if course:
            coverage = course.get("position_coverage") or {}
            horse_count = course.get("horse_count") or "?"
            lines = [
                f"コース情報取得状態：{clean_text(course.get('source_status')) or 'html内に存在しない'}",
                f"推定位置カバー：始 {coverage.get('start', 0)}/{horse_count}・3角 {coverage.get('corner3', 0)}/{horse_count}・4角 {coverage.get('corner4', 0)}/{horse_count}",
                f"トラックバイアス：{clean_text(course.get('track_bias_status')) or 'html内に存在しない'}",
                f"ラップ予測：{clean_text(course.get('lap_prediction_status')) or 'html内に存在しない'}",
                f"前半/後半3F：{course.get('predicted_3f_coverage', 0)}/{horse_count}",
            ]
            matrix = four_corner_rates_display(course.get("four_corner_place_rates"))
            if matrix:
                lines.append(f"4角位置別複勝率：{matrix}")
            st.markdown("<br>".join(plain_text_to_html(line) for line in lines), unsafe_allow_html=True)
        if jockey:
            st.write(
                f"騎手コースHTML：{clean_text(jockey.get('source_status')) or '未アップロード'}"
                + (f" / {len(jockey.get('horses') or {})}頭" if jockey.get("horses") else "")
            )
        raw_records = []
        for row in table.to_dict("records"):
            raw = join_nonempty(
                [pick(row, "position_start_market"), pick(row, "position_corner3_market"), pick(row, "position_corner4_market")],
                sep=" / ",
            )
            if raw and raw != "未取得 / 未取得 / 未取得":
                raw_records.append(
                    {
                        "馬": join_nonempty([horse_no(pick(row, "馬番", "馬")), pick(row, "馬名")], sep=" "),
                        "生座標（始/3/4角）": raw,
                        "人間向け位置": clean_text(pick(row, "position_path_market")) or "位置不明",
                    }
                )
        if raw_records:
            st.dataframe(pd.DataFrame.from_records(raw_records), use_container_width=True, hide_index=True)
        watch_records = []
        for row in table.to_dict("records"):
            label = clean_text(pick(row, "ability_watch_label"))
            if not label:
                continue
            watch_records.append(
                {
                    "馬": join_nonempty([horse_no(pick(row, "馬番", "馬")), pick(row, "馬名")], sep=" "),
                    "能力注記": label,
                    "ability_top_match": bool(pick(row, "ability_top_match")),
                    "ability_top3_unmarked": bool(pick(row, "ability_top3_unmarked")),
                    "market_supported_unmarked": bool(pick(row, "market_supported_unmarked")),
                    "high_risk_unmarked": bool(pick(row, "high_risk_unmarked")),
                    "ability_gap_1_2": pick(row, "ability_gap_1_2"),
                }
            )
        if watch_records:
            st.write("能力順位×印×保存オッズ 監査")
            st.dataframe(pd.DataFrame.from_records(watch_records), use_container_width=True, hide_index=True)
        legacy_columns = existing_columns(
            table,
            ["表示印", "最終印", "グループ", "AI点", "総合評価", "SS指数", "SS", "BUY", "単勝期待値", "軸信頼度"],
        )
        if legacy_columns:
            st.write("旧評価・印（互換表示）")
            st.dataframe(table.loc[:, legacy_columns], use_container_width=True, hide_index=True)
        render_raw_text_section("旧AIレース考察", result.ai_race_review)
        render_raw_text_section("旧馬券構成", result.betting_structure)


def render_market_user_selection(result: PredictionResult, table: pd.DataFrame) -> None:
    st.subheader("自分の選択を保存")
    debug = ((getattr(result, "debug_info", {}) or {}).get("market_compare") or {})
    saved = debug.get("user_selection") if isinstance(debug.get("user_selection"), dict) else {}
    options = [
        join_nonempty([horse_no(pick(row, "馬番", "馬")), pick(row, "馬名")], sep=" ")
        for row in table.to_dict("records")
    ]
    default_horses = [value for value in saved.get("horses", []) if value in options]
    selected = st.multiselect("気になる馬・本命候補・相手候補", options, default=default_horses, key="market_user_horses")
    reason = st.text_area("理由", value=clean_text(saved.get("reason")), placeholder="例：A帯7倍 / 同距離 / 状態↑", key="market_user_reason")
    ticket = st.text_input("券種・買い方（自由入力）", value=clean_text(saved.get("ticket")), key="market_user_ticket")
    if st.button("今回の選択を保存", use_container_width=True, key="save_market_user_selection"):
        market = dict(debug)
        market["user_selection"] = {"horses": list(selected), "reason": reason.strip(), "ticket": ticket.strip()}
        all_debug = dict(getattr(result, "debug_info", {}) or {})
        all_debug["market_compare"] = market
        result.debug_info = all_debug
        st.session_state.prediction_result = result
        st.success("今回の選択を予測データへ保存しました。固定保存すると一緒に記録されます。")


def format_signed_number(value: Any) -> str:
    number = to_float(value)
    return "未取得" if number is None else f"{number:+.1f}kg"


def append_nar_star_display_trace(
    result: PredictionResult,
    stage: str,
    table: pd.DataFrame,
    *,
    horse_no_pos: int = 2,
    horse_name_pos: int = 3,
) -> None:
    if result.race_mode != "nar" or table is None or getattr(table, "empty", False):
        return
    debug_info = getattr(result, "debug_info", None)
    if debug_info is None:
        result.debug_info = {}
        debug_info = result.debug_info
    flag = f"_logged_{stage}"
    if debug_info.get(flag):
        return
    rows = []
    for _, row in table.iterrows():
        rows.append(
            star_trace_row(
                horse_no=row.iloc[horse_no_pos] if len(row) > horse_no_pos else "",
                horse_name=row.iloc[horse_name_pos] if len(row) > horse_name_pos else "",
                year_max_index=_star_trace_value(row, "year_max_index", 23),
                star_max_index=_star_trace_value(row, "star_max_index", 24),
                star_source=row.get("star_max_source"),
            )
        )
    debug_info.setdefault("nar_star_trace", []).extend(log_star_trace(stage, rows))
    debug_info[flag] = True


def _star_trace_value(row: pd.Series, key: str, fallback_pos: int):
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


def render_raw_text_section(title: str, text: str) -> None:
    st.subheader(title)
    body = clean_multiline(text)
    if not body:
        st.markdown('<div class="ka-section ka-muted">未取得です。</div>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="ka-section">{plain_text_to_html(body)}</div>', unsafe_allow_html=True)


POWER_GROUPS = [
    ("SS", ""),
    ("A", ""),
    ("B", ""),
    ("C", ""),
    ("Z", ""),
]


def render_race_header(result: PredictionResult) -> None:
    info = result.race_info or {}
    mode = "地方" if result.race_mode == "nar" else "中央"
    title = clean_text(result.race_name) or clean_text(pick(info, "race_name", "レース名")) or "レース"
    items = [
        mode,
        pick(info, "venue", "競馬場", "place"),
        pick(info, "race_number", "R", "レース番号"),
        pick(info, "class", "クラス"),
        pick(info, "post_time", "発走時刻", "発走"),
        pick(info, "distance", "距離"),
        pick(info, "surface", "芝ダート", "馬場種別"),
        pick(info, "turn", "回り"),
        _horse_count_text(result),
    ]
    chips = "".join(f'<span class="ka-chip">{plain_text_to_html(item)}</span>' for item in items if clean_text(item))
    st.markdown(
        f'<div class="ka-dashboard-card"><div class="ka-dashboard-title">レース基本情報</div>'
        f'<div class="ka-dashboard-value">{plain_text_to_html(title)}</div>{chips}</div>',
        unsafe_allow_html=True,
    )


def render_race_summary(result: PredictionResult) -> None:
    rows = result_rows(result)
    if not rows:
        return
    first = rows[0]
    if getattr(result, "logic_version", "v3") == "practical":
        practical = ((getattr(result, "debug_info", {}) or {}).get("practical") or {}).get("summary", {})
        st.markdown(
            '<div class="ka-dashboard-card">'
            '<div class="ka-dashboard-title">実戦モード</div>'
            '<div><span class="ka-chip ss">Ver3印を固定</span>'
            '<span class="ka-chip">★/☆/※は補助情報</span>'
            '<span class="ka-chip">◎単勝100円固定</span></div>'
            f'<div class="ka-note">購入判断：{plain_text_to_html(clean_text(practical.get("decision")) or "WATCH")} / '
            '条件適性による順位の強制変更は行いません。</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return
    if getattr(result, "logic_version", "v3") in {"v4", "v4.1"}:
        summary = dict(getattr(result, "ver4_summary", {}) or {})
        st.markdown(
            '<div class="ka-dashboard-card">'
            '<div class="ka-dashboard-title">レースサマリー Ver4</div>'
            f'<div><span class="ka-chip">{plain_text_to_html("軸信頼度：" + clean_text(summary.get("axis_confidence") or "なし"))}</span>'
            f'<span class="ka-chip">{plain_text_to_html("上位差：" + format_number(summary.get("top_score_gap")))}</span>'
            f'<span class="ka-chip">{plain_text_to_html(clean_text(summary.get("race_competitiveness")) or "未判定")}</span></div>'
            f'<div class="ka-note">判断：{plain_text_to_html(clean_text(summary.get("decision_v4")) or "SKIP")} / '
            f'軸馬：{plain_text_to_html(clean_text(summary.get("axis_horse_no")) or "—")} / '
            f'軸Score：{plain_text_to_html(format_number(summary.get("axis_score")) or "—")}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return
    difficulty = clean_text(pick(first, "レース難易度", "race_difficulty")) or "-"
    difficulty_reason = clean_text(pick(first, "レース難易度理由", "race_difficulty_reason")) or "-"
    gap = clean_text(pick(first, "能力差", "ability_gap_level")) or "-"
    axis = clean_text(pick(first, "軸信頼度", "axis_confidence")) or "-"
    axis_reason = clean_text(pick(first, "軸信頼度理由", "axis_confidence_reason")) or "-"
    body = (
        '<div class="ka-dashboard-card">'
        '<div class="ka-dashboard-title">レースサマリー</div>'
        f'<div><span class="ka-chip">{plain_text_to_html("能力差：" + gap)}</span>'
        f'<span class="ka-chip">{plain_text_to_html("難易度：" + difficulty)}</span>'
        f'<span class="ka-chip">{plain_text_to_html("軸信頼度：" + axis)}</span></div>'
        f'<div class="ka-note">{plain_text_to_html(difficulty_reason)}<br>{plain_text_to_html(axis_reason)}</div>'
        '</div>'
    )
    st.markdown(body, unsafe_allow_html=True)


def result_prediction_table(result: PredictionResult) -> pd.DataFrame | None:
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        table = result.horse_evaluation
    return table


def render_investment_decision(result: PredictionResult) -> InvestmentDecision:
    table = result_prediction_table(result)
    decision = build_investment_decision(
        table,
        result.race_mode,
        race_info=result.race_info,
        prediction_logic_version=getattr(result, "logic_version", "v3"),
    )
    st.subheader("今回買うべき馬券")

    if getattr(result, "logic_version", "v3") == "practical":
        render_practical_investment_decision(decision)
        return decision
    if getattr(result, "logic_version", "v3") in {"v4", "v4.1"}:
        render_ver4_investment_decision(decision)
        return decision

    source_race_count = decision.source_race_count
    race_label = "地方" if decision.race_type == "nar" else "中央"
    source_line = (
        f"{race_label}{source_race_count}R時点の暫定検証"
        if source_race_count
        else f"{race_label}の暫定検証"
    )
    if decision.updated_at:
        source_line += f" / 更新: {decision.updated_at}"

    judgement_class = {
        "買い": "ss",
        "保留": "a",
        "見送り": "z",
    }.get(decision.judgement, "z")

    if decision.selected is None:
        reasons = "<br>".join(plain_text_to_html("・" + line) for line in decision.reason_lines) or "・正式購入条件の一致なし"
        st.markdown(
            '<div class="ka-dashboard-card">'
            f'<div><span class="ka-chip {judgement_class}">総合判定：{plain_text_to_html(decision.judgement)}</span></div>'
            '<div class="ka-dashboard-value">今回は見送り推奨</div>'
            f'<div class="ka-note">今回は正式購入条件に一致する馬券がありません。<br><br>'
            f'見送り理由<br>{reasons}<br><br>{plain_text_to_html(source_line)}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        render_investment_audit(decision)
        return decision

    selected = decision.selected
    score = selected.audit.get("strategy_score")
    confidence = confidence_label(score if isinstance(score, (int, float)) else None)
    tickets = "<br>".join(plain_text_to_html(line) for line in selected.tickets) or "買い目なし"
    matched = "<br>".join(plain_text_to_html("✓ " + line) for line in selected.matched_conditions) or "✓ 条件成立"
    context_lines = decision.final_context_summary or decision.horse_trust_summary
    horse_basis = "<br>".join(
        plain_text_to_html("・" + line) for line in context_lines
    ) or "・対象馬の根拠は未取得"
    ticket_basis = investment_ticket_basis_html(decision)
    alignment_basis = investment_alignment_html(decision)
    caution = ""
    if decision.source_note:
        caution = f"<br>{plain_text_to_html(decision.source_note)}"
    st.markdown(
        '<div class="ka-dashboard-card">'
        f'<div><span class="ka-chip {judgement_class}">総合判定：{plain_text_to_html(decision.judgement)}</span></div>'
        f'<div class="ka-dashboard-value">{plain_text_to_html(selected.ticket_type)} {plain_text_to_html(selected.label)}</div>'
        f'<div class="ka-note">実際の買い目<br>{tickets}<br><br>'
        f'{selected.ticket_count}点 / 合計{decision.total_stake}円（1点100円）<br><br>'
        f'【今回の中心馬・相手馬】<br>{horse_basis}<br><br>'
        f'【馬券側の根拠】<br>{ticket_basis}<br><br>'
        f'【今回評価との一致】<br>{alignment_basis}<br><br>'
        f'過去実績<br>対象{selected.sample_races}R / 的中率{(selected.hit_rate or 0):.1f}% / '
        f'回収率{(selected.expected_roi or 0):.1f}%<br>'
        f'信頼度：{plain_text_to_html(confidence)}<br><br>'
        f'買い条件<br>{matched}<br><br>'
        f'注意<br>{plain_text_to_html(source_line)}{caution}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    render_investment_audit(decision)
    return decision


def render_practical_investment_decision(decision: InvestmentDecision) -> None:
    is_buy = clean_text(decision.practical_decision) == "BUY"
    label = "BUY" if is_buy else "WATCH"
    chip_class = "ss" if is_buy else "z"
    reason_lines = decision.practical_reason_lines or decision.reason_lines
    reasons = "<br>".join(plain_text_to_html("✓ " + line) for line in reason_lines[:4]) or "判定理由なし"
    honmei = join_nonempty([decision.honmei_horse_no, decision.honmei_horse_name], sep=" ") or "—"
    ticket = "◎単勝 1点100円" if is_buy else "購入なし"
    st.markdown(
        '<div class="ka-dashboard-card">'
        f'<div><span class="ka-chip {chip_class}">{label}</span></div>'
        f'<div class="ka-dashboard-value">{plain_text_to_html(ticket)}</div>'
        f'<div class="ka-note">◎ {plain_text_to_html(honmei)}<br><br>'
        f'判定理由<br>{reasons}<br><br>'
        '予想順位・◎○▲△✓はVer3のままです。★/☆/※は購入判断の補助情報で、必須条件ではありません。'
        '</div></div>',
        unsafe_allow_html=True,
    )


def render_ver4_investment_decision(decision: InvestmentDecision) -> None:
    decision_v4 = clean_text(getattr(decision, "decision_v4", "")) or "SKIP"
    label = {"BUY": "買い", "LIGHT": "軽め", "WATCH": "様子見", "SKIP": "見送り"}.get(decision_v4, decision_v4)
    chip_class = {"BUY": "ss", "LIGHT": "a", "WATCH": "b", "SKIP": "z"}.get(decision_v4, "z")
    selected = decision.selected
    if selected is None:
        reasons = "<br>".join(plain_text_to_html("・" + line) for line in decision.reason_lines) or "・買い条件不成立"
        st.markdown(
            '<div class="ka-dashboard-card">'
            f'<div><span class="ka-chip {chip_class}">Ver4判断：{plain_text_to_html(label)}</span></div>'
            f'<div class="ka-dashboard-value">軸信頼度：{plain_text_to_html(clean_text(decision.axis_confidence_v4) or "なし")}</div>'
            f'<div class="ka-note">軸Score：{plain_text_to_html(format_number(decision.axis_score) or "—")}<br>'
            f'買い候補Score：{plain_text_to_html(format_number(decision.ticket_candidate_score) or "—")}<br><br>'
            f'{reasons}</div></div>',
            unsafe_allow_html=True,
        )
        return

    tickets = "<br>".join(plain_text_to_html(ticket) for ticket in selected.tickets)
    st.markdown(
        '<div class="ka-dashboard-card">'
        f'<div><span class="ka-chip {chip_class}">Ver4判断：{plain_text_to_html(label)}</span></div>'
        f'<div class="ka-dashboard-value">{plain_text_to_html(selected.ticket_type)}　{plain_text_to_html(selected.label)}</div>'
        f'<div class="ka-note">実際の買い目<br>{tickets}<br><br>'
        f'{selected.ticket_count}点 / 合計{decision.total_stake}円（1点100円）<br><br>'
        f'軸Score：{plain_text_to_html(format_number(decision.axis_score) or "—")}<br>'
        f'軸信頼度：{plain_text_to_html(clean_text(decision.axis_confidence_v4) or "—")}<br>'
        f'買い候補Score：{plain_text_to_html(format_number(decision.ticket_candidate_score) or "—")}<br><br>'
        'Horse Scoreと適性で軸・相手を決め、相手VETO通過後に低点数で構成しています。'
        '</div></div>',
        unsafe_allow_html=True,
    )


def investment_alignment_html(decision: InvestmentDecision) -> str:
    lines = decision.ticket_alignment_summary
    if not lines and decision.selected is not None:
        lines = tuple(decision.selected.audit.get("ticket_alignment_summary", ()) or ())
    if not lines:
        return "今回評価との照合データは未取得"
    return "<br>".join(plain_text_to_html(line) for line in lines)


def investment_ticket_basis_html(decision: InvestmentDecision) -> str:
    selected = decision.selected
    if selected is None:
        return "記録なし"
    rationale = decision.ticket_rationale or selected.audit.get("ticket_rationale", {})
    lines = [
        f"{selected.ticket_type} {selected.label}",
        f"過去{selected.sample_races}件",
        f"{int(to_float(rationale.get('hits')) or 0)}的中" if rationale.get("hits") not in (None, "") else "",
        f"回収率 {(selected.expected_roi or 0):.1f}%",
    ]
    max_dependency = rationale.get("max_payout_contribution")
    max_losing = rationale.get("max_losing_streak")
    if max_dependency not in (None, ""):
        lines.append(f"高配当依存 {format_number(max_dependency)}%")
    if max_losing not in (None, ""):
        lines.append(f"最大連敗 {format_number(max_losing)}")
    return "<br>".join(plain_text_to_html(line) for line in lines if clean_text(line)) or "記録なし"


def render_investment_target_horses(result: PredictionResult, decision: InvestmentDecision) -> None:
    selected = decision.selected
    if selected is None or not selected.ticket_horses:
        return
    st.subheader("今回の対象馬")
    context_by_no = {
        clean_text(item.get("horse_number")): clean_text(item.get("display_summary"))
        for item in decision.final_betting_context
    }
    trust_by_no = {clean_text(item.get("horse_no")): clean_text(item.get("summary")) for item in decision.horse_trust}
    horse_lines_list = []
    for label in selected.ticket_horses:
        no_match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", clean_text(label))
        no = no_match.group(1) if no_match else ""
        trust = context_by_no.get(no, "") or trust_by_no.get(no, "")
        horse_lines_list.append(f"{label}\n{trust}" if trust else label)
    horse_lines = "<br><br>".join(plain_text_to_html(line) for line in horse_lines_list)
    matched = "<br>".join(plain_text_to_html("・" + line) for line in selected.matched_conditions) or "・条件成立"
    ticket_lines = " / ".join(selected.tickets)
    st.markdown(
        '<div class="ka-dashboard-card">'
        f'<div class="ka-dashboard-value">{horse_lines}</div>'
        f'<div class="ka-note">一致条件<br>{matched}<br><br>'
        f'採用馬券<br>{plain_text_to_html(selected.ticket_type)} {plain_text_to_html(selected.label)} '
        f'{plain_text_to_html(ticket_lines)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_investment_audit(decision: InvestmentDecision) -> None:
    if not decision.audit_rows:
        return
    with st.expander("監査モード：馬券戦略選択", expanded=False):
        st.dataframe(pd.DataFrame(decision.audit_rows), use_container_width=True, hide_index=True)


def render_recommended_betting(result: PredictionResult) -> list[BettingRecommendation]:
    if result.race_mode != "jra":
        return []
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        table = result.horse_evaluation
    recommendations = build_betting_recommendations(table)
    st.subheader("今回のおすすめ買い方")
    if not recommendations:
        st.markdown(
            '<div class="ka-dashboard-card">'
            '<div class="ka-dashboard-title">今回は見送り推奨</div>'
            '<div class="ka-note">現在レースで正式条件に一致する買い方がありません。'
            'ランキング上位を無理に表示せず、条件が成立した時だけ表示します。</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        render_recommendation_audit()
        return []
    blocks = []
    for item in recommendations:
        roi = f"期待回収率：{item.expected_roi:.0f}%" if item.expected_roi is not None else "期待回収率：検証中"
        hit = f"的中率：{item.hit_rate:.1f}%" if item.hit_rate is not None else "的中率：検証中"
        matched = "<br>".join(plain_text_to_html("✓ " + line) for line in item.matched_conditions) or "✓ 条件一致"
        ticket_lines = "<br>".join(plain_text_to_html(line) for line in item.tickets) or "買い目なし"
        blocks.append(
            '<div class="ka-dashboard-card">'
            f'<div class="ka-dashboard-title">{plain_text_to_html(item.stars)}</div>'
            f'<div class="ka-dashboard-value">{plain_text_to_html(item.ticket_type)}　{plain_text_to_html(item.label)}</div>'
            f'<div class="ka-note">一致条件<br>{matched}<br><br>'
            f'過去実績<br>{plain_text_to_html(str(item.sample_races) + "R")} / {plain_text_to_html(roi)} / {plain_text_to_html(hit)}<br><br>'
            f'実際の買い目（{item.ticket_count}点）<br>{ticket_lines}</div>'
            '</div>'
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)
    render_recommendation_audit()
    return recommendations


def render_recommendation_audit() -> None:
    if not LAST_MATCH_AUDIT:
        return
    with st.expander("監査モード：おすすめ買い方判定", expanded=False):
        st.dataframe(pd.DataFrame(LAST_MATCH_AUDIT), use_container_width=True, hide_index=True)


def render_purchase_condition_recommendations(
    result: PredictionResult,
    betting_recommendations: list[BettingRecommendation] | None = None,
) -> None:
    if result.race_mode != "jra":
        return
    betting_recommendations = betting_recommendations or []
    adoption_map = adoption_map_from_recommendations(betting_recommendations)
    adopted_horse_numbers = set(adoption_map)
    if not adopted_horse_numbers:
        return
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        table = result.horse_evaluation
    recommendations = build_purchase_condition_recommendations(
        table,
        adopted_horse_numbers=adopted_horse_numbers,
        adoption_map=adoption_map,
    )
    if not recommendations:
        return
    st.subheader("今回のおすすめ購入条件")
    blocks = []
    for item in recommendations:
        condition_lines = "<br>".join(plain_text_to_html(label) for label in item.condition_labels)
        horses = " / ".join(item.matched_horses)
        adopted = " / ".join(item.adopted_betting_labels)
        tickets = " / ".join(item.recommended_ticket_types) or plain_text_to_html(item.ticket_type)
        blocks.append(
            '<div class="ka-dashboard-card">'
            f'<div class="ka-dashboard-title">{plain_text_to_html(item.stars)} {plain_text_to_html(tickets)}</div>'
            f'<div class="ka-dashboard-value">{plain_text_to_html(horses)}</div>'
            f'<div class="ka-note">一致条件<br>{condition_lines}<br><br>'
            f'推奨: {plain_text_to_html(tickets)}<br>'
            f'過去実績: 対象{item.target_horses}頭・{item.target_races}R<br>'
            f'単勝回収率{item.win_roi:.0f}% / 複勝回収率{item.place_roi:.0f}%<br>'
            f'勝率{item.win_rate:.1f}% / 複勝率{item.place_rate:.1f}%<br>'
            f'信頼度: {plain_text_to_html(item.reliability)} / score {item.condition_score:.1f}<br>'
            f'採用買い方: {plain_text_to_html(adopted)}</div>'
            '</div>'
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)


def render_power_map(result: PredictionResult) -> None:
    rows = sorted_display_rows(result)
    if not rows:
        return
    st.subheader("勢力図")
    blocks = []
    for group, _label in POWER_GROUPS:
        nums = group_numbers(rows, group)
        if not nums:
            continue
        blocks.append(
            f'<div class="ka-power-group"><span class="ka-chip {group.lower()}">{plain_text_to_html(group)}</span>'
            f'<div class="ka-dashboard-value">{plain_text_to_html("・".join(nums))}</div></div>'
        )
    if blocks:
        st.markdown("".join(blocks), unsafe_allow_html=True)


def render_race_flow(result: PredictionResult) -> None:
    rows = sorted_display_rows(result)
    if not rows:
        return
    st.subheader("レース展開・レース考察")
    raw_flow = extract_raw_section(result, ["展開予想"])
    pace = extract_named_value(raw_flow, ["ペース", "想定ペース"]) or "既存展開考察を確認"
    front, middle, back, unknown = running_position_groups(rows)
    body = [
        '<div class="ka-dashboard-card">',
        '<div class="ka-dashboard-title">前半の展開予想</div>',
        f'<div class="ka-chip">{plain_text_to_html("想定ペース：" + pace)}</div>',
        flow_line_html("前方", front),
        flow_line_html("中団", middle),
        flow_line_html("後方", back),
    ]
    if unknown:
        body.append(flow_line_html("未分類", unknown))
    body.append("</div>")
    flow_review = race_flow_review_lines(rows, pace)
    if flow_review:
        body.append('<div class="ka-dashboard-card"><div class="ka-dashboard-title">レース考察</div>')
        body.append(
            '<div class="ka-note">'
            + plain_text_to_html("\n\n".join(flow_review))
            + "</div>"
        )
        body.append("</div>")
    st.markdown("".join(body), unsafe_allow_html=True)

    review = strip_section_title(result.ai_race_review, "AIレース考察")
    if clean_multiline(review):
        with st.expander("展開考察本文", expanded=False):
            st.markdown(f'<div class="ka-section">{plain_text_to_html(clean_multiline(review))}</div>', unsafe_allow_html=True)


def render_horse_summary_cards(result: PredictionResult) -> None:
    rows = sorted_display_rows_with_value_support(result)
    if not rows:
        st.info("馬別サマリーは未取得です。")
        return
    overall_rows_by_horse = build_overall_rows_by_horse(result.overall_table)

    def card_html(row: dict[str, Any]) -> str:
        horse_key = normalize_horse_number_key(pick(row, "馬番", "馬"))
        return horse_summary_card_html(row, result.race_mode, overall_rows_by_horse.get(horse_key, {}), getattr(result, "race_info", {}) or {})

    st.subheader("馬別サマリーカード")
    visible = [row for row in rows if display_group_from_row(row) != "Z"]
    hidden = [row for row in rows if display_group_from_row(row) == "Z"]
    for row in visible:
        st.markdown(card_html(row), unsafe_allow_html=True)
    if hidden:
        with st.expander("Zグループの馬も表示", expanded=False):
            for row in hidden:
                st.markdown(card_html(row), unsafe_allow_html=True)


def render_backtest_reference(result: PredictionResult) -> None:
    rows = sorted_display_rows_with_value_support(result)
    references = value_reference_rows()
    honmei = next((row for row in rows if display_mark_from_row(row) == "◎"), None)
    current_ref = current_mark_reference(honmei) if honmei else None
    blocks: list[str] = []
    for item in references:
        blocks.append(backtest_reference_line(item))
    if current_ref:
        blocks.append("現在◎参考： " + backtest_reference_line(current_ref))
    value_rows = [row for row in rows if truthy_display(pick(row, "value_signal"))]
    if value_rows:
        value_bits = []
        for row in value_rows:
            value_bits.append(
                join_nonempty(
                    [
                        pick(row, "馬番", "馬"),
                        pick(row, "馬名"),
                        clean_text(pick(row, "value_reason")),
                    ],
                    sep=" ",
                )
            )
        blocks.append("妙味あり候補： " + " / ".join(value_bits))
    if not blocks:
        return
    st.subheader("過去検証参考")
    st.caption("現行印を過去データで続けた場合の参考値です。予想順位・印・能力値には反映していません。")
    body = "<br>".join(plain_text_to_html(block) for block in blocks if clean_text(block))
    st.markdown(f'<div class="ka-dashboard-card"><div class="ka-note">{body}</div></div>', unsafe_allow_html=True)


def backtest_reference_line(item: dict[str, Any]) -> str:
    label = clean_text(item.get("label")) or "参考"
    sample = item.get("sample")
    hit_rate = item.get("hit_rate")
    roi = item.get("roi")
    top1 = item.get("top1_excluded_roi")
    category = clean_text(item.get("category")) or "未校正"
    parts = [
        label,
        f"{int(to_float(sample) or 0)}件",
        f"的中{format_number(hit_rate)}%" if to_float(hit_rate) is not None else "",
        f"回収{format_number(roi)}%" if to_float(roi) is not None else "",
        f"最大除外{format_number(top1)}%" if to_float(top1) is not None else "",
        f"→ {category}",
    ]
    return "｜".join(part for part in parts if clean_text(part))


def card_pick(row: dict[str, Any], index_row: dict[str, Any], *names: str) -> Any:
    value = pick(row, *names)
    if not is_missing_value(value):
        return value
    return pick(index_row, *names)


def merged_card_source(row: dict[str, Any], index_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(index_row or {})
    for key, value in (row or {}).items():
        if not is_missing_value(value):
            merged[key] = value
    return merged


def ability_value_for_card(row: dict[str, Any], index_row: dict[str, Any]) -> Any:
    return card_pick(row, index_row, "horse_score_v4", "能力評価値", "ability_display_score", "raw_score", "_raw_score")


def clamp_ability_display_value(value: Any) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(round(max(0.0, min(100.0, number))))


def ability_bar_html(row: dict[str, Any], index_row: dict[str, Any]) -> str:
    display_value = clamp_ability_display_value(ability_value_for_card(row, index_row))
    if display_value is None:
        return ""
    return (
        '<div class="ka-ability-wrap">'
        '<div class="ka-ability-head"><span>能力評価</span>'
        f'<span>{display_value}</span></div>'
        '<div class="ka-ability-track">'
        f'<div class="ka-ability-fill" style="width:{display_value}%"></div>'
        '</div></div>'
    )


def signed_material_value(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    if abs(number) < 0.05:
        return "±0"
    sign = "+" if number > 0 else ""
    return f"{sign}{format_number(number)}"


def index_material_badge(label: str, value: Any) -> tuple[str, str] | None:
    number = to_float(value)
    if number is None:
        return None
    if number >= 60:
        return f"{label}◎", "plus"
    if number >= 45:
        return f"{label}○", "neutral"
    return f"{label}△", "minus"


def initial_blinker_source(
    row: dict[str, Any],
    race_mode: str,
    index_row: dict[str, Any] | None = None,
) -> str:
    if race_mode != "jra":
        return ""
    index_row = index_row or {}
    fields = [
        "補足",
        "supplement_note",
        "評価／検討材料",
        "評価/検討材料",
        "調教/評価/検討材料",
        "馬具",
        "新聞コメント",
        "厩舎コメント",
        "stable_comment",
        "表示コメント",
        "display_comment",
    ]
    text = " ".join(clean_text(card_pick(row, index_row, field)) for field in fields)
    if not text:
        return ""
    first_blinker_patterns = ["初ブリンカー", "初Ｂ", "初B", "B初", "Ｂ初", "ブリンカー初", "初めてブリンカー"]
    if any(pattern in text for pattern in first_blinker_patterns):
        return text
    return ""


def ability_material_badges(
    row: dict[str, Any],
    index_row: dict[str, Any],
    race_mode: str,
) -> list[tuple[str, str]]:
    badges: list[tuple[str, str]] = []
    age_adjustment = card_pick(row, index_row, "年齢補正", "age_adjustment")
    age_text = signed_material_value(age_adjustment)
    if age_text:
        tone = "plus" if age_text.startswith("+") else "minus" if age_text.startswith("-") else "neutral"
        badges.append((f"年齢{age_text}", tone))
    else:
        badges.append(("年齢±0", "neutral"))

    for badge in (
        index_material_badge("距離", card_pick(row, index_row, "距離指数")),
        index_material_badge("コース", card_pick(row, index_row, "コース指数")),
    ):
        if badge:
            badges.append(badge)

    state = state_label_from_row(row)
    if state:
        if any(key in state for key in ["上昇", "良化", "安定", "持ち直し", "反発"]):
            badges.append((f"状態{state}", "plus"))
        elif any(key in state for key in ["下降", "急落", "不安", "波"]):
            badges.append((f"状態{state}", "minus"))
        else:
            badges.append((f"状態{state}", "neutral"))

    weight = compact_weight_text(row)
    if weight:
        if "前走データなし" in weight:
            badges.append(("斤量不明", "neutral"))
        elif "+" in weight or "＋" in weight:
            badges.append(("斤量増", "minus"))
        elif "-" in weight or "－" in weight:
            badges.append(("斤量減", "plus"))
        elif "±" in weight or "ﾂｱ" in weight:
            badges.append(("斤量±0", "neutral"))

    jockey = compact_jockey_text(row)
    if jockey:
        if "乗替" in jockey or "乗り替" in jockey or "乗り替わり" in jockey:
            badges.append(("乗替△", "minus"))
        elif "継続" in jockey:
            badges.append(("継続", "plus"))

    if initial_blinker_source(row, race_mode, index_row):
        badges.append(("初B", "info"))

    pace_mark = clean_text(card_pick(row, index_row, "展開印", "pace_mark"))
    if pace_mark:
        badges.append((f"展開{pace_mark}", "neutral"))

    return badges[:8]


def material_badges_html(badges: list[tuple[str, str]]) -> str:
    if not badges:
        return ""
    parts = [
        f'<span class="ka-material-badge {plain_text_to_html(tone)}">{plain_text_to_html(label)}</span>'
        for label, tone in badges
    ]
    return '<div class="ka-material-badges">' + "".join(parts) + "</div>"


def horse_summary_card_html(
    row: dict[str, Any],
    race_mode: str,
    overall_row: dict[str, Any] | None = None,
    race_info: dict[str, Any] | None = None,
) -> str:
    index_row = row if overall_row is None else overall_row
    recent_source = merged_card_source(row, index_row)
    mark = display_mark_from_row(row)
    no = clean_text(pick(row, "馬番", "馬"))
    name = clean_text(pick(row, "馬名"))
    odds = format_odds(pick(row, "単勝オッズ", "オッズ", "単勝"))
    group = display_group_from_row(row)
    age = clean_text(pick(row, "馬年齢", "性齢", "馬齢")) or "—"
    weight = compact_weight_text(row)
    jockey = compact_jockey_text(row)
    style = display_running_style_from_row(row) or "データなし"
    star = star_summary_text(index_row)
    distance = index_summary_text("距離", pick(index_row, "距離指数"))
    course = index_summary_text("コース", pick(index_row, "コース指数"))
    state = state_label_from_row(row)
    recent_summary = recent_races_summary_text(recent_source)
    recent_detail = rich_recent_races_detail_text(recent_source)
    condition_fit = resolved_condition_fit(recent_source, race_info)
    condition_badge = condition_fit_badge_text(recent_source, race_info)
    condition_status = clean_text(condition_fit.get("condition_fit_data_status")) or "—"
    practical_warning = clean_text(card_pick(row, index_row, "practical_warning_reason"))
    legacy_recent_detail = recent3_detail_text(index_row)
    if clean_text(legacy_recent_detail):
        if clean_text(recent_detail) and "データなし" not in clean_text(recent_detail):
            recent_detail = f"{recent_detail}\n\n{legacy_recent_detail}"
        else:
            recent_detail = legacy_recent_detail
    corner4 = clean_text(card_pick(row, index_row, "4隗剃ｺ域Φ", "4角予想", "4角評価", "corner4_evaluation"))
    straight = clean_text(card_pick(row, index_row, "逶ｴ邱夊ｩ穂ｾ｡", "直線評価", "straight_evaluation"))
    ability_raw = ability_value_for_card(row, index_row)
    ability_display = clamp_ability_display_value(ability_raw)
    ability_bar = ability_bar_html(row, index_row)
    material_badges = ability_material_badges(row, index_row, race_mode)
    material_badges_markup = material_badges_html(material_badges)
    material_labels = " ／ ".join(label for label, _tone in material_badges)
    first_blinker_source = initial_blinker_source(row, race_mode, index_row)
    training_label = clean_text(card_pick(row, index_row, "training_display"))
    stable_comment = clean_text(card_pick(row, index_row, "stable_comment_display"))
    course_material = clean_text(card_pick(row, index_row, "course_material_label"))
    course_material_detail = clean_text(card_pick(row, index_row, "course_material_detail"))
    netkeiba_favorable = clean_text(card_pick(row, index_row, "netkeiba_favorable_label"))
    value_signal = truthy_display(card_pick(row, index_row, "value_signal"))
    value_reason = clean_text(card_pick(row, index_row, "value_reason"))
    value_plus = card_pick(row, index_row, "value_plus_materials")
    value_minus = card_pick(row, index_row, "value_minus_materials")
    mark_part = mark if mark else ""
    quick_items = [
        f"{age}　{weight}" if weight else age,
        jockey,
        f"脚質：{style}",
        star,
        distance,
        course,
        f"条件実績：{condition_badge}" if condition_badge else "",
        f"状態：{state}",
    ]
    if training_label:
        quick_items.append(training_label)
    if stable_comment:
        quick_items.append(stable_comment)
    if course_material:
        quick_items.append(f"コース：{course_material}")
    if netkeiba_favorable:
        quick_items.append(netkeiba_favorable)
    if value_signal:
        quick_items.append(f"妙味あり：{value_reason}")
    horse_score_v4 = card_pick(row, index_row, "horse_score_v4")
    race_rank_v4 = card_pick(row, index_row, "race_rank_v4")
    if not is_missing_value(horse_score_v4):
        quick_items.insert(0, f"Horse Score：{format_number(horse_score_v4)}（Race Rank {format_number(race_rank_v4)}）")
    if recent_summary:
        quick_items.append(f"近3走\n{recent_summary}")
    if practical_warning:
        quick_items.append(f"warning：{practical_warning}")
    if corner4:
        quick_items.append(f"4角：{corner4}")
    if straight:
        quick_items.append(f"直線：{straight}")
    quick = "<br>".join(plain_text_to_html(item) for item in quick_items if clean_text(item))
    central_lines = central_card_lines(row) if race_mode == "jra" else []
    detail_lines = [
        "出走馬詳細",
        f"【{group}】{mark_part} {no} {name}".strip(),
        f"{age}",
        weight,
        jockey,
        f"脚質：{style}",
        f"オッズ：{odds or '—'}",
        "",
        f"距離指数：{format_index_value(pick(index_row, '距離指数'))}",
        f"コース指数：{format_index_value(pick(index_row, 'コース指数'))}",
        f"★最高指数：{format_star_value(pick(index_row, '★最高指数', 'star_max_index'))}",
        f"状態：{state}",
        "",
        "近3走",
        recent_detail,
        f"3走平均：{format_index_value(pick(index_row, '平均指数', '3走平均', '近3走平均'))}",
        "",
        f"★該当走：{clean_text(pick(index_row, '★該当走', 'star_max_race')) or '—'}",
        f"★条件：{star_condition_text_from_row(index_row) or '—'}",
        f"条件実績：{condition_badge or '—条件実績なし'}",
        f"条件実績理由：{clean_text(condition_fit.get('condition_fit_reason')) or '—'}",
        f"condition data status：{condition_status}",
        f"条件実績該当走：{condition_fit_matched_runs_text(condition_fit)}",
        f"warning：{practical_warning or '—'}",
        f"能力評価値：{format_number(ability_raw) or '—'}",
        f"能力評価表示：{ability_display if ability_display is not None else '—'}",
        f"表示材料：{material_labels or '—'}",
        "数値補正：なし（既存の能力評価値をそのまま表示）",
        "二重補正回避：年齢・距離・コース・斤量・騎手は通常カードの材料表示のみ",
        f"調教表示：{training_label or '—'}",
        f"厩舎コメント：{stable_comment or '—'}",
        f"展開/コース：{course_material or '—'}",
        f"展開/コース監査：{course_material_detail or '—'}",
        f"netkeiba推定：{netkeiba_favorable or '—'}",
        f"妙味あり：{'該当' if value_signal else '—'}",
        f"妙味理由：{value_reason or '—'}",
        f"妙味＋材料：{reason_list_text(value_plus) or '—'}",
        f"妙味－材料：{reason_list_text(value_minus) or '—'}",
        f"近3走指数推移：{recent3_text_from_row(index_row, row)}",
        f"4角：{corner4 or '—'}　直線：{straight or '—'}",
        f"コメント：{short_comment_from_row(row)}",
        f"穴候補：{'該当' if truthy_display(pick(row, '穴候補', 'hole_candidate')) else '—'}　注意馬：{'該当' if truthy_display(pick(row, '注意馬', 'watch_horse')) else '—'}",
    ]
    if not is_missing_value(horse_score_v4):
        positive_reasons = card_pick(row, index_row, "positive_reasons_v4")
        negative_reasons = card_pick(row, index_row, "negative_reasons_v4")
        detail_lines.extend(
            [
                "",
                f"Horse Score Ver4：{format_number(horse_score_v4)}",
                f"Race Rank Ver4：{format_number(race_rank_v4)}",
                f"評価理由：{reason_list_text(positive_reasons) or '—'}",
                f"注意理由：{reason_list_text(negative_reasons) or '—'}",
                f"✓理由：{clean_text(card_pick(row, index_row, 'watch_reason_v4')) or '—'}",
            ]
        )
    if race_mode == "jra":
        detail_lines.extend(
            [
                f"初B：{'該当' if first_blinker_source else '—'}",
                f"初B取得元：{shorten_text(first_blinker_source, 80) if first_blinker_source else '—'}",
            ]
        )
    if central_lines:
        detail_lines.extend(["", *central_lines])
    title = f"【{group}】{mark_part} {no} {name}　{odds}".strip()
    if first_blinker_source:
        title = f"{title}　初B"
    return (
        f'<div class="ka-horse-card">'
        f'<details><summary>'
        f'<div class="ka-horse-title-line"><span class="ka-chip {group.lower()}">{plain_text_to_html(group)}</span>'
        f'<span>{plain_text_to_html(title)}</span></div>'
        f'<div class="ka-horse-quick">{quick}</div>'
        f'{ability_bar}'
        f'{material_badges_markup}'
        f'<div class="ka-muted">詳細を見る</div>'
        f'</summary><div class="ka-horse-detail">{plain_text_to_html(chr(10).join(line for line in detail_lines if clean_text(line)))}</div></details>'
        f'</div>'
    )


def result_rows(result: PredictionResult) -> list[dict[str, Any]]:
    for table in (result.horse_evaluation, result.overall_table):
        if table is not None and not getattr(table, "empty", False):
            return table.to_dict("records")
    return []


def sorted_display_rows(result: PredictionResult) -> list[dict[str, Any]]:
    rows = result_rows(result)
    group_order = {"SS": 0, "A": 1, "B": 2, "C": 3, "Z": 4}
    mark_order = {"◎": 0, "○": 1, "▲": 2, "△": 3, "✓": 4, "✔": 4, "": 9}

    def sort_key(row: dict[str, Any]) -> tuple[int, int, float, int, str]:
        group = display_group_from_row(row)
        mark = display_mark_from_row(row)
        score = to_float(pick(row, "horse_score_v4", "総合評価監査点", "final_mark_score", "総合評価点", "_最終印点", "AI点", "normalized_ai_score"))
        horse_no = to_float(pick(row, "馬番", "馬"))
        return (
            group_order.get(group, 9),
            mark_order.get(mark, 8),
            -(score if score is not None else -9999.0),
            int(horse_no) if horse_no is not None else 999,
            clean_text(pick(row, "馬名")),
        )

    return sorted(rows, key=sort_key)


def sorted_display_rows_with_value_support(result: PredictionResult) -> list[dict[str, Any]]:
    rows = sorted_display_rows(result)
    if not rows:
        return []
    overall_rows_by_horse = build_overall_rows_by_horse(result.overall_table)
    merged_rows: list[dict[str, Any]] = []
    for row in rows:
        horse_key = normalize_horse_number_key(pick(row, "馬番", "馬"))
        merged_rows.append(merged_card_source(row, overall_rows_by_horse.get(horse_key, {})))
    enriched = attach_value_signals(merged_rows, result.race_mode)
    out: list[dict[str, Any]] = []
    for row, value_row in zip(rows, enriched, strict=False):
        copied = dict(row)
        for field in VALUE_FIELD_NAMES:
            if field in value_row:
                copied[field] = value_row[field]
        out.append(copied)
    return out


def _horse_count_text(result: PredictionResult) -> str:
    info = result.race_info or {}
    count = pick(info, "頭数", "horse_count", "runners", "出走頭数")
    if not count:
        count = len(result_rows(result))
    number = to_float(count)
    if number is not None:
        return f"{int(number)}頭"
    text = clean_text(count)
    return text if "頭" in text else f"{text}頭" if text else ""


def recent3_text_from_row(row: dict[str, Any], trend_row: dict[str, Any] | None = None) -> str:
    values = [
        pick(row, "3走前", "race3", "three_back_index"),
        pick(row, "2走前", "race2", "two_back_index"),
        pick(row, "前走", "race1", "last_index"),
    ]
    parts = [format_number(value) if not is_missing_value(value) else "-" for value in values]
    trend = clean_text(pick(trend_row or row, "近3走傾向", "recent3_trend"))
    if not trend:
        return " → ".join(parts)
    arrow = "↗" if trend in {"連続上昇", "上昇", "持ち直し", "反発"} else "↘" if trend in {"連続下降", "下降", "急落"} else "→"
    return f"{' → '.join(parts)}　{arrow} {trend}"


def star_text_from_row(row: dict[str, Any]) -> str:
    star = pick(row, "★最高指数", "star_max_index")
    if is_missing_value(star):
        return "なし"
    star_text = format_number(star) or clean_text(star)
    race = clean_text(pick(row, "★該当走", "star_max_race"))
    condition_text = star_condition_text_from_row(row)
    pieces = [f"★{star_text}"]
    if condition_text:
        pieces.append(condition_text)
    if race:
        pieces.append(race)
    return "｜".join(pieces)


def star_condition_text_from_row(row: dict[str, Any]) -> str:
    condition = clean_text(pick(row, "★条件", "star_max_condition"))
    if condition:
        return condition
    level = clean_text(pick(row, "star_match_level"))
    return "今回と同条件" if level and level != "none" else ""


def condition_fit_matched_runs_text(condition_fit: dict[str, Any]) -> str:
    runs = condition_fit.get("matched_past_runs") if isinstance(condition_fit, dict) else []
    if not isinstance(runs, list) or not runs:
        return "—"
    labels: list[str] = []
    for run in runs[:3]:
        if not isinstance(run, dict):
            continue
        label = clean_text(run.get("label"))
        venue = clean_text(run.get("venue"))
        distance = clean_text(run.get("distance"))
        distance_text = f"{distance}m" if distance and distance.isdigit() else distance
        finish = clean_text(run.get("finish"))
        index = clean_text(run.get("time_index"))
        parts = [label, venue, distance_text, finish, f"指数{index}" if index else ""]
        text = " ".join(part for part in parts if part)
        if text:
            labels.append(text)
    return " / ".join(labels) if labels else "—"


def truthy_display(value: Any) -> bool:
    if is_missing_value(value):
        return False
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    return text not in {"", "-", "なし", "false", "0", "no", "nan", "none", "×"}


def display_group_from_row(row: dict[str, Any]) -> str:
    group = clean_text(pick(row, "group_v4", "グループ", "display_group"))
    if group in {"SS", "A", "B", "C", "Z"}:
        return group
    return display_group_from_mark(display_mark_from_row(row))


def display_group_from_mark(mark: Any) -> str:
    text = clean_text(mark)
    if text == "◎":
        return "SS"
    if text in {"○", "▲"}:
        return "A"
    if text == "△":
        return "B"
    if text in {"✓", "✔"}:
        return "C"
    return "Z"


def original_mark_from_row(row: dict[str, Any]) -> str:
    return clean_text(pick(row, "元印", "original_mark", "旧印", "old_final_mark", "最終印"))


def group_numbers(rows: list[dict[str, Any]], group: str) -> list[str]:
    return [clean_text(pick(row, "馬番", "馬")) for row in rows if display_group_from_row(row) == group and clean_text(pick(row, "馬番", "馬"))]


def flow_line_html(label: str, nums: list[str]) -> str:
    value = "・".join(nums) if nums else "—"
    return f'<div class="ka-power-row"><b>{plain_text_to_html(label)}</b><br>{plain_text_to_html(value)}</div>'


def running_position_groups(rows: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str], list[str]]:
    front: list[str] = []
    middle: list[str] = []
    back: list[str] = []
    unknown: list[str] = []
    for row in rows:
        no = clean_text(pick(row, "馬番", "馬"))
        if not no:
            continue
        style = display_running_style_from_row(row)
        if style in {"逃げ", "先行"}:
            front.append(no)
        elif style == "差し":
            middle.append(no)
        elif style == "追込":
            back.append(no)
        else:
            unknown.append(no)
    return front, middle, back, unknown


def horse_refs(rows: list[dict[str, Any]], numbers: list[str], limit: int = 4) -> str:
    by_number = {clean_text(pick(row, "馬番", "馬")): row for row in rows}
    refs = []
    for no in numbers[:limit]:
        name = clean_text(pick(by_number.get(no, {}), "馬名"))
        refs.append(f"{no}番{name}" if name else f"{no}番")
    if len(numbers) > limit:
        refs.append("ほか")
    return "・".join(refs) if refs else "該当なし"


def race_flow_review_lines(rows: list[dict[str, Any]], pace: str) -> list[str]:
    front, middle, back, _unknown = running_position_groups(rows)
    upper = [
        clean_text(pick(row, "馬番", "馬"))
        for row in rows
        if display_group_from_row(row) in {"SS", "A"} and clean_text(pick(row, "馬番", "馬"))
    ]
    middle_force = [
        clean_text(pick(row, "馬番", "馬"))
        for row in rows
        if display_group_from_row(row) in {"B", "C"} and clean_text(pick(row, "馬番", "馬"))
    ]
    lower_front = [
        clean_text(pick(row, "馬番", "馬"))
        for row in rows
        if display_group_from_row(row) in {"C", "Z"}
        and clean_text(pick(row, "馬番", "馬")) in front
    ]
    lines = [
        f"【スタート】\n{horse_refs(rows, front)}がハナ・好位候補。{horse_refs(rows, middle)}は中団から運ぶ想定です。",
        f"【前半】\n想定ペースは{pace}。先頭に行く馬と、最後まで残る評価は分けて確認します。",
        f"【4角】\n勢力図上位は{horse_refs(rows, upper)}。ここが直線へ向けて進出する中心です。",
        f"【直線】\n中心は{horse_refs(rows, upper, 3)}。相手・穴では{horse_refs(rows, middle_force, 4)}まで比較対象です。",
    ]
    if lower_front:
        lines.append(
            "【展開注意】\n"
            f"{horse_refs(rows, lower_front)}は勢力図では下位寄りですが、単騎逃げや楽な先行なら前残り余地があります。"
        )
    return lines


def extract_named_value(text: str, names: list[str]) -> str:
    body = clean_multiline(text)
    if not body:
        return ""
    for line in body.splitlines():
        compact = clean_text(line)
        for name in names:
            if compact.startswith(f"{name}：") or compact.startswith(f"{name}:"):
                return compact.split("：", 1)[-1].split(":", 1)[-1].strip()
    return ""


def compact_weight_text(row: dict[str, Any]) -> str:
    detail = clean_text(pick(row, "斤量詳細"))
    if detail:
        detail = detail.replace("前走比", "")
        detail = re.sub(r"（\s*([+\-＋－±]?\d+(?:\.\d+)?)kg\s*）", lambda m: f"（{normalize_sign(m.group(1))}）", detail)
        detail = detail.replace("＋", "+").replace("－", "-")
        return detail
    weight = format_number(pick(row, "斤量"))
    return f"{weight}kg" if weight else ""


def normalize_sign(value: str) -> str:
    text = clean_text(value).replace("＋", "+").replace("－", "-")
    if text in {"0", "0.0", "+0", "+0.0", "-0", "-0.0", "±0.0"}:
        return "±0"
    if text.startswith("+"):
        return text
    if text.startswith("-") or text.startswith("±"):
        return text
    return f"+{text}"


def compact_jockey_text(row: dict[str, Any]) -> str:
    detail = clean_text(pick(row, "騎手詳細"))
    jockey = clean_text(pick(row, "騎手", "jockey"))
    if detail:
        if "前走データなし" in detail:
            return jockey or detail.split("【", 1)[0]
        return detail.replace("【乗り替わり】", "【乗替】")
    return jockey


def compact_table_jockey_text(row: dict[str, Any]) -> str:
    detail = compact_jockey_text(row)
    if "【継続】" in detail:
        return detail.replace("【継続】", "（継）")
    if "【乗替】" in detail:
        return detail.replace("【乗替】", "（替）")
    return detail or "—"


def short_running_style(row: dict[str, Any]) -> str:
    style = display_running_style_from_row(row)
    return {"逃げ": "逃", "先行": "先", "差し": "差", "追込": "追"}.get(style, style or "—")


def format_index_value(value: Any) -> str:
    if is_missing_value(value):
        return "—"
    number = to_float(value)
    if number is None:
        return clean_text(value) or "—"
    return f"{number:.1f}".rstrip("0").rstrip(".")


def normalize_horse_number_key(value: Any) -> str:
    number = to_float(value)
    if number is not None and number.is_integer():
        return str(int(number))
    return clean_text(value)


def build_overall_rows_by_horse(table: Any) -> dict[str, dict[str, Any]]:
    if table is None or getattr(table, "empty", False):
        return {}
    rows_by_horse: dict[str, dict[str, Any]] = {}
    for row in table.to_dict("records"):
        horse_key = normalize_horse_number_key(pick(row, "馬番", "馬"))
        if horse_key:
            rows_by_horse[horse_key] = row
    return rows_by_horse


def index_summary_text(label: str, value: Any) -> str:
    formatted = format_index_value(value)
    return f"{label}{formatted}" if formatted != "—" else f"{label}—"


def format_star_value(value: Any) -> str:
    formatted = format_index_value(value)
    return "該当なし" if formatted == "—" else formatted


def star_summary_text(row: dict[str, Any]) -> str:
    value = format_star_value(pick(row, "★最高指数", "star_max_index"))
    return f"★{value}" if value != "該当なし" else "★該当なし"


def state_label_from_row(row: dict[str, Any]) -> str:
    existing = clean_text(pick(row, "状態", "form_state"))
    if existing:
        return existing
    trend = clean_text(pick(row, "近3走傾向", "recent3_trend"))
    if trend in {"連続上昇", "上昇"}:
        return "上昇"
    if trend in {"横ばい", "安定"}:
        return "安定"
    if trend in {"連続下降", "下降", "急落"}:
        return "下降"
    if trend in {"持ち直し", "反発"}:
        return "反発"
    if trend in {"判定保留", "未判定"}:
        return "判定なし"
    volatility = to_float(pick(row, "recent3_volatility"))
    if volatility is not None and volatility >= 18:
        return "波あり"
    return "判定なし"


def recent3_detail_text(row: dict[str, Any]) -> str:
    parts = []
    for label, index_name, condition_names in [
        ("3走前", "3走前", ["3走前条件", "three_back_condition"]),
        ("2走前", "2走前", ["2走前条件", "two_back_condition"]),
        ("前走", "前走", ["前走条件", "last_condition"]),
    ]:
        index = format_index_value(pick(row, index_name))
        condition = clean_text(pick(row, *condition_names))
        parts.append(f"{label}：{condition + ' ' if condition else ''}{index}")
    return "\n↓\n".join(parts)


def central_card_lines(row: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    training = training_display(row, "jra").get("display", "")
    stable = clean_text(pick(row, "厩舎コメント", "新聞コメント", "stable_comment"))
    if training:
        lines.append(f"調教表示：{training}")
    if stable:
        summary = stable_comment_display(row, "jra")
        if summary:
            lines.append(summary)
        lines.append(f"厩舎コメント全文：{shorten_text(stable, 90)}")
    return lines


def short_comment_from_row(row: dict[str, Any]) -> str:
    comment = clean_text(pick(row, "表示コメント", "display_comment", "一言コメント", "コメント"))
    if comment:
        return shorten_text(comment, 42)
    material = clean_text(pick(row, "評価／検討材料", "評価/検討材料", "評価材料"))
    if not material:
        return "—"
    parts = re.split(r"[／/、,\s]+", material)
    parts = [part for part in parts if part]
    return " / ".join(parts[:2]) if parts else shorten_text(material, 42)


def render_overall_table(result: PredictionResult) -> None:
    st.subheader("出走馬詳細分析表")
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        st.info("出走馬詳細分析表は未取得です。")
        return

    append_nar_star_display_trace(result, "09 app.py display DataFrame creation", table)

    overall_rows_by_horse = build_overall_rows_by_horse(table)

    rows = sorted_display_rows_with_value_support(result)
    display_table = build_detail_analysis_table(rows, overall_rows_by_horse, result.race_mode)
    append_nar_star_display_trace(result, "11 Streamlit detail table before st.dataframe", display_table)
    st.dataframe(display_table, use_container_width=True, hide_index=True)


def build_detail_analysis_table(
    rows: list[dict[str, Any]],
    overall_rows_by_horse: dict[str, dict[str, Any]] | None = None,
    race_mode: str = "jra",
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        no = clean_text(pick(row, "馬番", "馬"))
        name = clean_text(pick(row, "馬名"))
        if overall_rows_by_horse is None:
            index_row = row
        else:
            horse_key = normalize_horse_number_key(pick(row, "馬番", "馬"))
            index_row = overall_rows_by_horse.get(horse_key, {})
        record = {
            "グループ": display_group_from_row(row),
            "馬": join_nonempty([no, name], sep=" "),
            "オッズ": format_odds(pick(row, "単勝オッズ", "オッズ", "単勝")) or "—",
            "年齢": clean_text(pick(row, "馬年齢", "性齢", "馬齢")) or "—",
            "騎手": compact_table_jockey_text(row),
            "斤量": compact_weight_text(row).replace("kg", "") or "—",
            "脚質": short_running_style(row),
            "今回の展開": clean_text(pick(row, "pace_material_label", "pace_mark_market", "展開印")) or "—",
            "今回のコース材料": clean_text(pick(row, "course_material_label")) or "—",
            "netkeiba推定": clean_text(pick(row, "netkeiba_favorable_label")) or "—",
            "想定位置": clean_text(pick(row, "estimated_position_label", "position_path_market", "推定位置", "想定位置")) or "位置不明",
            "距離": format_index_value(pick(index_row, "距離指数")),
            "コース": format_index_value(pick(index_row, "コース指数")),
            "★": format_star_value(pick(index_row, "★最高指数", "star_max_index")),
            "3走前": format_index_value(pick(index_row, "3走前")),
            "2走前": format_index_value(pick(index_row, "2走前")),
            "前走": format_index_value(pick(index_row, "前走")),
            "3走平均": format_index_value(pick(index_row, "平均指数", "3走平均", "近3走平均")),
            "状態": state_label_from_row(row),
            "妙味": "妙味あり" if truthy_display(pick(row, "value_signal")) else "—",
            "＋材料": reason_list_text(pick(row, "value_plus_materials")) or "—",
            "－材料": reason_list_text(pick(row, "value_minus_materials")) or "—",
            "コメント": short_comment_from_row(row),
        }
        if race_mode == "jra":
            insert_after = list(record.items())
            record = {}
            for key, value in insert_after:
                record[key] = value
                if key == "脚質":
                    record["調教"] = clean_text(pick(row, "training_display")) or "—"
        records.append(record)
    return pd.DataFrame.from_records(records)


def render_betting_consideration(result: PredictionResult) -> None:
    st.subheader("今回の検討馬券")
    rows = sorted_display_rows(result)
    group_blocks = []
    for group, _label in POWER_GROUPS:
        nums = group_numbers(rows, group)
        if nums:
            group_blocks.append(f"<b>{plain_text_to_html(group)}</b><br>{plain_text_to_html('・'.join(nums))}")
    betting = strip_section_title(result.betting_structure, "今回の馬券構成")
    betting = strip_section_title(betting, "今回の検討馬券")
    body = '<div class="ka-dashboard-card">'
    if group_blocks:
        body += "<br><br>".join(group_blocks)
    if clean_multiline(betting):
        body += '<div class="ka-horse-detail">' + plain_text_to_html(clean_multiline(betting)) + "</div>"
    else:
        body += '<div class="ka-muted">既存馬券構成は未取得です。</div>'
    body += "</div>"
    st.markdown(body, unsafe_allow_html=True)


def render_race_difficulty(result: PredictionResult) -> None:
    rows = []
    if result.overall_table is not None and not getattr(result.overall_table, "empty", False):
        rows = result.overall_table.to_dict("records")
    if not rows and result.horse_evaluation is not None and not getattr(result.horse_evaluation, "empty", False):
        rows = result.horse_evaluation.to_dict("records")
    if not rows:
        return
    first = rows[0]
    gap = clean_text(pick(first, "能力差", "ability_gap_level"))
    difficulty = clean_text(pick(first, "レース難易度", "race_difficulty"))
    reason = clean_text(pick(first, "レース難易度理由", "race_difficulty_reason"))
    if not gap and not difficulty:
        return
    st.subheader("レース難易度")
    body = join_nonempty(
        [
            f"能力差：{gap}" if gap else "",
            f"レース難易度：{difficulty}" if difficulty else "",
            reason,
        ],
        sep="\n",
    )
    st.markdown(f'<div class="ka-section">{plain_text_to_html(body)}</div>', unsafe_allow_html=True)


def render_horse_evaluation(result: PredictionResult) -> None:
    st.subheader("馬評価（全頭）")
    table = result.horse_evaluation
    if table is None or getattr(table, "empty", False):
        st.info("馬評価は未取得です。")
        return

    mode = st.radio(
        "馬評価の表示",
        ["カード表示", "一覧表"],
        horizontal=True,
        key="horse_evaluation_mode",
        label_visibility="collapsed",
    )
    if mode == "一覧表":
        columns = existing_columns(table, HORSE_EVALUATION_COLUMNS)
        st.dataframe(table.loc[:, columns or list(table.columns)], use_container_width=True, hide_index=True)
        return

    for row in table.to_dict("records"):
        st.markdown(horse_evaluation_card_html(row, result.race_mode), unsafe_allow_html=True)


def render_audit_details(result: PredictionResult) -> None:
    table = result.overall_table
    if table is None or getattr(table, "empty", False) or not existing_columns(table, AUDIT_EVALUATION_COLUMNS):
        table = result.horse_evaluation
    if table is None or getattr(table, "empty", False):
        return
    audit_table = build_audit_export_table(table)
    if audit_table.empty:
        return
    with st.expander("監査モード：評価値詳細", expanded=False):
        st.dataframe(audit_table, use_container_width=True, hide_index=True)
        course_rows = course_material_audit_rows(result)
        if course_rows:
            st.caption("展開/コース材料監査（netkeiba推定有利馬とは別表示）")
            st.dataframe(pd.DataFrame(course_rows), use_container_width=True, hide_index=True)
        col1, col2, col3 = st.columns(3)
        base_name = make_download_file_name(result).replace(".png", "")
        col1.download_button(
            "監査CSV",
            data=audit_table_to_csv_bytes(audit_table),
            file_name=f"{base_name}_audit.csv",
            mime="text/csv",
            use_container_width=True,
        )
        col2.download_button(
            "監査JSON",
            data=audit_table_to_json_bytes(audit_table),
            file_name=f"{base_name}_audit.json",
            mime="application/json",
            use_container_width=True,
        )
        col3.download_button(
            "監査MD",
            data=audit_table_to_markdown(audit_table).encode("utf-8"),
            file_name=f"{base_name}_audit.md",
            mime="text/markdown",
            use_container_width=True,
        )


def course_material_audit_rows(result: PredictionResult) -> list[dict[str, Any]]:
    rows = sorted_display_rows_with_value_support(result)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "馬番": pick(row, "馬番", "馬"),
                "馬名": pick(row, "馬名"),
                "展開/コース": pick(row, "course_material_label"),
                "展開/コース詳細": pick(row, "course_material_detail"),
                "netkeiba推定": pick(row, "netkeiba_favorable_label"),
                "netkeiba元値": pick(row, "netkeiba_favorable_source"),
                "推定位置": pick(row, "estimated_position_label"),
                "妙味": "妙味あり" if truthy_display(pick(row, "value_signal")) else "",
                "妙味理由": pick(row, "value_reason"),
            }
        )
    return out


def render_attention_horses(result: PredictionResult) -> None:
    st.subheader("注目馬")
    blocks = [clean_multiline(block) for block in result.attention_horses if clean_multiline(block)]
    if not blocks:
        st.markdown('<div class="ka-section ka-muted">未取得です。</div>', unsafe_allow_html=True)
        return
    for block in blocks:
        st.markdown(f'<div class="ka-section">{plain_text_to_html(block)}</div>', unsafe_allow_html=True)


def horse_evaluation_card_html(row: dict[str, Any], race_mode: str) -> str:
    mark = display_mark_from_row(row)
    no = pick(row, "馬番", "馬")
    name = pick(row, "馬名")
    horse_age = pick(row, "馬年齢", "性齢", "馬齢") or "データなし"
    jockey = pick(row, "騎手", "jockey") or "―"
    style = display_running_style_from_row(row) or "データなし"
    weight_detail = pick(row, "斤量詳細")
    jockey_detail = pick(row, "騎手詳細") or jockey
    odds = format_odds(pick(row, "単勝オッズ", "オッズ", "単勝"))
    market = pick(row, "市場評価")
    ability_value = format_number(pick(row, "能力評価値", "ability_display_score", "raw_score"))
    ability_band = clean_text(pick(row, "能力帯", "ability_band")) or "-"
    class_shift = pick(row, "クラス変動") or "-"
    material = pick(row, "評価／検討材料", "評価/検討材料", "評価材料") or "-"
    horse_type = pick(row, "馬タイプ") or "-"
    comment = pick(row, "表示コメント", "display_comment", "一言コメント", "コメント")
    support_label = "対戦評価" if race_mode == "nar" else "調教評価"
    support_value = (
        pick(row, "対戦評価", "対戦材料", "対戦")
        if race_mode == "nar"
        else pick(row, "調教評価", "調教/評価/検討材料", "状態材料")
    ) or ("未評価" if race_mode == "nar" else "未取得")
    stable_comment = pick(row, "厩舎コメント", "新聞コメント") if race_mode == "jra" else ""
    audit_labels = join_nonempty(
        [
            "穴候補：該当" if clean_text(pick(row, "穴候補", "hole_candidate")) in ("○", "True", "true", "1") else "",
            "注意馬：該当" if clean_text(pick(row, "注意馬", "watch_horse")) in ("○", "True", "true", "1") else "",
        ],
        sep="　",
    )
    card_class = "ka-horse-card watch" if "✓" in str(mark) else "ka-horse-card"
    title = join_nonempty([mark, no, name], sep=" ")
    lines = [
        f"馬年齢：{horse_age}",
        f"脚質：{style}",
        f"斤量：{weight_detail}" if weight_detail else "",
        f"騎手：{jockey_detail}",
        f"単勝：{odds}" if odds else "単勝：―",
        join_nonempty([f"能力評価値：{ability_value}" if ability_value else "", f"能力帯：{ability_band}" if ability_band else ""], sep="　"),
        f"市場評価：{market}" if market else "",
        audit_labels,
        join_nonempty([f"クラス：{class_shift}", f"{support_label}：{support_value}"], sep="　"),
        f"評価材料：{material}",
        f"馬タイプ：{horse_type}",
    ]
    if stable_comment:
        lines.append(f"厩舎コメント：{shorten_text(stable_comment, 84)}")
    if comment:
        lines.append(f"コメント：{comment}")
    content = "<br>".join(plain_text_to_html(line) for line in lines if clean_text(line))
    return f'<div class="{card_class}"><div class="ka-horse-title">{plain_text_to_html(title)}</div><div class="ka-horse-meta">{content}</div></div>'


def display_mark_from_row(row: dict[str, Any]) -> str:
    if "mark_v4" in row and not is_missing_value(row.get("mark_v4")):
        return clean_text(row.get("mark_v4"))
    if "表示印" in row:
        return clean_text(row.get("表示印"))
    if "display_mark" in row:
        return clean_text(row.get("display_mark"))
    return clean_text(pick(row, "印", "最終印"))


def reason_list_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " / ".join(clean_text(item) for item in value if clean_text(item))
    return clean_text(value)


def display_running_style_from_row(row: dict[str, Any]) -> str:
    text = clean_text(pick(row, "脚質表示", "running_style_display", "脚質", "running_style", "style"))
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


def shorten_text(value: Any, max_len: int) -> str:
    text = clean_text(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def extract_raw_section(result: PredictionResult, titles: list[str]) -> str:
    raw = clean_multiline(result.raw_output)
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
    return clean_multiline(match.group("body"))


def strip_section_title(text: str, title: str) -> str:
    cleaned = clean_multiline(text)
    for candidate in (f"【{title}】", title):
        if cleaned.startswith(candidate):
            return cleaned[len(candidate) :].strip()
    return cleaned


def ordered_existing_columns(table: Any, preferred: list[str]) -> list[str]:
    columns = list(getattr(table, "columns", []))
    selected = [column for column in preferred if column in columns]
    selected.extend(column for column in columns if column not in selected)
    return selected


def existing_columns(table: Any, preferred: list[str]) -> list[str]:
    columns = set(getattr(table, "columns", []))
    return [column for column in preferred if column in columns]


def pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name not in row:
            continue
        value = row.get(name)
        if not is_missing_value(value):
            return value
    return ""


def format_odds(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    number = to_float(text)
    if number is None or number <= 0:
        return ""
    return f"{number:g}倍"


def format_number(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return clean_text(value)
    return f"{number:.1f}".rstrip("0").rstrip(".")


def to_float(value: Any) -> float | None:
    try:
        if is_missing_value(value):
            return None
        text = str(value).replace(",", "").replace("倍", "").strip()
        if not text or text.lower() == "nan":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any) -> str:
    if is_missing_value(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_multiline(value: Any) -> str:
    if is_missing_value(value):
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


def plain_text_to_html(value: Any) -> str:
    if is_missing_value(value):
        return ""
    return html.escape(str(value)).replace("\n", "<br>")


def join_nonempty(parts: list[Any], sep: str = " ") -> str:
    return sep.join(clean_text(part) for part in parts if clean_text(part))


def is_missing_value(value: Any) -> bool:
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


def make_download_file_name(result: PredictionResult) -> str:
    mode = "nar" if result.race_mode == "nar" else "jra"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    race = sanitize_ascii(result.race_name) or "race"
    return f"keiba_ai_mobile_{mode}_{timestamp}_{race}.png"


def sanitize_ascii(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", clean_text(value))
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:36]


if __name__ == "__main__":
    main()
