from __future__ import annotations

import html
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
from core.jra_predictor import predict_jra
from core.html_classifier import (
    DISPLAY_ORDER,
    classify_html,
    classify_many,
    kind_label,
    required_kinds,
)
from core.models import ClassifiedHtml, PredictionResult, RaceMode
from core.nar_json_input import (
    NarJsonDataError,
    NarJsonPredictionInput,
    build_nar_prediction_inputs_from_uploads,
)
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
        fallback_selected, fallback_grouped, has_fallback_uploads, fallback_missing = render_upload_input(
            "nar",
            key_prefix="nar_json_direct",
        )
        fallback_ready = has_fallback_uploads and not fallback_missing and bool(fallback_selected)
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


def render_nar_previous_jockey_upload_trace(package: NarJsonPredictionInput) -> None:
    rows = list(getattr(package, "debug_logs", ()) or ())
    if not rows:
        return
    with st.expander("地方前走騎手診断（アップロード解析）", expanded=False):
        st.caption("HTML全文は表示せず、前走騎手の抽出・統合経路だけを表示します。")
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
        fallback_selected, fallback_grouped, has_uploads, missing = render_upload_input(
            "nar",
            key_prefix="nar_fallback",
        )
        fallback_ready = has_uploads and not missing and bool(fallback_selected)
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
    selected, grouped, has_uploads, missing = render_upload_input(mode, key_prefix=mode)

    st.subheader("予想")
    can_predict = has_uploads and not missing and bool(selected)
    if st.button("予想する", disabled=not can_predict, type="primary", use_container_width=True):
        clear_prediction_state(keep_input=True)
        result, png_bytes = run_upload_prediction_with_progress(mode, selected, grouped)
        if result is not None and png_bytes is not None:
            st.session_state.prediction_result = result
            st.session_state.png_bytes = png_bytes


def render_upload_input(
    mode: RaceMode,
    key_prefix: str,
) -> tuple[dict[str, ClassifiedHtml], dict[str, list[ClassifiedHtml]], bool, list[str]]:
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

    st.markdown("#### 認識結果")
    allow_expanders = "fallback" not in key_prefix
    selected = render_recognition(grouped, mode, allow_expanders=allow_expanders)
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

    render_unknown_files(grouped, allow_expander=allow_expanders)
    return selected, grouped, has_uploads, missing


def render_recognition(
    grouped: dict[str, list[ClassifiedHtml]],
    mode: RaceMode,
    allow_expanders: bool = True,
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
        with st.expander("判定できなかったHTML", expanded=False):
            if unknowns:
                for item in unknowns:
                    st.write(item.file_name)
            else:
                st.write("なし")
        return

    st.markdown("判定できなかったHTML")
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
        if mode == "jra" and "oikiri" in grouped and grouped["oikiri"]:
            html_files["oikiri"] = grouped["oikiri"][0].html_text
            file_names["oikiri"] = grouped["oikiri"][0].file_name
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
) -> PredictionResult:
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
]


def render_result_area(result: PredictionResult, png_bytes: bytes) -> None:
    render_colab_style_result(result)
    render_audit_details(result)
    render_nar_previous_jockey_result_trace(result)

    st.divider()
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
        st.session_state.fetch_failures = []
        st.session_state.fetch_race_id = ""
        st.session_state.url_input_key += 1
        st.rerun()


def render_nar_previous_jockey_result_trace(result: PredictionResult) -> None:
    if result.race_mode != "nar":
        return
    rows = list((getattr(result, "debug_info", {}) or {}).get("nar_previous_jockey_trace", []) or [])
    if not rows:
        return
    with st.expander("地方前走騎手診断（PredictionResult・表示直前）", expanded=False):
        st.caption("PredictionResult作成時の内部列と、app.pyカード表示が参照する騎手詳細です。")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_colab_style_result(result: PredictionResult) -> None:
    render_raw_text_section(
        "会場別試験評価",
        extract_raw_section(result, ["会場別試験評価", "JRA会場別試験評価"]),
    )
    render_raw_text_section(
        "展開予想",
        extract_raw_section(result, ["展開予想"]),
    )
    render_race_difficulty(result)
    render_overall_table(result)
    render_horse_evaluation(result)
    render_attention_horses(result)
    render_raw_text_section(
        "AIレース考察",
        strip_section_title(result.ai_race_review, "AIレース考察"),
    )
    render_raw_text_section(
        "今回の馬券構成",
        strip_section_title(result.betting_structure, "今回の馬券構成"),
    )


def render_raw_text_section(title: str, text: str) -> None:
    st.subheader(title)
    body = clean_multiline(text)
    if not body:
        st.markdown('<div class="ka-section ka-muted">未取得です。</div>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="ka-section">{plain_text_to_html(body)}</div>', unsafe_allow_html=True)


def render_overall_table(result: PredictionResult) -> None:
    st.subheader("レース全体表")
    table = result.overall_table
    if table is None or getattr(table, "empty", False):
        st.info("レース全体表は未取得です。")
        return

    mode = st.radio(
        "レース全体表の表示",
        ["簡易表示", "詳細表示"],
        horizontal=True,
        key="overall_table_mode",
        label_visibility="collapsed",
    )
    columns = OVERALL_SIMPLE_COLUMNS if mode == "簡易表示" else ordered_existing_columns(table, OVERALL_DETAIL_COLUMNS)
    if mode == "簡易表示":
        columns = existing_columns(table, columns)
    if not columns:
        columns = list(table.columns)
    st.dataframe(table.loc[:, columns], use_container_width=True, hide_index=True)


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
    if "表示印" in row:
        return clean_text(row.get("表示印"))
    if "display_mark" in row:
        return clean_text(row.get("display_mark"))
    return clean_text(pick(row, "印", "最終印"))


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
    if "倍" in text:
        return text
    number = to_float(text)
    return f"{number:g}倍" if number is not None else text


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
