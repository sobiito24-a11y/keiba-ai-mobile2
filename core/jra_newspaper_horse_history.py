"""Pre-race netkeiba JRA newspaper: per-run short notes and *career* performance.

These data are factual, separately saved evidence. Never amend the model's
ability scores, ranks, marks, or recommendations. No external fetch or postrace
results may be used. The previous three runs and the full-career table are
deliberately kept separate: three runs are NOT the lifetime sample.
"""
from __future__ import annotations

from datetime import date
import re
import unicodedata
from typing import Any, Mapping

from bs4 import BeautifulSoup

VERSION = "jra_newspaper_horse_history_v1_20261108"
LABELS = ("前走", "2走前", "3走前")
COURSE_PATTERN = re.compile(
    r"^(?:全(?:場)?(?:芝|ダ|障)(?:\d{3,4}m)?|"
    r"(?:札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)(?:芝|ダ|障)\d{3,4}m|"
    r"重不(?:芝|ダ|障)|全着)$"
)
DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})(?!\d)")


def _name(value: Any) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _horse_number(value: Any) -> int | None:
    try:
        value = str(value).strip()
        n = int(value)
        return n if n >= 1 else None
    except (ValueError, TypeError):
        return None


def _date(value: Any) -> tuple[int, int] | None:
    found = DATE_PATTERN.search(str(value or ""))
    if not found:
        return None
    month, day = int(found[1]), int(found[2])
    try:
        date(2024, month, day)
        return month, day
    except ValueError:
        return None


def _page_race_id(soup: BeautifulSoup) -> str:
    for selector in ('meta[property="og:url"]', 'link[rel="canonical"]'):
        node = soup.select_one(selector)
        if node:
            url = str(node.get("content") or node.get("href") or "")
            found = re.search(r"(?:race_id=|/race/)(\d{12})(?!\d)", url)
            if found:
                return found[1]
    return ""


def parse_newspaper_horse_history(
    html: str, *, expected_race_id: str,
) -> dict[str, dict[str, Any]]:
    """Only select each horse's own pre-race HorseList; fail closed on race mismatch."""
    if not html or not re.fullmatch(r"\d{12}", str(expected_race_id)):
        return {}
    soup = BeautifulSoup(html, "lxml")
    detected = _page_race_id(soup)
    if detected != expected_race_id:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for block in soup.select("dl.HorseList"):
        num_node = block.select_one("dt.Waku_Horse")
        if num_node is None:
            continue
        number = _horse_number(_text(num_node))
        name_node = block.select_one("dt.HorseName a, .Horse_Info .Horse02 a")
        name = _name(_text(name_node))
        if number is None or not name:
            continue
        number_text = str(number)
        if number_text in result:
            # Duplicate horse => a collision; do not accidentally cross-join.
            result[number_text] = {"status": "horse_duplicate", "name": name}
            continue
        notes = []
        past_nodes = block.select(".Past_Wrapper li.Past")
        for label, past in zip(LABELS, past_nodes[:3]):
            remark = _text(past.select_one(".Data24"))
            month_day = _date(_text(past.select_one(".Data01")))
            if month_day and remark and len(remark) <= 140 and "ダミー" not in remark:
                notes.append({"label": label, "month_day": list(month_day), "text": remark,
                              "source": "netkeiba_past_Data24"})
        performance = []
        per = block.select_one("dd.Performance")
        if per:
            for tr in per.select("tr"):
                cells = tr.find_all(["td", "th"], recursive=False)
                if len(cells) != 5:
                    continue
                label = _name(_text(cells[0]))
                if not COURSE_PATTERN.fullmatch(label):
                    continue
                values = []
                for cell in cells[1:]:
                    raw = _text(cell).replace(",", "")
                    if not re.fullmatch(r"\d{1,5}", raw):
                        values = []
                        break
                    values.append(int(raw))
                if len(values) == 4:
                    performance.append({
                        "label": label, "wins": values[0], "seconds": values[1],
                        "thirds": values[2], "other": values[3],
                        "starts": sum(values), "scope": "career_as_of_pre_race_newspaper",
                    })
        quote = _text(block.select_one("dd.Stable_Comment .Comment_Cell dd"))
        result[number_text] = {
            "status": "captured" if notes or performance or quote else "no_visible_data",
            "name": name, "notes": notes, "career": performance,
            "trainer_quote": quote[:500] if quote else "",
            "version": VERSION,
        }
    return result


def _dated_saved_runs(row: Mapping[str, Any], cutoff: str) -> dict[str, tuple[int, int]]:
    saved = row.get("_past_runs")
    if not isinstance(saved, list):
        return {}
    previous = {}
    for run in saved:
        if not isinstance(run, Mapping):
            continue
        label = run.get("label") or run.get("key")
        if label not in LABELS:
            continue
        date_string = str(run.get("race_date") or "")
        try:
            run_date = date.fromisoformat(date_string)
            race_date = date.fromisoformat(cutoff)
        except ValueError:
            continue
        if run_date < race_date:
            previous[label] = (run_date.month, run_date.day)
    return previous


