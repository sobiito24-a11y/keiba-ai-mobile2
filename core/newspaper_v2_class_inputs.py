"""Versioned class evidence adapter. Frozen v1 parser is intentionally untouched."""
import re
from bs4 import BeautifulSoup
from .class_context import text
from .newspaper_v2_inputs import horse_no, number
from .jra_class_v2 import classify_jra_class
from .nar_class_v2 import classify_nar_class

JRA_VENUES = frozenset("札幌 函館 福島 新潟 東京 中山 中京 京都 阪神 小倉".split())
NAR_VENUES = frozenset("門別 帯広 盛岡 水沢 浦和 船橋 大井 川崎 金沢 笠松 名古屋 園田 姫路 高知 佐賀".split())


def previous_class_evidence(html):
    """Select only the first past-run slot for each horse; retain source text."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    output = {}
    for horse in soup.select("dl.HorseList"):
        no = horse.select_one(".Waku_Horse")
        key = horse_no({"horse_no": no.get_text(strip=True) if no else None})
        if not key or key in output:
            raise ValueError("class split: missing/duplicate horse number")
        past = horse.select_one(".Past_Wrapper li.Past")
        def t(selector):
            node = past.select_one(selector) if past else None
            return text(node.get_text(" ", strip=True)) if node else ""
        first_line = past.select_one(".PastDataLine") if past else None
        # Class badges are siblings of Data01, not children of Data03.
        badges = [text(n.get_text(" ", strip=True)) for n in first_line.select(".Icon_GradeType")] if first_line else []
        link = past.select_one(".RaceName a[href]") if past else None
        match = re.search(r"/race/(\d{12})(?:/|$)", link.get("href", "")) if link else None
        venue = re.search(r"\d{1,2}/\d{1,2}\s+([^\s\d]+)", t(".Data01"))
        count = re.fullmatch(r"(\d+)\s*頭", t(".Data05"))
        finish = re.fullmatch(r"(\d+)\s*(?:着)?", t(".Data04 .Num"))
        output[key] = dict(
            source="saved_newspaper_first_past_slot", past_slot_present=past is not None,
            race_name=t(".RaceName"), venue=venue[1] if venue else None,
            previous_race_id=match[1] if match else None,
            finish=int(finish[1]) if finish else None,
            head_count=int(count[1]) if count else None,
            class_badge_raw=" / ".join(badges),
            data01_raw=t(".Data01"), data03_raw=t(".Data03"),
            data04_raw=t(".Data04 .Num"), data05_raw=t(".Data05"), data09_raw=t(".Data09"),
        )
    return output


def classify_previous(evidence):
    venue = text(evidence.get("venue"))
    family = "JRA" if venue in JRA_VENUES else "NAR" if venue in NAR_VENUES else "unknown"
    raw = " / ".join(str(evidence.get(k) or "") for k in ("race_name", "class_badge_raw", "data03_raw", "race_data2", "class_label"))
    condition = text(evidence.get("data09_raw") or evidence.get("surface"))
    discipline = "jump" if "障" in condition or "障害" in raw or re.search(r"J[・.]G", raw) else "flat" if re.search(r"芝|ダ", condition) else "unknown"
    classify = classify_jra_class if family == "JRA" else classify_nar_class
    context = classify({"race_name": raw, "racecourse": venue,
                        "surface": "障害" if discipline == "jump" else condition,
                        "race_grade": evidence.get("race_grade")})
    context["class_family"] = family
    context["race_discipline_v2"] = discipline
    context["venue_v2"] = venue
    if family == "unknown" or discipline == "unknown":
        context["comparable_class_group_v2"] = ""
    return context


def comparison_blockers(current, previous):
    """Independent flags, never infer age/venue/family comparability."""
    flags = []
    for side, ctx in (("current", current), ("previous", previous)):
        if ctx.get("class_label_v2") in (None, "不明"):
            flags.append(side + "_class_unknown")
        if ctx.get("class_level_v2") is None:
            flags.append(side + "_class_level_unmapped")
        if ctx.get("age_restriction_v2") in (None, "不明"):
            flags.append(side + "_age_unknown")
        if ctx.get("class_family") not in ("JRA", "NAR"):
            flags.append(side + "_family_unknown")
        if ctx.get("race_discipline_v2") not in ("flat", "jump"):
            flags.append(side + "_discipline_unknown")
    if current.get("class_family") != previous.get("class_family"):
        flags.append("family_mismatch")
    ca, pa = current.get("age_restriction_v2"), previous.get("age_restriction_v2")
    if ca not in (None,"不明") and pa not in (None,"不明") and ca != pa:
        flags.append("age_mismatch")
    cd, pd = current.get("race_discipline_v2"), previous.get("race_discipline_v2")
    if cd in ("flat","jump") and pd in ("flat","jump") and cd != pd:
        flags.append("discipline_mismatch")
    if current.get("class_family") == "NAR" or previous.get("class_family") == "NAR":
        cv,pv=current.get("venue_v2"),previous.get("venue_v2")
        if not cv or not pv:
            flags.append("venue_unknown")
        elif cv != pv:
            flags.append("venue_mismatch")
    if not current.get("comparable_class_group_v2") or current.get("comparable_class_group_v2") != previous.get("comparable_class_group_v2"):
        flags.append("comparable_group_unavailable_or_mismatch")
    return flags


def finish_quality(evidence):
    f,n=number(evidence.get("finish")),number(evidence.get("head_count"))
    flags=[]
    if f is None:
        raw = text(evidence.get("data04_raw"))
        if raw in {"中", "中止", "取", "取消", "除", "除外", "失", "失格"}:
            flags.append("previous_finish_noncompletion_or_withdrawal")
        else:
            flags.append("previous_finish_parse_failure" if raw else "previous_finish_missing")
    if n is None:
        flags.append("previous_head_count_parse_failure" if evidence.get("data05_raw") else "previous_head_count_missing")
    if f is not None and (not f.is_integer() or f < 1):flags.append("previous_finish_invalid")
    if n is not None and (not n.is_integer() or n <= 1):flags.append("previous_head_count_invalid")
    if f is not None and n is not None and f > n:flags.append("finish_exceeds_head_count")
    return (None if flags else 1 - 2 * (f - 1) / (n - 1)), flags
