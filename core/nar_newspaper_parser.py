from __future__ import annotations

import html as html_lib
import re
from typing import Any


class NarNewspaperParseError(ValueError):
    """Raised when NAR newspaper HTML cannot be converted to entry data."""


def is_nar_newspaper_html(text: str) -> bool:
    source = html_lib.unescape(str(text or ""))
    lower = source.lower()
    head = lower[:150_000]
    return (
        "<html" in lower
        and ("newspaper" in head or "競馬新聞" in source[:150_000])
        and ("nar.netkeiba.com" in head or "地方競馬" in source[:150_000])
    )


def extract_race_id_from_nar_newspaper_html(html: str) -> str:
    source = html_lib.unescape(str(html or ""))
    head = source[:150_000]
    for tag_pattern in (
        r"<link\b[^>]*rel=['\"]?canonical['\"]?[^>]*>",
        r"<meta\b[^>]*(?:property|name)=['\"]?og:url['\"]?[^>]*>",
    ):
        for tag in re.findall(tag_pattern, head, flags=re.I):
            value = _attr(tag, "href") or _attr(tag, "content")
            race_id = _first_race_id(value)
            if race_id:
                return race_id
    return _first_race_id(head)


def parse_nar_newspaper_html(html: str) -> dict[str, Any]:
    if not is_nar_newspaper_html(html):
        raise NarNewspaperParseError("地方競馬新聞HTMLとして判定できませんでした。")

    records = _extract_horse_records(html)
    if not records:
        raise NarNewspaperParseError("競馬新聞HTMLから馬データを取得できませんでした。")

    race_id = extract_race_id_from_nar_newspaper_html(html)
    return {
        "race_id": race_id,
        "data_type": "newspaper",
        "race": _extract_race_info(html),
        "horses": records,
    }


def build_entry_from_nar_newspaper(newspaper_data: dict[str, Any]) -> dict[str, Any]:
    horses = []
    for item in newspaper_data.get("horses", []):
        horse = {
            "frame_number": item.get("frame_number", ""),
            "horse_number": item.get("horse_number", ""),
            "horse_id": item.get("horse_id", ""),
            "horse_name": item.get("horse_name", ""),
            "sex_age": item.get("sex_age", ""),
            "weight": item.get("weight", ""),
            "jockey": item.get("jockey", ""),
            "trainer": item.get("trainer", ""),
            "affiliation": item.get("affiliation", ""),
            "horse_weight": item.get("horse_weight", ""),
            "odds": item.get("odds", ""),
            "popularity": item.get("popularity", ""),
            "running_style": item.get("running_style", ""),
            "style": item.get("running_style", ""),
            "stable_comment": item.get("stable_comment", ""),
            "pace_prediction": item.get("pace_prediction", ""),
            "ai_mark": item.get("ai_mark", ""),
            "early_3f": item.get("early_3f", ""),
            "late_3f": item.get("late_3f", ""),
        }
        horses.append(horse)

    return {
        "race_id": str(newspaper_data.get("race_id", "")).strip(),
        "data_type": "entry",
        "race": newspaper_data.get("race") or {},
        "horses": horses,
        "source": "nar_newspaper_html",
        "suggested_file_name": str(newspaper_data.get("_uploaded_file_name") or "nar_newspaper_entry.html"),
    }


def _extract_horse_records(html: str) -> list[dict[str, Any]]:
    source = html_lib.unescape(str(html or ""))
    records: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()
    for row_html in re.findall(r"<tr\b[^>]*>([\s\S]*?)</tr>", source, flags=re.I):
        if "/horse/" not in row_html and "Horse_Info" not in row_html and "HorseName" not in row_html:
            continue
        record = _record_from_row(row_html)
        number = str(record.get("horse_number", "")).strip()
        name = str(record.get("horse_name", "")).strip()
        if not number or not name or number in seen_numbers:
            continue
        seen_numbers.add(number)
        records.append(record)
    return sorted(records, key=lambda item: _number_sort_key(str(item.get("horse_number", ""))))


