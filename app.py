from __future__ import annotations

import html
import re
import traceback
from datetime import datetime

import streamlit as st

from core.html_classifier import (
    DISPLAY_ORDER,
    classify_many,
    kind_label,
    required_kinds,
)
from core.jra_predictor import predict_jra
from core.models import ClassifiedHtml, PredictionResult, RaceMode
from core.nar_predictor import predict_nar
from core.version import APP_VERSION
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
  div[data-testid="stRadio"] label {
    align-items: flex-start;
  }
</style>
"""


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

    uploaded_files = st.file_uploader(
        "HTML追加",
        type=["html", "htm"],
        accept_multiple_files=True,
        help="必要なHTMLをまとめて選択してください。内容から自動判定します。",
        key=f"html_upload_{st.session_state.uploader_key}",
    )

    grouped: dict[str, list[ClassifiedHtml]] = {}
    if uploaded_files:
        grouped = classify_many([(file.name, file.getvalue()) for file in uploaded_files], mode)

    st.subheader("認識結果")
    selected = render_recognition(grouped, mode)
    missing = [kind for kind in required_kinds(mode) if kind not in selected]

    if not uploaded_files:
        st.info("HTMLを追加してください。")
    elif missing:
        for kind in missing:
            st.markdown(
                f'<div class="ka-card"><span class="ka-ng">× {kind_label(kind)}HTMLが不足しています</span></div>',
                unsafe_allow_html=True,
            )
    elif selected:
        st.success("必要なHTMLが揃いました。")

    render_unknown_files(grouped)

    st.subheader("予想")
    can_predict = not missing and bool(selected)
    if st.button("予想する", disabled=not can_predict, type="primary", use_container_width=True):
        result, png_bytes = run_prediction_with_progress(mode, selected, grouped)
        if result is not None and png_bytes is not None:
            st.session_state.prediction_result = result
            st.session_state.png_bytes = png_bytes

    if st.session_state.prediction_result is not None and st.session_state.png_bytes is not None:
        render_result_area(st.session_state.prediction_result, st.session_state.png_bytes)


def _init_state() -> None:
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("prediction_result", None)
    st.session_state.setdefault("png_bytes", None)


def render_recognition(grouped: dict[str, list[ClassifiedHtml]], mode: RaceMode) -> dict[str, ClassifiedHtml]:
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
            f'<div class="ka-card"><span class="ka-ok">✓ {label}</span><br>'
            f'同じ種類のHTMLが{len(candidates)}件あります</div>',
            unsafe_allow_html=True,
        )
        options = [item.file_name for item in candidates]
        chosen_name = st.radio(
            f"{label}HTMLを選択",
            options=options,
            key=f"{mode}_{kind}_duplicate",
            label_visibility="visible",
        )
        item = next(candidate for candidate in candidates if candidate.file_name == chosen_name)
        selected[kind] = item

    extra_kinds = [
        kind
        for kind in grouped
        if kind not in set(DISPLAY_ORDER[mode]) | {"unknown"}
    ]
    if extra_kinds:
        with st.expander("任意HTML / 今回は補助として使用", expanded=False):
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


def render_unknown_files(grouped: dict[str, list[ClassifiedHtml]]) -> None:
    with st.expander("判定できなかったHTML", expanded=False):
        unknowns = grouped.get("unknown", [])
        if unknowns:
            for item in unknowns:
                st.write(item.file_name)
        else:
            st.write("なし")


def run_prediction_with_progress(
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
        step(10, "1. HTML解析中")
        step(30, "2. AI予想中")
        result = run_prediction(mode, selected, grouped)
        step(60, "3. 結果整理中")
        validate_result(result)
        step(80, "4. PNG生成中")
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
    selected: dict[str, ClassifiedHtml],
    grouped: dict[str, list[ClassifiedHtml]],
) -> PredictionResult:
    html_files = {kind: item.html_text for kind, item in selected.items()}
    file_names = {kind: item.file_name for kind, item in selected.items()}
    if mode == "jra" and "oikiri" in grouped and grouped["oikiri"]:
        html_files["oikiri"] = grouped["oikiri"][0].html_text
        file_names["oikiri"] = grouped["oikiri"][0].file_name
    if mode == "nar":
        return predict_nar(html_files, file_names)
    return predict_jra(html_files, file_names)


def validate_result(result: PredictionResult) -> None:
    if result.status != "ok":
        raise RuntimeError(result.message or "PredictionResultが正常状態ではありません。")
    if result.overall_table is None:
        raise RuntimeError("レース全体表が取得できませんでした。")
    if result.horse_evaluation is None:
        raise RuntimeError("馬評価が取得できませんでした。")


def render_result_area(result: PredictionResult, png_bytes: bytes) -> None:
    st.subheader("スマホ用PNG")
    st.image(png_bytes, use_container_width=True)
    st.download_button(
        "PNGを保存",
        data=png_bytes,
        file_name=make_download_file_name(result),
        mime="image/png",
        use_container_width=True,
    )

    with st.expander("PredictionResult簡易確認", expanded=False):
        st.write(
            {
                "version": result.version,
                "created_at": result.created_at,
                "mode": result.race_mode,
                "race_name": result.race_name,
                "status": result.status,
            }
        )

    if st.button("次のレースを予想", use_container_width=True):
        st.session_state.prediction_result = None
        st.session_state.png_bytes = None
        st.session_state.uploader_key += 1
        st.rerun()


def make_download_file_name(result: PredictionResult) -> str:
    mode = "nar" if result.race_mode == "nar" else "jra"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    race = sanitize_ascii(result.race_name) or "race"
    return f"keiba_ai_mobile_{mode}_{timestamp}_{race}.png"


def sanitize_ascii(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "")
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:36]


if __name__ == "__main__":
    main()
