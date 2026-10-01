"""Offline diagnostic replay. Frozen ranks and new reference V2 are distinct.

Results JSON: {race_id: {horse_no: finish}}. Results enter only after evaluation.
No predictor, old Top5 reconstruction, coefficient search, or snapshot write.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.newspaper_v2_engine import evaluate_shadow
from core.newspaper_v2_inputs import horse_no, number, pick


def read_races(path):
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("snapshot.json"))["races"]


def frozen_rows(race):
    rows = {horse_no(h): dict(h) for h in race.get("horses", []) if horse_no(h)}
    for row in (race.get("prediction_result", {}).get("overall_table") or {}).get("records", []):
        key = horse_no(row)
        if key:
            # Formal horse records are the frozen source of saved ability rank.
            rows[key] = {**row, **rows.get(key, {})}
    if race.get("race_mode") == "nar":
        for row in rows.values():
            if number(row.get("nar_top5_rank")) is None:
                # Formal NAR Top5 is defined by saved canonical pure rank.
                # This is an alias, not a sort/reconstruction from ability values.
                row["nar_top5_rank"] = number(pick(row, "ability_rank", "nar_pure_ability_rank"))
                row["_official_top5_rank_source"] = "saved_canonical_ability_rank_alias"
    return [rows[k] for k in sorted(rows, key=int)]


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def evaluate_files(paths, output, results=None, html_roots=()):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    results = results or {}
    headers = {}
    for root in html_roots:
        for path in Path(root).rglob("*_newspaper.html"):
            headers.setdefault(path.name.split("_")[0], path)
    audits, rows_out, replays, source_manifest = [], [], [], []
    metrics = defaultdict(list)
    seen = set()
    for path in paths:
        source_manifest.append({"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()})
        for race in read_races(path):
            rid, mode = str(race["race_id"]), race["race_mode"]
            if rid in seen:
                raise ValueError("duplicate race_id: " + rid)
            seen.add(rid)
            source = race.get("prediction_result", {})
            info = {**source.get("race_info", {}), "race_name": race.get("race_name"), "race_id": rid}
            rows = frozen_rows(race)
            html = headers[rid].read_text(encoding="utf-8-sig") if rid in headers else ""
            shadow = source.get("debug_info", {}).get(mode + "_newspaper_v2_shadow")
            provenance = "frozen_v2" if shadow else "reference_recalculation_v2_only"
            if not shadow:
                shadow = evaluate_shadow(rows, info, mode, html=html, race_identifier=rid)
            replays.append({"race_id": rid, "provenance": provenance, "shadow": shadow})
            ctx = shadow["class_context"]
            audits.append({"race_id": rid, "mode": mode, "date": race.get("date"), "venue": race.get("venue"),
                           "race_name": race.get("race_name"), "horse_count": len(rows),
                           "legacy_class": info.get("class_label"), **ctx,
                           "prediction_created_at": race.get("prediction_created_at"),
                           "scheduled_post_time": info.get("scheduled_post_time"),
                           "provenance": provenance, "header_source": str(headers.get(rid, "saved_header")),
                           "result_matched": rid in results})
            # Outcome lookup is deliberately downstream of all V2 calculations.
            finishes = results.get(rid, {})
            by_no = {h["horse_no"]: h for h in shadow["horses"]}
            probability_field = mode + "_win_probability"
            probabilities = {horse_no(r): number(r.get(probability_field)) for r in rows}
            prob_order = sorted(probabilities, key=lambda k: (-(probabilities[k] or 0), int(k))) if all(v is not None for v in probabilities.values()) else []
            complete = {
                "frozen_pure_ability": all(number(pick(r, "ability_rank", "nar_pure_ability_rank")) is not None for r in rows),
                "frozen_official_top5": all(number(r.get(mode + "_top5_rank")) is not None for r in rows),
                "frozen_current_evaluation": all(number(r.get("current_evaluation_rank")) is not None for r in rows),
                "frozen_probability": bool(prob_order),
                "v2_win_candidate": all(h.get(mode + "_v2_win_candidate_rank") is not None for h in shadow["horses"]),
                "v2_top5_candidate": all(h.get(mode + "_v2_top5_candidate_rank") is not None for h in shadow["horses"]),
            }
            baseline = "frozen_official_top5" if mode == "jra" else "frozen_pure_ability"
            paired = complete[baseline] and complete["v2_win_candidate"] and complete["v2_top5_candidate"]
            for row in rows:
                key = horse_no(row)
                sh = by_no.get(key, {})
                rank_fields = {
                    "frozen_pure_ability": number(pick(row, "ability_rank", "nar_pure_ability_rank")),
                    "frozen_official_top5": number(row.get(mode + "_top5_rank")),
                    "frozen_current_evaluation": number(row.get("current_evaluation_rank")),
                    "frozen_probability": prob_order.index(key) + 1 if key in prob_order else None,
                    "v2_win_candidate": sh.get(mode + "_v2_win_candidate_rank"),
                    "v2_top5_candidate": sh.get(mode + "_v2_top5_candidate_rank"),
                }
                finish = number(finishes.get(key))
                quality = sh.get(mode + "_v2_data_quality", "unknown")
                rows_out.append({"race_id": rid, "mode": mode, "date": race.get("date"), "venue": race.get("venue"), "horse_no": key,
                                 "horse_name": pick(row, "horse_name", "馬名"), "finish": finish, "quality": quality,
                                 **rank_fields, "legacy_class_shift": sh.get("legacy_class_shift"),
                                 "previous_to_current_v2": sh.get("class_history", {}).get("previous_to_current")})
                if finish == 1:
                    for model, rank in rank_fields.items():
                        # Do not score partial-field rankings as full-field predictions.
                        rank = rank if complete[model] else None
                        for dimension, value in [("all", "all"), ("date", race.get("date")), ("venue", race.get("venue")),
                                                 ("class", ctx["class_label_v2"]), ("discipline", ctx["race_discipline_v2"]),
                                                 ("age_restriction", ctx["age_restriction_v2"]), ("quality", quality)]:
                            metrics[(mode, model, dimension, str(value))].append(rank)
                        if paired and model in {baseline, "v2_win_candidate", "v2_top5_candidate"}:
                            metrics[(mode, model, "paired_with_official", "all")].append(rank)
    summaries = []
    for (mode, model, dimension, value), ranks in sorted(metrics.items()):
        valid = [r for r in ranks if r is not None]
        n = len(valid)
        summaries.append(dict(mode=mode, model=model, dimension=dimension, value=value, result_races=len(ranks),
                              evaluable_races=n, missing_rank_races=len(ranks)-n,
                              top1=sum(r <= 1 for r in valid), top3=sum(r <= 3 for r in valid), top5=sum(r <= 5 for r in valid),
                              top1_rate=sum(r <= 1 for r in valid)/n if n else None,
                              top3_rate=sum(r <= 3 for r in valid)/n if n else None,
                              top5_rate=sum(r <= 5 for r in valid)/n if n else None,
                              mean_winner_rank=sum(valid)/n if n else None))
    for name, data in [("class_audit", audits), ("horse_comparison", rows_out), ("metrics", summaries)]:
        write_csv(output / (name + ".csv"), data)
    for name, data in [("v2_reference_replays", replays), ("source_manifest", source_manifest), ("metrics", summaries)]:
        (output / (name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    report = ["# 新聞型V2 開発・診断用比較", "", "V2未保存の過去レースは参考再計算。正式予想・旧Snapshotは再生成／更新していません。",
              "未取得の正式順位は欠損として除外。モデル間の母数が違う場合は改善とは判定できません。", "", f"入力 {len(audits)}R / 結果照合 {sum(a['result_matched'] for a in audits)}R", "",
              "|系統|評価|母数|Top1|Top3|Top5|勝ち馬平均順位|", "|---|---|---:|---:|---:|---:|---:|"]
    for r in summaries:
        if r["dimension"] == "all":
            report.append(f'|{r["mode"]}|{r["model"]}|{r["evaluable_races"]}|{r["top1"]}|{r["top3"]}|{r["top5"]}|{r["mean_winner_rank"]}|')
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    return audits, summaries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--results-json")
    parser.add_argument("--html-root", action="append", default=[])
    args = parser.parse_args()
    outcomes = json.loads(Path(args.results_json).read_text(encoding="utf-8-sig")) if args.results_json else {}
    evaluate_files(args.snapshots, args.output, outcomes, args.html_root)