def _record_from_row(row_html: str) -> dict[str, Any]:
    cells = _extract_cells(row_html)
    row_text = _clean_text(row_html)
    horse_link = re.search(r"<a\b[^>]*href=['\"][^'\"]*/horse/([^/'\"?]+)[^'\"]*['\"][^>]*>([\s\S]*?)</a>", row_html, flags=re.I)
    horse_id = horse_link.group(1).strip() if horse_link else ""
    horse_name = _clean_text(horse_link.group(2)) if horse_link else _first_nonempty_cell(cells, ("Horse_Info", "HorseName", "Horse_Name"))

    horse_number = _cell_number(cells, ("Umaban", "Horse_Num", "HorseNum", "HorseList_Num", "UmaBan"))
    if not horse_number:
        horse_number = _infer_horse_number(cells, horse_name)

    frame_number = _cell_number(cells, ("Waku", "Frame", "枠"))
    if not frame_number:
        frame_number = _infer_frame_number(cells, horse_number)

    weight, sex_age = _extract_weight_and_sex_age(cells, row_text)
    body_weight = _extract_body_weight(row_text)
    body_value, body_diff = _split_body_weight(body_weight)
    odds = _extract_odds(cells, row_html)
    popularity = _extract_popularity(cells, row_html)

    raw_trainer = _link_text(row_html, "/trainer/")
    affiliation, trainer = _split_trainer_affiliation(raw_trainer)
    if not affiliation:
        affiliation = _extract_affiliation(row_text, trainer)

    return {
        "frame_number": frame_number,
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "weight": weight,
        "jockey": _link_text(row_html, "/jockey/") or _first_nonempty_cell(cells, ("Jockey", "騎手")),
        "trainer": trainer,
        "affiliation": affiliation,
        "horse_weight": body_weight,
        "horse_weight_value": body_value,
        "horse_weight_diff": body_diff,
        "odds": odds,
        "popularity": popularity,
        "running_style": _extract_running_style(cells, row_text),
        "stable_comment": _extract_comment(cells, ("Comment", "コメント", "厩舎")),
        "pace_prediction": _extract_comment(cells, ("Pace", "展開")),
        "ai_mark": _extract_mark(cells, row_text),
        "early_3f": _extract_3f(row_text, "前半"),
        "late_3f": _extract_3f(row_text, "後半"),
    }


def _extract_cells(row_html: str) -> list[tuple[str, str, str]]:
    cells = []
    for match in re.finditer(r"<td\b(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</td>", row_html, flags=re.I):
        attrs = match.group("attrs") or ""
        body = match.group("body") or ""
        cells.append((attrs, body, _clean_text(body)))
    return cells


def _cell_number(cells: list[tuple[str, str, str]], class_keywords: tuple[str, ...]) -> str:
    for attrs, _, text in cells:
        if any(keyword in attrs for keyword in class_keywords):
            match = re.search(r"\d{1,2}", text)
            if match:
                return match.group(0)
    return ""


def _infer_horse_number(cells: list[tuple[str, str, str]], horse_name: str) -> str:
    for _, _, text in cells[:5]:
        if text and text != horse_name:
            match = re.fullmatch(r"\d{1,2}", text)
            if match:
                return match.group(0)
    return ""


def _infer_frame_number(cells: list[tuple[str, str, str]], horse_number: str) -> str:
    number_seen = False
    for _, _, text in cells[:4]:
        if text == horse_number:
            number_seen = True
            continue
        if number_seen:
            break
        if re.fullmatch(r"\d", text):
            return text
    return ""


def _extract_weight_and_sex_age(cells: list[tuple[str, str, str]], row_text: str) -> tuple[str, str]:
    sex_age = ""
    weight = ""
    for _, _, text in cells:
        if not sex_age:
            match = re.search(r"([牡牝セせ騸]\s*\d{1,2})", text)
            if match:
                sex_age = match.group(1).replace(" ", "").replace("せ", "セ")
        if not weight:
            match = re.fullmatch(r"(\d{2}(?:\.\d)?)", text)
            if match and 45 <= float(match.group(1)) <= 65:
                weight = match.group(1)
    if not sex_age:
        match = re.search(r"([牡牝セせ騸]\s*\d{1,2})", row_text)
        if match:
            sex_age = match.group(1).replace(" ", "").replace("せ", "セ")
    if not weight:
        for match in re.finditer(r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)", row_text):
            value = float(match.group(1))
            if 45 <= value <= 65:
                weight = match.group(1)
                break
    return weight, sex_age


def _extract_body_weight(row_text: str) -> str:
    match = re.search(r"(\d{3})\s*\(([+-]?\d+)\)", row_text)
    return f"{match.group(1)}({match.group(2)})" if match else ""


def _split_body_weight(value: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d{3})\(([+-]?\d+)\)", str(value or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_odds(cells: list[tuple[str, str, str]], row_html: str) -> str:
    for attrs, _, text in cells:
        if "odds" in attrs.lower() or "Odds" in attrs:
            value = _first_float(text)
            if value:
                return value
    match = re.search(r"id=['\"]odds-[^'\"]*['\"][^>]*>([\s\S]*?)<", row_html, flags=re.I)
    if match:
        return _first_float(_clean_text(match.group(1)))
    return ""


