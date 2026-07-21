from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from typing import Any, Iterable

from .nar_courseanalysis_parser import (
    NarCourseAnalysisParseError,
    is_courseanalysis_html,
    parse_courseanalysis_html,
)


REQUIRED_NAR_JSON_TYPES = {"entry", "speed", "courseanalysis"}


class NarJsonDataError(ValueError):
    """Raised when uploaded shortcut data cannot be used for NAR prediction."""


@dataclass(frozen=True)
class NarJsonPredictionInput:
    race_id: str
    html_files: dict[str, str]
    file_names: dict[str, str]
    entry_count: int
    speed_count: int
    running_styles: tuple[str, ...]


def build_nar_prediction_inputs_from_uploads(
    uploaded_files: Iterable[tuple[str, bytes]],
) -> NarJsonPredictionInput:
    classified = classify_nar_uploaded_files(uploaded_files)
    validate_nar_uploaded_data(classified)

    entry_data = classified["entry"]
    speed_data = classified["speed"]
    courseanalysis_data = classified["courseanalysis"]
    race_id = str(entry_data.get("race_id", "")).strip()
    merged_horses = merge_entry_and_speed(entry_data, speed_data)
    running_styles = tuple(
        str(item.get("style", "")).strip()
        for item in courseanalysis_data.get("running_styles", [])
        if str(item.get("style", "")).strip()
    )

    html_files = {
        "shutuba": build_shutuba_html(entry_data, merged_horses),
        "speed": build_speed_html(speed_data, entry_data, merged_horses),
        "style": build_courseanalysis_html(courseanalysis_data, merged_horses),
    }
    file_names = {
        "shutuba": _suggested_name(entry_data, race_id, "entry"),
        "speed": _suggested_name(speed_data, race_id, "speed"),
        "style": _suggested_name(courseanalysis_data, race_id, "courseanalysis"),
    }
    return NarJsonPredictionInput(
        race_id=race_id,
        html_files=html_files,
        file_names=file_names,
        entry_count=len(entry_data.get("horses", [])),
        speed_count=len(speed_data.get("horses", [])),
        running_styles=running_styles,
    )


def classify_nar_uploaded_files(uploaded_files: Iterable[tuple[str, bytes]]) -> dict[str, dict[str, Any]]:
    classified: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[str]] = {}
    invalid_files: list[str] = []

    for file_name, raw in uploaded_files:
        text = decode_uploaded_text(raw)
        data = try_load_json(text)
        if data is not None:
            data_type = str(data.get("data_type", "")).strip()
            if data_type not in REQUIRED_NAR_JSON_TYPES:
                invalid_files.append(f"{file_name}: data_type が不正です（{data_type or '未取得'}）")
                continue
            _add_classified_data(classified, duplicates, data_type, data, file_name)
            continue

        if is_courseanalysis_html(text):
            try:
                courseanalysis_data = parse_courseanalysis_html(text)
            except NarCourseAnalysisParseError as exc:
                invalid_files.append(f"{file_name}: コース分析HTMLの解析に失敗しました（{exc}）")
                continue
            _add_classified_data(classified, duplicates, "courseanalysis", courseanalysis_data, file_name)
            continue

        invalid_files.append(f"{file_name}: entry/speed JSON または courseanalysis HTML として判定できません")

    if invalid_files:
        raise NarJsonDataError("読み込めないファイルがあります。\n" + "\n".join(invalid_files))
    if duplicates:
        details = [f"{data_type}: {', '.join(names)}" for data_type, names in duplicates.items()]
        raise NarJsonDataError("同じ種類のファイルが複数あります。採用するファイルを1つにしてください。\n" + "\n".join(details))
    return classified


def classify_uploaded_json_files(uploaded_files: Iterable[tuple[str, bytes]]) -> dict[str, dict[str, Any]]:
    return classify_nar_uploaded_files(uploaded_files)


def _add_classified_data(
    classified: dict[str, dict[str, Any]],
    duplicates: dict[str, list[str]],
    data_type: str,
    data: dict[str, Any],
    file_name: str,
) -> None:
    if data_type in classified:
        duplicates.setdefault(data_type, []).append(file_name)
        return
    data["_uploaded_file_name"] = file_name
    classified[data_type] = data


def decode_uploaded_file(uploaded_file: Any) -> str:
    if isinstance(uploaded_file, bytes):
        return decode_uploaded_text(uploaded_file)
    if hasattr(uploaded_file, "getvalue"):
        return decode_uploaded_text(uploaded_file.getvalue())
    return decode_uploaded_text(bytes(uploaded_file))


