"""NAR classes: venue / age restrictions are never pooled with JRA."""
import re
from .class_context import age_restriction, context, header_evidence, text, normalized_grade_text


def classify_nar_class(info, html=""):
    raw, grade, source = header_evidence(info, html)
    venue = text(info.get("racecourse") or info.get("venue"))
    group_match = re.search(r"[23]歳\s*[-ー]?\s*([一二三四五六七八九十百\d]+)組", raw)
    if not group_match:
        group_match = re.search(r"[23]歳\s*[-ー]?\s*([一二三四五六七八九十百]+)(?=\s|/|$|\))", raw)
    if not group_match:
        group_match = re.search(r"(?:[ABC][123][-ー]|[ABC])\s*([一二三四五六七八九十百\d]+)組", raw)
    group = group_match[1] if group_match else ""
    age = age_restriction(raw)
    label, level = "不明", None
    graded = re.search(r"(?:Jpn|G)[123]|重賞", normalized_grade_text(grade + " " + raw), re.I)
    if graded:
        label = graded[0]
    elif "新馬" in raw:
        label = "新馬"
    elif age in {"2歳限定", "3歳限定"}:
        label = age + ("・" + group + "組" if group else "")
    else:
        general = re.sub(r"([ABC])\d+組", r"\1", raw)
        matches = re.findall(r"(?<![A-Za-z])([ABC])([123])?(?!\d)", general)
        if matches:
            labels = list(dict.fromkeys(a + b for a, b in matches))
            label = "/".join(labels)
            if len(labels) == 1:
                a, b = matches[0]
                level = {"A": 30, "B": 20, "C": 10}[a] + (4 - int(b) if b else 0)
    out = context("NAR", raw, label, level, source, venue, group)
    out["legacy_class_label"] = text(info.get("class_label"))
    out["class_grade_raw_v2"] = grade
    return out