def _extract_popularity(cells: list[tuple[str, str, str]], row_html: str) -> str:
    for attrs, _, text in cells:
        lower = attrs.lower()
        if "ninki" in lower or "popular" in lower or "人気" in attrs:
            match = re.search(r"\d{1,2}", text)
            if match:
                return match.group(0)
    match = re.search(r"id=['\"]ninki-[^'\"]*['\"][^>]*>([\s\S]*?)<", row_html, flags=re.I)
    if match:
        text = _clean_text(match.group(1))
        number = re.search(r"\d{1,2}", text)
        return number.group(0) if number else ""
    return ""


def _extract_running_style(cells: list[tuple[str, str, str]], row_text: str) -> str:
    for attrs, _, text in cells:
        if "DataTitle_Cell" in attrs or "脚質" in attrs or "style" in attrs.lower():
            style = _normalize_style(text)
            if style:
                return style
    for _, _, text in cells:
        if len(text) <= 3:
            style = _normalize_style(text)
            if style:
                return style
    return _normalize_style(row_text)


def _extract_comment(cells: list[tuple[str, str, str]], class_keywords: tuple[str, ...]) -> str:
    candidates = []
    for attrs, _, text in cells:
        if any(keyword.lower() in attrs.lower() for keyword in class_keywords) and len(text) >= 3:
            candidates.append(text)
    return max(candidates, key=len)[:160] if candidates else ""


def _extract_mark(cells: list[tuple[str, str, str]], row_text: str) -> str:
    marks = ("◎", "○", "◯", "▲", "△", "☆", "✓")
    for _, _, text in cells[:6]:
        for mark in marks:
            if mark in text:
                return "○" if mark == "◯" else mark
    for mark in marks:
        if mark in row_text[:80]:
            return "○" if mark == "◯" else mark
    return ""


def _extract_3f(row_text: str, label: str) -> str:
    pattern = rf"{label}\s*3F?\s*[:：]?\s*(\d{{1,2}}\.\d)"
    match = re.search(pattern, row_text, flags=re.I)
    return match.group(1) if match else ""


def _link_text(row_html: str, href_part: str) -> str:
    match = re.search(
        rf"<a\b[^>]*href=['\"][^'\"]*{re.escape(href_part)}[^'\"]*['\"][^>]*>([\s\S]*?)</a>",
        row_html,
        flags=re.I,
    )
    return _clean_text(match.group(1)) if match else ""


def _extract_affiliation(row_text: str, trainer: str) -> str:
    if not trainer:
        return ""
    match = re.search(r"([^\s・/／]+)[・/／]\s*" + re.escape(trainer), row_text)
    return match.group(1) if match else ""


def _split_trainer_affiliation(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    for separator in ("・", "/", "／"):
        if separator in text:
            left, right = text.split(separator, 1)
            return left.strip(), right.strip()
    return "", text


def _first_nonempty_cell(cells: list[tuple[str, str, str]], class_keywords: tuple[str, ...]) -> str:
    for attrs, _, text in cells:
        if any(keyword in attrs for keyword in class_keywords) and text:
            return text
    return ""


def _first_float(text: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", str(text or ""))
    return match.group(0) if match else ""


def _extract_race_info(html: str) -> dict[str, str]:
    return {
        "race_name": _class_text(html, "RaceName") or _title_text(html),
        "race_number": _class_text(html, "RaceNum"),
        "race_data_1": _class_text(html, "RaceData01"),
        "race_data_2": _class_text(html, "RaceData02"),
    }


def _class_text(html: str, class_name: str) -> str:
    pattern = (
        r"<(?P<tag>[a-z0-9]+)\b[^>]*class=['\"][^'\"]*\b"
        + re.escape(class_name)
        + r"\b[^'\"]*['\"][^>]*>(?P<body>[\s\S]*?)</(?P=tag)>"
    )
    match = re.search(pattern, html, flags=re.I)
    return _clean_text(match.group("body")) if match else ""


def _title_text(html: str) -> str:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, flags=re.I)
    return _clean_text(match.group(1)) if match else ""


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_style(value: Any) -> str:
    text = str(value or "").strip()
    if "逃" in text:
        return "逃"
    if "先" in text:
        return "先"
    if "差" in text:
        return "差"
    if "追" in text:
        return "追"
    return ""


def _attr(tag: str, attr_name: str) -> str:
    match = re.search(rf"\b{re.escape(attr_name)}\s*=\s*(['\"])(.*?)\1", tag, flags=re.I)
    return html_lib.unescape(match.group(2)) if match else ""


def _first_race_id(text: str) -> str:
    source = str(text or "")
    for pattern in (
        r"race_id(?:=|%3D)(\d{12})",
        r"race_id['\"]?\s*[:=]\s*['\"](\d{12})",
    ):
        match = re.search(pattern, source, flags=re.I)
        if match:
            return match.group(1)
    return ""


def _number_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value), value
    except ValueError:
        return 999, value
