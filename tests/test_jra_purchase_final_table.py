from core.jra_purchase_navigator import build_jra_purchase_navigation


def _rows():
    rows = []
    marks = ["◎", "○", "▲", "△", "✔︎", "✓"]
    for i, mark in enumerate(marks, start=1):
        rows.append({
            "number": str(i), "name": f"馬{i}", "v1_final_mark": mark,
            "jra_top5_rank": i, "jra_top5_score": 110 - i * 5,
            "_v1_ability_rank": i, "jra_pure_ability_score": 100 - i * 4,
            "v1_reproducibility": "○" if i == 1 else "—",
            "v1_pace_eval": "○" if i == 1 else "—",
            "jra_training_grade": "A" if i == 1 else "B",
        })
    return rows


def test_final_marks_define_roles_and_support_signals_define_grade():
    nav = build_jra_purchase_navigation(_rows(), race_mode="jra", race_info={"surface": "芝"})
    assert [h["number"] for h in nav["buy_groups"]["中心"]] == ["1"]
    assert [h["number"] for h in nav["buy_groups"]["本線"]] == ["2", "3"]
    assert [h["number"] for h in nav["buy_groups"]["狙い"]] == ["5"]
    assert [h["number"] for h in nav["hole_attention"]] == ["6"]
    assert nav["purchase_grade"] == "A"
    assert nav["axis_candidate"]["number"] == "1"


def test_odds_and_popularity_never_change_jra_final_purchase_grade():
    rows_a = _rows(); rows_b = _rows()
    for row in rows_a: row.update(odds=1.1, popularity=1)
    for row in rows_b: row.update(odds=999, popularity=99)
    a = build_jra_purchase_navigation(rows_a, race_mode="jra", race_info={"surface": "芝"})
    b = build_jra_purchase_navigation(rows_b, race_mode="jra", race_info={"surface": "芝"})
    assert a["purchase_grade"] == b["purchase_grade"]
    assert a["buy_groups"] == b["buy_groups"]
