"""Conservative class evidence for newspaper shadow; never writes legacy classes."""
from __future__ import annotations

import re
import unicodedata
from bs4 import BeautifulSoup


def text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalized_grade_text(value):
    def replace(match):
        return match[1] + {"I": "1", "II": "2", "III": "3"}.get(match[2].upper(), match[2])
    return re.sub(r"(Jpn|G)\s*(III|II|I|[123])(?![A-Za-z0-9])", replace, text(value), flags=re.I)


def header_evidence(info, html=""):
    """Only race header text / its grade icon; never generic HTML attributes."""
    if html:
        soup = BeautifulSoup(html, "html.parser")
        # Newspaper past-run rows also use .RaceName. Select the current header
        # once, never every node sharing that class.
        selectors = (".RaceName", ".RaceData01", ".RaceData02") if soup.select_one(".RaceData02") else (".data_intro h1", ".data_intro .racedata", ".data_intro .smalltxt")
        nodes = [node for selector in selectors if (node := soup.select_one(selector)) is not None]
        if nodes:
            raw = " / ".join(n.get_text(" ", strip=True) for n in nodes)
            # GradeType icons are meaningful only inside this race's name.
            name = soup.select_one(".RaceName, .data_intro h1")
            grade = ""
            if name:
                for icon in name.select("[class], [title], [alt]"):
                    attrs = " ".join(icon.get("class", []))
                    match = re.search(r"(?:^|\s)Icon_GradeType([123])(?:\s|$)", attrs)
                    if match:
                        grade = "G" + match[1]
                        break
                    label = text(icon.get("title") or icon.get("alt"))
                    if re.fullmatch(r"(?:G|Jpn)[123]", label, re.I):
                        grade = label
            return text(raw), grade, "race_header_html"
    # Excludes class_label: this is the old, potentially misclassified output.
    raw = " / ".join(text(info.get(k)) for k in ("race_name", "race_data", "race_data2", "raw_class_text", "surface") if info.get(k))
    grade = text(info.get("race_grade"))
    return raw, grade, "saved_race_header"


def age_restriction(raw):
    match = re.search(r"([234])歳(以上|上)?", raw)
    if match:
        return match[1] + ("歳以上" if match[2] else "歳限定")
    return "一般" if "一般" in raw else "不明"


def context(family, raw, label, level, source, venue="", group=""):
    discipline = "jump" if re.search(r"障(?:害|[未新]|\d)|ジャンプ|J[・.]?G[123]", normalized_grade_text(raw)) else "flat"
    age = age_restriction(raw)
    # NAR age-limited classes have no sound mapping onto general A/B/C levels.
    comparable = ""
    if label != "不明" and age != "不明" and (family == "JRA" or venue):
        comparable = "|".join([family, discipline, age, venue if family == "NAR" else "national"])
    return dict(class_family=family, class_label_v2=label, class_level_v2=level,
                age_restriction_v2=age, race_discipline_v2=discipline,
                class_source_v2=source, class_confidence_v2="explicit" if label != "不明" else "unknown",
                comparable_class_group_v2=comparable, class_raw_v2=raw,
                venue_v2=venue, class_group_v2=group)


def class_change(current, previous):
    if not previous or not current.get("comparable_class_group_v2") or current["comparable_class_group_v2"] != previous.get("comparable_class_group_v2"):
        return "比較不能"
    a, b = current.get("class_level_v2"), previous.get("class_level_v2")
    if a is None or b is None:
        return "比較不能"
    return "同級" if a == b else "昇級" if a > b else "降級"


def class_history(current, past):
    """past is most-recent first, with explicit class context and finish."""
    comparable = [p for p in past if class_change(current, p["class"]) != "比較不能"]
    best = max(comparable, key=lambda p: p["class"]["class_level_v2"], default=None)
    return {
        "previous_to_current": class_change(current, past[0]["class"]) if past else "比較不能",
        "best_recent_class": best["class"]["class_label_v2"] if best else None,
        "same_class_good_runs": sum(class_change(current, p["class"]) == "同級" and p.get("finish") is not None and 1 <= p["finish"] <= 3 for p in comparable),
    }
