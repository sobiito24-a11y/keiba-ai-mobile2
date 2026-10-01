"""JRA class normalization, isolated from official prediction inputs."""
import re
from .class_context import context, header_evidence, text, normalized_grade_text


def classify_jra_class(info, html=""):
    raw, grade, source = header_evidence(info, html)
    evidence = normalized_grade_text(grade + " " + raw)
    label, level = "不明", None
    match = re.search(r"(?<![A-Za-z])(?:Jpn|G)([123])(?!\d)", evidence, re.I)
    if match:
        label = match[0].replace("jpn", "Jpn").upper().replace("JPN", "Jpn")
        level = {"1": 8, "2": 7, "3": 6}[match[1]]
    else:
        for pattern, candidate, value in [
            (r"リステッド|(?<![A-Za-z])L(?![A-Za-z])", "L", 5),
            (r"オープン|(?<![A-Za-z])OP(?![A-Za-z])", "OP", 4),
            (r"3\s*勝|1600万", "3勝", 3), (r"2\s*勝|1000万", "2勝", 2),
            (r"1\s*勝|500万", "1勝", 1), (r"未勝利", "未勝利", 0), (r"新馬|メイクデビュー", "新馬", None),
        ]:
            if re.search(pattern, evidence, re.I):
                label, level = candidate, value
                break
    out = context("JRA", raw, label, level, source)
    out["legacy_class_label"] = text(info.get("class_label"))
    out["class_grade_raw_v2"] = grade
    return out