def match_history_to_horse(
    evidence: Mapping[str, Any] | None, row: Mapping[str, Any],
    race_date: str,
) -> dict[str, Any]:
    """Verify horse number/name and date before accepting a past-run short note."""
    empty = {
        "jra_history_status": "未取得",
        "jra_past_short_notes": {},
        "jra_career_performance": [],
        "jra_trainer_original_quote": "",
        "jra_history_version": VERSION,
    }
    if not isinstance(evidence, Mapping) or evidence.get("status") != "captured":
        return empty
    expected_name = _name(row.get("馬名") or row.get("horse_name"))
    if not expected_name or _name(evidence.get("name")) != expected_name:
        return empty
    dated = _dated_saved_runs(row, race_date)
    notes = {}
    for note in evidence.get("notes") or []:
        label = note.get("label")
        when = note.get("month_day")
        if (label in dated and isinstance(when, list)
                and tuple(when) == dated[label]):
            notes[label] = str(note.get("text") or "").strip()
    career = [
        dict(item) for item in evidence.get("career") or []
        if isinstance(item, Mapping) and item.get("scope") == "career_as_of_pre_race_newspaper"
    ]
    return {
        "jra_history_status": "新聞原文取得" if notes or career else "対象データ未取得",
        "jra_past_short_notes": notes,
        "jra_career_performance": career,
        "jra_trainer_original_quote": str(evidence.get("trainer_quote") or ""),
        "jra_history_version": VERSION,
    }


def attach_jra_newspaper_history(result: Any, html_files: Mapping[str, str] | None) -> Any:
    """Save captured factual evidence onto JRA prediction tables for future .keiba."""
    if str(getattr(result, "race_mode", "")).lower() != "jra":
        return result
    source = dict(html_files or {})
    html = source.get("newspaper") or source.get("newspaper_context") or ""
    from .newspaper_v2_inputs import race_id
    expected = race_id(result)
    evidence = parse_newspaper_horse_history(html, expected_race_id=expected)
    info = getattr(result, "race_info", {}) or {}
    race_date = str(info.get("race_date") or info.get("date") or "")[:10]
    import pandas as pd
    for attr in ("overall_table", "horse_evaluation"):
        table = getattr(result, attr, None)
        if not isinstance(table, pd.DataFrame) or table.empty:
            continue
        target = table.copy()
        keys = ("jra_history_status", "jra_past_short_notes",
                "jra_career_performance", "jra_trainer_original_quote",
                "jra_history_version")
        for key in keys:
            if key not in target.columns:
                target[key] = pd.Series([None]*len(target), index=target.index, dtype="object")
        for idx, item in target.iterrows():
            row = item.to_dict()
            number = _horse_number(row.get("馬番"))
            data = match_history_to_horse(evidence.get(str(number)), row, race_date)
            for key, value in data.items():
                target.at[idx, key] = value
        setattr(result, attr, target)
    debug = dict(getattr(result, "debug_info", None) or {})
    debug["jra_newspaper_horse_history"] = {
        "version": VERSION, "race_id": expected, "horse_count": len(evidence),
        "source": "pre_race_uploaded_newspaper", "research_only": True,
    }
    result.debug_info = debug
    return result


def _course_label(race_info: Mapping[str, Any] | None) -> str:
    info = race_info or {}
    venue = str(info.get("racecourse") or info.get("venue") or "").strip()
    surface = str(info.get("surface") or "").strip().replace("ダート", "ダ")
    distance = info.get("distance")
    try:
        number = int(float(distance))
    except (ValueError, TypeError):
        return ""
    if surface not in ("芝", "ダ", "障") or not venue:
        return ""
    return f"{venue}{surface}{number}m"


def with_jra_history_context(
    view: list[Mapping[str, Any]],
    sources: list[Mapping[str, Any]],
    race_info: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read-only view projection; missing means unavailable, never 0-0-0-0."""
    raw = {}
    for item in sources:
        try:
            no = str(int(item.get("馬番")))
        except (ValueError, TypeError):
            continue
        if no not in raw:
            raw[no] = item
    target = _course_label(race_info)
    out = []
    for horse in view:
        candidate = dict(horse)
        if str(horse.get("mode") or "") != "jra":
            out.append(candidate)
            continue
        source = raw.get(str(horse.get("no") or ""), {})
        if _name(horse.get("name")) and _name(source.get("馬名")) != _name(horse.get("name")):
            source = {}
        notes = source.get("jra_past_short_notes")
        career = source.get("jra_career_performance")
        notes = dict(notes) if isinstance(notes, Mapping) else {}
        career = list(career) if isinstance(career, list) else []
        current = next((row for row in career if row.get("label") == target), None)
        candidate.update(
            jra_past_short_notes=notes,
            jra_career_performance=career,
            jra_career_current_course=current,
            jra_history_status=source.get("jra_history_status") or "未取得",
            jra_trainer_original_quote=source.get("jra_trainer_original_quote") or "",
        )
        out.append(candidate)
    return out
