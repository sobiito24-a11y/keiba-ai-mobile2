"""Read-only, horse-number keyed input adapter. No odds or result joins."""
from __future__ import annotations
import json
import math
import re
from datetime import date, datetime
from collections.abc import Mapping
from bs4 import BeautifulSoup
from .recent_races import build_recent_races
from .class_context import text


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def pick(row, *keys):
    for key in keys:
        v = row.get(key)
        if v is not None and str(v).strip() not in {"", "nan", "None", "—", "未取得"}:
            return v
    return None


def horse_no(row):
    v = number(pick(row, "horse_no", "馬番"))
    return str(int(v)) if v is not None and v > 0 and v.is_integer() else ""


def result_rows(result):
    tables = [getattr(result, name, None) for name in ("overall_table", "horse_evaluation")]
    merged = {}
    for table in tables:
        if table is None or not hasattr(table, "to_dict"):
            continue
        seen = set()
        for row in table.to_dict("records"):
            key = horse_no(row)
            if not key or key in seen:
                raise ValueError("V2: 馬番欠損・重複。行番号では補完しません。")
            seen.add(key)
            if key not in merged:
                merged[key] = dict(row)
            else:
                for k, v in row.items():
                    if pick(merged[key], k) is None:
                        merged[key][k] = v
    return [merged[k] for k in sorted(merged, key=int)]


def newspaper_past_evidence(html):
    """Scoped horse-number join, first three run slots (including empty slots).

    Current race results are never selected. Data07 (past popularity) is also
    intentionally ignored. Index values continue to come from saved inputs.
    """
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    output = {}
    for horse in soup.select("dl.HorseList"):
        number_node = horse.select_one(".Waku_Horse")
        key = horse_no({"horse_no": number_node.get_text(strip=True) if number_node else None})
        if not key or key in output:
            raise ValueError("V2新聞過去走: 馬番欠損・重複")
        runs = []
        for label, past in zip(("前走", "2走前", "3走前"), horse.select(".Past_Wrapper li.Past")[:3]):
            def t(selector):
                node = past.select_one(selector)
                return text(node.get_text(" ", strip=True)) if node else ""
            date_venue = t(".Data01")
            day = re.search(r"\d{1,2}/\d{1,2}", date_venue)
            venue = re.search(r"\d{1,2}/\d{1,2}\s+([^\s\d]+)", date_venue)
            count = re.fullmatch(r"(\d+)頭", t(".Data05"))
            condition = re.search(r"(芝|ダ|障)\s*(\d{3,4})", t(".Data09"))
            turn = re.search(r"左|右|直", t(".Data10"))
            margin = re.fullmatch(r"\(([+-]?\d+(?:\.\d+)?)\)", t(".Data23"))
            grade = t(".Data03")
            grade_node = past.select_one(".Data03 [class*='GradeType']")
            if grade_node:
                for cls in grade_node.get("class", []):
                    m = re.fullmatch(r"Icon_GradeType([123])", cls)
                    if m:
                        grade += " G" + m[1]
            runs.append(dict(label=label, date=day[0] if day else None,
                             venue=venue[1] if venue else None, race_name=t(".RaceName"),
                             finish=number(t(".Data04 .Num")), head_count=int(count[1]) if count else None,
                             surface=condition[1] if condition else None, distance=int(condition[2]) if condition else None,
                             turn=turn[0] if turn else None, margin=float(margin[1]) if margin else None,
                             race_data2=grade, class_label=None, race_grade=None,
                             opponent_evidence=t(".Data22") or None, time_index=None,
                             passing_order=t(".Data20"), source="saved_newspaper_past_block"))
        output[key] = runs
    return output