def try_load_json(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    if not source:
        return None
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", source, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def load_uploaded_json(raw: bytes) -> dict[str, Any]:
    data = try_load_json(decode_uploaded_text(raw))
    if data is None:
        raise NarJsonDataError("JSON本文を取得できませんでした。")
    return data


def decode_uploaded_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def validate_nar_uploaded_data(classified: dict[str, dict[str, Any]]) -> None:
    missing = REQUIRED_NAR_JSON_TYPES - set(classified)
    if missing:
        labels = ", ".join(_type_label(value) for value in sorted(missing))
        raise NarJsonDataError(f"必要なデータが不足しています: {labels}")

    race_ids = {str(classified[key].get("race_id", "")).strip() for key in REQUIRED_NAR_JSON_TYPES}
    if len(race_ids) != 1 or "" in race_ids:
        details = ", ".join(f"{_type_label(key)}={classified[key].get('race_id', '')}" for key in sorted(REQUIRED_NAR_JSON_TYPES))
        raise NarJsonDataError("3ファイルのrace_idが一致していません。\n" + details)

    entry_horses = classified["entry"].get("horses", [])
    speed_horses = classified["speed"].get("horses", [])
    running_styles = classified["courseanalysis"].get("running_styles", [])
    if not isinstance(entry_horses, list) or not entry_horses:
        raise NarJsonDataError("出走表JSONのhorsesが空です。")
    if not isinstance(speed_horses, list) or not speed_horses:
        raise NarJsonDataError("タイム指数JSONのhorsesが空です。")
    if len(entry_horses) != len(speed_horses):
        raise NarJsonDataError(
            f"出走表とタイム指数の頭数が一致しません（出走表{len(entry_horses)}頭 / タイム指数{len(speed_horses)}頭）。"
        )

    entry_numbers = _number_list(entry_horses)
    speed_numbers = _number_list(speed_horses)
    if any(not number for number in entry_numbers + speed_numbers):
        raise NarJsonDataError("horse_numberが空の馬があります。")
    _raise_if_duplicate(entry_numbers, "出走表")
    _raise_if_duplicate(speed_numbers, "タイム指数")
    if set(entry_numbers) != set(speed_numbers):
        missing_speed = sorted(set(entry_numbers) - set(speed_numbers), key=_number_sort_key)
        missing_entry = sorted(set(speed_numbers) - set(entry_numbers), key=_number_sort_key)
        detail = []
        if missing_speed:
            detail.append("タイム指数にない馬番: " + ", ".join(missing_speed))
        if missing_entry:
            detail.append("出走表にない馬番: " + ", ".join(missing_entry))
        raise NarJsonDataError("出走表とタイム指数の馬番が一致しません。\n" + "\n".join(detail))

    _validate_horse_identity(entry_horses, speed_horses)

    if not isinstance(running_styles, list) or not running_styles:
        raise NarJsonDataError("コース脚質データのrunning_stylesが空です。")
    has_invalid_style = False
    for item in running_styles:
        if not isinstance(item, dict) or not str(item.get("style", "")).strip() or item.get("win_rate") is None:
            has_invalid_style = True
            break
    if has_invalid_style:
        raise NarJsonDataError("コース脚質データにstyleまたはwin_rateが不足しています。")


def validate_nar_json_bundle(classified: dict[str, dict[str, Any]]) -> None:
    validate_nar_uploaded_data(classified)


def merge_entry_and_speed(entry_data: dict[str, Any], speed_data: dict[str, Any]) -> list[dict[str, Any]]:
    speed_by_number = {
        _horse_number(horse): horse
        for horse in speed_data.get("horses", [])
        if _horse_number(horse)
    }
    merged_horses: list[dict[str, Any]] = []
    for entry_horse in entry_data.get("horses", []):
        horse_number = _horse_number(entry_horse)
        speed_horse = speed_by_number.get(horse_number)
        if not speed_horse:
            raise NarJsonDataError(f"馬番{horse_number}のタイム指数が見つかりません。")
        merged = dict(entry_horse)
        for key in ("max", "avg5", "distance", "course", "race3", "race2", "race1"):
            merged[key] = parse_index(speed_horse.get(key))
        for key in ("odds", "popularity", "style", "running_style"):
            if not str(merged.get(key, "")).strip() and str(speed_horse.get(key, "")).strip():
                merged[key] = speed_horse.get(key)
        weight_value, weight_diff = parse_horse_weight(merged.get("horse_weight"))
        merged["horse_weight_value"] = weight_value
        merged["horse_weight_diff"] = weight_diff
        merged["_speed_horse"] = speed_horse
        merged_horses.append(merged)
    return merged_horses


def parse_index(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace("*", "")
    if text in {"", "-", "未", "未取得", "None", "nan"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_horse_weight(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    match = re.search(r"(\d+)\s*\(([+-]?\d+)\)", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def build_speed_html(
    speed_data: dict[str, Any],
    entry_data: dict[str, Any],
    merged_horses: list[dict[str, Any]],
) -> str:
    race_id = str(speed_data.get("race_id") or entry_data.get("race_id") or "").strip()
    race = _race_dict(speed_data, entry_data)
    race_name = _race_value(race, "race_name") or "地方競馬"
    race_data_1 = _race_value(race, "race_data_1", "race_data", "race_info") or ""
    race_data_2 = _race_value(race, "race_data_2") or ""
    rows = []
    for horse in merged_horses:
        rows.append(
            '<tr class="List HorseList">'
            f"<td>{_e(horse.get('frame_number'))}</td>"
            f'<td><span class="Speed_List01 UmaBan">{_e(horse.get("horse_number"))}</span></td>'
            f'<td><span class="Horse_Name"><a href="https://nar.netkeiba.com/horse/{_e(horse.get("horse_id"))}">{_e(horse.get("horse_name"))}</a></span></td>'
            "<td></td>"
            f"<td>{_e(horse.get('sex_age'))}</td>"
            f'<td><span class="Speed_List02">{_e(horse.get("weight"))}</span></td>'
            f'<td><span class="Jockey">{_e(horse.get("jockey"))}</span></td>'
            f'<td class="Speed_List07 Odds">{_e(horse.get("odds"))}</td>'
            f'<td class="Speed_List08 Ninki">{_e(horse.get("popularity"))}</td>'
            f'<td class="Speed_List05">{_index_text(horse.get("distance"))}</td>'
            f'<td class="Speed_List06">{_index_text(horse.get("course"))}</td>'
            f'<td class="Speed_List09">{_index_text(horse.get("race3"))}</td>'
            f'<td class="Speed_List10">{_index_text(horse.get("race2"))}</td>'
            f'<td class="Speed_List11">{_index_text(horse.get("race1"))}</td>'
            "</tr>"
        )
    return _html_document(
        race_id,
        race_name,
        race_data_1,
        race_data_2,
        "speed",
        f'<div id="Speed_List"><table class="SpeedIndex_Table"><tbody>{"".join(rows)}</tbody></table></div>',
    )


def build_shutuba_html(entry_data: dict[str, Any], merged_horses: list[dict[str, Any]]) -> str:
    race_id = str(entry_data.get("race_id", "")).strip()
    race = _race_dict(entry_data)
    race_name = _race_value(race, "race_name") or "地方競馬"
    race_data_1 = _race_value(race, "race_data_1", "race_data", "race_info") or ""
    race_data_2 = _race_value(race, "race_data_2") or ""
    rows = []
    for horse in merged_horses:
        rows.append(
            '<tr class="HorseList">'
            f'<td class="Waku">{_e(horse.get("frame_number"))}</td>'
            f'<td class="Umaban Horse_Num HorseNum Num HorseList_Num">{_e(horse.get("horse_number"))}</td>'
            f'<td class="Horse_Info"><a href="https://nar.netkeiba.com/horse/{_e(horse.get("horse_id"))}">{_e(horse.get("horse_name"))}</a></td>'
            f"<td>{_e(horse.get('sex_age'))}</td>"
            f"<td>{_e(horse.get('weight'))}</td>"
            f"<td>{_e(horse.get('jockey'))}</td>"
            f'<td class="Weight HorseWeight Horse_Weight">{_e(horse.get("horse_weight"))}</td>'
            "</tr>"
        )
    return _html_document(
        race_id,
        race_name,
        race_data_1,
        race_data_2,
        "shutuba",
        f'<table class="Shutuba_Table"><tbody>{"".join(rows)}</tbody></table>',
    )


def build_courseanalysis_html(
    courseanalysis_data: dict[str, Any],
    merged_horses: list[dict[str, Any]],
) -> str:
    race_id = str(courseanalysis_data.get("race_id", "")).strip()
    race = _race_dict(courseanalysis_data)
    race_name = _race_value(race, "race_name") or "地方競馬"
    race_data_1 = _race_value(race, "race_data_1", "race_data", "race_info") or ""
    race_data_2 = _race_value(race, "race_data_2") or ""

    horse_rows = []
    for horse in merged_horses:
        style = str(horse.get("running_style") or horse.get("style") or "").strip()
        if not style:
            continue
        horse_rows.append(
            '<tr class="HorseList">'
            f"<td>{_e(horse.get('horse_number'))}</td>"
            f'<td class="Horse_Info"><a>{_e(horse.get("horse_name"))}</a></td>'
            f'<td class="DataTitle_Cell">{_e(style)}</td>'
            "<td></td><td></td><td></td><td></td><td></td>"
            "<td></td><td></td><td></td><td></td><td></td>"
            "</tr>"
        )

    trend_rows = []
    for item in courseanalysis_data.get("running_styles", []):
        trend_rows.append(
            "<tr>"
            f"<td>{_e(item.get('style'))}</td>"
            f"<td>{_e(item.get('win_rate'))}</td>"
            f"<td>{_e(item.get('quinella_rate'))}</td>"
            f"<td>{_e(item.get('place_rate'))}</td>"
            f"<td>{_e(item.get('outside_rate'))}</td>"
            "</tr>"
        )

    body = (
        f'<canvas id="score1"></canvas>'
        f'<table id="table_sort_back" class="Data01_Table"><tbody>{"".join(horse_rows)}</tbody></table>'
        f'<table class="CourseAnalysis"><tbody>{"".join(trend_rows)}</tbody></table>'
    )
    return _html_document(race_id, race_name, race_data_1, race_data_2, "courseanalysis", body)


def _html_document(
    race_id: str,
    race_name: str,
    race_data_1: str,
    race_data_2: str,
    page_kind: str,
    body: str,
) -> str:
    canonical = {
        "speed": f"https://nar.netkeiba.com/race/speed.html?race_id={race_id}",
        "shutuba": f"https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}",
        "courseanalysis": f"https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=1",
    }.get(page_kind, f"https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}")
    return (
        "<!doctype html><html><head>"
        f"<title>{_e(race_name)}</title>"
        f'<link rel="canonical" href="{_e(canonical)}">'
        f'<meta property="og:url" content="{_e(canonical)}">'
        "</head>"
        '<body id="Netkeiba_Race_Nar_Shutuba">'
        f'<a href="{_e(canonical)}">race_id={_e(race_id)}</a>'
        f'<h1 class="RaceName">{_e(race_name)}</h1>'
        f'<div class="RaceData01">{_e(race_data_1)}</div>'
        f'<div class="RaceData02">{_e(race_data_2)}</div>'
        f"{body}</body></html>"
    )


def _suggested_name(data: dict[str, Any], race_id: str, fallback_type: str) -> str:
    return str(data.get("suggested_file_name") or data.get("_uploaded_file_name") or f"{race_id}_{fallback_type}.html")


def _race_dict(*sources: dict[str, Any]) -> dict[str, Any]:
    for source in sources:
        race = source.get("race")
        if isinstance(race, dict):
            return race
    return {}


def _race_value(race: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = race.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _horse_number(horse: dict[str, Any]) -> str:
    return str(horse.get("horse_number", "")).strip()


def _number_list(horses: list[dict[str, Any]]) -> list[str]:
    return [_horse_number(horse) for horse in horses]


def _raise_if_duplicate(numbers: list[str], label: str) -> None:
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1}, key=_number_sort_key)
    if duplicates:
        raise NarJsonDataError(f"{label}に重複馬番があります: {', '.join(duplicates)}")


def _validate_horse_identity(entry_horses: list[dict[str, Any]], speed_horses: list[dict[str, Any]]) -> None:
    speed_by_number = {_horse_number(horse): horse for horse in speed_horses}
    mismatches: list[str] = []
    for entry_horse in entry_horses:
        number = _horse_number(entry_horse)
        speed_horse = speed_by_number.get(number, {})
        entry_id = str(entry_horse.get("horse_id", "")).strip()
        speed_id = str(speed_horse.get("horse_id", "")).strip()
        if entry_id and speed_id and entry_id != speed_id:
            mismatches.append(f"馬番{number}: horse_id {entry_id} / {speed_id}")
        entry_name = _normalize_name(entry_horse.get("horse_name"))
        speed_name = _normalize_name(speed_horse.get("horse_name"))
        if entry_name and speed_name and entry_name != speed_name:
            mismatches.append(f"馬番{number}: 馬名 {entry_horse.get('horse_name')} / {speed_horse.get('horse_name')}")
    if mismatches:
        raise NarJsonDataError("出走表とタイム指数で馬情報が一致しません。\n" + "\n".join(mismatches[:8]))


def _normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _number_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value), value
    except ValueError:
        return 999, value


def _index_text(value: Any) -> str:
    parsed = parse_index(value)
    return "" if parsed is None else str(parsed)


def _type_label(data_type: str) -> str:
    return {
        "entry": "出走表JSON",
        "speed": "タイム指数JSON",
        "courseanalysis": "コース脚質HTML/JSON",
    }.get(data_type, data_type)


def _e(value: Any) -> str:
    return escape(str(value or ""), quote=True)
