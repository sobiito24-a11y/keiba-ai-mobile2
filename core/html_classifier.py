from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Iterable

from .models import ClassifiedHtml, HtmlMeta, RaceMode


KIND_LABELS = {
    "speed": "タイム指数",
    "shutuba": "出馬表",
    "style": "脚質分析",
    "newspaper": "競馬新聞",
    "oikiri": "調教",
    "odds": "オッズ",
    "unknown": "不明",
}

REQUIRED_KINDS: dict[RaceMode, tuple[str, ...]] = {
    "nar": ("speed", "newspaper", "style"),
    "jra": ("speed", "newspaper", "style"),
}

DISPLAY_ORDER: dict[RaceMode, tuple[str, ...]] = {
    "nar": ("speed", "newspaper", "style", "shutuba"),
    "jra": ("speed", "newspaper", "style", "oikiri"),
}

KIND_PRIORITY = ("speed", "style", "newspaper", "shutuba", "oikiri", "odds")


def required_kinds(mode: RaceMode) -> tuple[str, ...]:
    return REQUIRED_KINDS[mode]


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def decode_uploaded_html(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp932", "euc-jp"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def classify_many(files: Iterable[tuple[str, bytes]], mode: RaceMode) -> dict[str, list[ClassifiedHtml]]:
    grouped: dict[str, list[ClassifiedHtml]] = defaultdict(list)
    for file_name, data in files:
        html_text = decode_uploaded_html(data)
        item = classify_html(file_name, html_text, mode)
        grouped[item.kind].append(item)
    return dict(grouped)


def classify_html(file_name: str, html_text: str, mode: RaceMode) -> ClassifiedHtml:
    meta = extract_meta(file_name, html_text)
    matches = _collect_matches(meta, mode)
    kind = _decide_kind(matches)
    reasons = tuple(matches.get(kind, ())) if kind != "unknown" else ()
    return ClassifiedHtml(
        kind=kind,
        label=kind_label(kind),
        file_name=file_name,
        html_text=html_text,
        meta=meta,
        reasons=reasons,
        all_matches={k: tuple(v) for k, v in matches.items()},
    )


def extract_meta(file_name: str, html_text: str) -> HtmlMeta:
    source = str(html_text or "")
    head = source[:120_000]
    title = _clean_text(_first_tag_text(head, "title"))
    body_id = _attr_from_first_tag(head, "body", "id")
    canonical = _extract_link_href(head, "canonical")
    og_url = _extract_meta_content(head, "og:url")
    table_markers = tuple(_extract_table_markers(head))
    return HtmlMeta(
        file_name=str(file_name or ""),
        title=title,
        canonical=canonical,
        og_url=og_url,
        body_id=body_id,
        table_markers=table_markers,
    )


def _collect_matches(meta: HtmlMeta, mode: RaceMode) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = defaultdict(list)
    fields = [
        ("file name", meta.file_name),
        ("title", meta.title),
        ("canonical", meta.canonical),
        ("og:url", meta.og_url),
        ("body id", meta.body_id),
        ("table id/class", " ".join(meta.table_markers)),
    ]
    for source_name, value in fields:
        for kind, reason in _match_field(source_name, value, mode):
            matches[kind].append(reason)
    return dict(matches)


def _match_field(source_name: str, value: str, mode: RaceMode) -> list[tuple[str, str]]:
    text = str(value or "")
    lower = text.lower()
    found: list[tuple[str, str]] = []

    def add(kind: str, description: str) -> None:
        found.append((kind, f"{source_name}: {description}"))

    if source_name in {"file name", "title"}:
        if "タイム指数" in text:
            add("speed", "タイム指数")
        if "有利な脚質" in text or "脚質 データ分析" in text:
            add("style", "有利な脚質")
        if "出馬表" in text or "出走表" in text:
            add("shutuba", "出馬表")
        if "競馬新聞" in text:
            add("newspaper", "競馬新聞")
        if "調教" in text or "追い切り" in text:
            add("oikiri", "調教・追い切り")
        if "オッズ" in text or "odds" in lower:
            add("odds", "オッズ")

    if source_name in {"canonical", "og:url"}:
        if "/race/speed.html" in lower or "speed.html" in lower:
            add("speed", "speed.html")
        if "mode=courseanalysis" in lower:
            add("style", "mode=courseanalysis")
        if "/race/shutuba.html" in lower or "shutuba.html" in lower:
            add("shutuba", "shutuba.html")
        if "newspaper" in lower:
            add("newspaper", "newspaper")
        if "oikiri" in lower:
            add("oikiri", "oikiri")
        if "/odds/" in lower:
            add("odds", "/odds/")

    if source_name == "body id":
        if text == "Netkeiba_Race_OddsView":
            add("odds", "Netkeiba_Race_OddsView")
        if text in {"Netkeiba_Race_NewsPaper", "Netkeiba_Race_Newspaper"}:
            add("newspaper", text)

    if source_name == "table id/class":
        if _contains_any(text, ("Speed_List", "SpeedIndex_Table")):
            add("speed", "Speed_List/SpeedIndex_Table")
        if _contains_any(text, ("CourseAnalysis", "RaceData_CourseAnalysis")):
            add("style", "CourseAnalysis")
        if _contains_any(text, ("Shutuba_Table", "RaceTable_Shutuba")):
            add("shutuba", "Shutuba_Table")
        if _contains_any(text, ("NewsPaper", "Newspaper", "RaceNewspaper")):
            add("newspaper", "NewsPaper table")
        if _contains_any(text, ("Oikiri", "Training", "Workout")):
            add("oikiri", "Oikiri table")
        if _contains_any(text, ("RaceOdds_HorseList_Table", "Odds_Table", "OddsTable")):
            add("odds", "Odds table")

    return found


def _decide_kind(matches: dict[str, list[str]]) -> str:
    if not matches:
        return "unknown"

    evidence_order = ("file name", "title", "canonical", "og:url", "body id", "table id/class")
    for source_name in evidence_order:
        candidates = [
            kind
            for kind, reasons in matches.items()
            if any(reason.startswith(f"{source_name}:") for reason in reasons)
        ]
        if candidates:
            for kind in KIND_PRIORITY:
                if kind in candidates:
                    return kind
            return candidates[0]
    return "unknown"


def _first_tag_text(source: str, tag_name: str) -> str:
    match = re.search(rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>", source, flags=re.I | re.S)
    return match.group(1) if match else ""


def _attr_from_first_tag(source: str, tag_name: str, attr_name: str) -> str:
    match = re.search(rf"<{tag_name}\b[^>]*>", source, flags=re.I | re.S)
    if not match:
        return ""
    return _extract_attr(match.group(0), attr_name)


def _extract_link_href(source: str, rel_value: str) -> str:
    for tag in re.findall(r"<link\b[^>]*>", source, flags=re.I | re.S):
        rel = _extract_attr(tag, "rel").lower()
        if rel_value.lower() in rel:
            return _extract_attr(tag, "href")
    return ""


def _extract_meta_content(source: str, property_value: str) -> str:
    for tag in re.findall(r"<meta\b[^>]*>", source, flags=re.I | re.S):
        prop = _extract_attr(tag, "property").lower() or _extract_attr(tag, "name").lower()
        if prop == property_value.lower():
            return _extract_attr(tag, "content")
    return ""


def _extract_table_markers(source: str) -> list[str]:
    markers: list[str] = []
    for tag in re.findall(r"<table\b[^>]*>", source, flags=re.I | re.S):
        for attr in ("id", "class"):
            value = _extract_attr(tag, attr)
            if value:
                markers.extend(part for part in re.split(r"\s+", value) if part)
    return markers


def _extract_attr(tag: str, attr_name: str) -> str:
    match = re.search(
        rf"""\b{re.escape(attr_name)}\s*=\s*(['"])(.*?)\1""",
        tag,
        flags=re.I | re.S,
    )
    return html.unescape(match.group(2).strip()) if match else ""


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