def recent_runs(row, evidence=None):
    normalized = build_recent_races(row)
    raw = pick(row, "_past_runs", "past_runs", "recent_runs") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = []
    if not isinstance(raw, (list, tuple)):
        raw = []
    output = []
    for run in normalized[:3]:
        label = run.get("label")
        extra = next((r for r in raw if isinstance(r, Mapping) and
                      (r.get("label") == label or r.get("key") == {"前走": "race1", "2走前": "race2", "3走前": "race3"}.get(label))), {})
        # Explicit whitelist: current race result/popularity cannot become a feature.
        output.append({**{k: run.get(k) for k in ("label", "date", "venue", "surface", "distance", "turn", "race_name", "finish", "time_index", "passing_order")},
                       "head_count": number(pick(extra, "head_count", "field_size", "頭数")),
                       "margin": number(pick(extra, "margin", "着差")),
                       "class_label": pick(extra, "class_label"),
                       "race_data2": pick(extra, "race_data2", "class_raw_text"),
                       "race_grade": pick(extra, "race_grade"),
                       "opponent_evidence": pick(extra, "opponent_strength_source")})
        if isinstance(output[-1]["date"], (date, datetime)):
            output[-1]["date"] = output[-1]["date"].isoformat()
    if evidence is not None:
        # Only pair the saved index with HTML run evidence when both dates agree.
        def month_day(v):
            digits = re.findall(r"\d+", str(v or "").split("T")[0])
            return tuple(map(int, digits[-2:])) if len(digits) >= 2 else None
        enriched = []
        for run in evidence:
            merged = dict(run)
            existing = next((r for r in output if r["label"] == run["label"]), {})
            if month_day(existing.get("date")) is not None and month_day(existing.get("date")) == month_day(run.get("date")):
                merged["time_index"] = existing.get("time_index")
            enriched.append(merged)
        return enriched
    return output


def race_id(result):
    info = result.race_info or {}
    if info.get("race_id"):
        return str(info["race_id"])
    for source in (result.source_files or {}).values():
        match = re.search(r"(?<!\d)(20\d{10})(?!\d)", str(source))
        if match:
            return match[1]
    return ""


def shadow_jockey_inputs(rows, html, info, expected_race_id, mode):
    """Read explicit saved course statistics into COPIES for V2 only.

    Canonical URL, course and horse number/name must agree. This deliberately
    does not repair or overwrite either application's existing formal tables.
    """
    from urllib.parse import urlparse, parse_qs
    import unicodedata
    copies = [dict(row) for row in rows]
    if not html or not expected_race_id:
        return copies
    soup = BeautifulSoup(html, "lxml")
    metadata = soup.select_one('link[rel="canonical"]') or soup.select_one('meta[property="og:url"]')
    url = urlparse((metadata.get("href") or metadata.get("content") or "") if metadata else "")
    query = parse_qs(url.query)
    if (url.hostname != ("race.netkeiba.com" if mode == "jra" else "nar.netkeiba.com")
            or query.get("race_id") != [str(expected_race_id)]
            or query.get("mode") != ["courseanalysis"] or query.get("cid") != ["2"]):
        return copies
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    course = re.search(r"([^\s|_]+?[芝ダ]\d{3,4}m)が得意な騎手", title)
    venue = info.get("racecourse") or info.get("venue")
    distance = number(info.get("distance"))
    surface = str(info.get("surface") or "").replace("ダート", "ダ")
    expected = f"{venue}{surface}{int(distance)}m" if venue and distance and surface else None
    if not course or course[1] != expected:
        return copies
    table = soup.select_one("table#table_sort_back")
    if table is None:
        return copies
    normalize = lambda value: re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))
    headers = [normalize(cell.get_text()) for cell in table.select("thead th")]
    required = ("馬番", "馬名", "出走回数", "複勝率")
    if any(headers.count(name) != 1 for name in required):
        return copies
    indexes = {name: headers.index(name) for name in required}
    evidence = {}
    for tr in table.select("tbody tr.HorseList"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) <= max(indexes.values()):
            continue
        values = {key: normalize(cells[i].get_text()) for key, i in indexes.items()}
        key = horse_no({"horse_no": values["馬番"]})
        if not key or key in evidence:
            raise ValueError("V2騎手成績: 馬番欠損・重複")
        evidence[key] = values
    for row in copies:
        values = evidence.get(horse_no(row))
        if not values or normalize(pick(row, "horse_name", "馬名") or "") != values["馬名"]:
            continue
        starts = number(values["出走回数"])
        rate = number(values["複勝率"].removesuffix("%"))
        if starts is None or starts < 0 or not starts.is_integer() or rate is None or not 0 <= rate <= 100:
            continue
        row["jockey_course_runs"] = starts
        row["jockey_course_top3_rate"] = rate
        row["_v2_jockey_source"] = "saved_courseanalysis_cid2_identity_checked"
    return copies


def shadow_jockey_change(row):
    # A missing previous jockey is not evidence of continuity or a switch.
    previous = pick(row, "_previous_jockey", "previous_jockey_market")
    if previous is None:
        return None
    return pick(row, "jockey_change_market")
