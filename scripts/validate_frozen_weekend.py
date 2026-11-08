#!/usr/bin/env python3
"""Reproduce frozen research comparisons on unseen .keiba snapshots + real payouts.

Usage:
  python scripts/validate_frozen_weekend.py --snapshots 20261114_all.keiba 20261115_all.keiba \
      --results official_results.csv --output frozen_holdout.csv

Result CSV columns:
  race_id,date,mode,winner_no,second_no,third_no,win_pay,quin_pay,
  wide12,wide13,wide23,wide_pair_payouts_json(optional)
Dead-heats require a complete wide_pair_payouts_json, e.g. {"2-7":730,"5-7":1170}.
This script does not fetch results, choose bets, edit predictions or merge a model.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from itertools import combinations
import json
from pathlib import Path
import re
import zipfile

from core.frozen_research_review import (
    FROZEN_VERSION, HOLDOUT_START, jra_research_pair_three, with_frozen_reviews,
)
from core.nar_recent_form_reference import evaluate_nar_rows


def number(value):
    try:
        result = float(value)
        return result if result == result and result not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError, OverflowError):
        return None


def rank(value):
    x = number(value)
    return int(x) if x is not None and x >= 1 and x.is_integer() else None


def indices(rows, key):
    valid = [(float(row[key]), rank(row.get("馬番"))) for row in rows if number(row.get(key)) is not None]
    valid = [(v, no) for v, no in valid if no is not None]
    return {no: i for i, (_, no) in enumerate(sorted(valid, key=lambda pair: (-pair[0], pair[1])), 1)}


def rest_days(row, race_date):
    dates = []
    for past in row.get("_past_runs") or []:
        try:
            old = date.fromisoformat(str(past.get("race_date")))
            if old < race_date and rank(past.get("position")) is not None:
                dates.append(old)
        except (TypeError, ValueError):
            pass
    return (race_date - max(dates)).days if dates else None


def research_for_race(race, snapshot_date):
    mode = race.get("race_mode")
    if mode not in ("jra", "nar"):
        return None
    race_date = str(race.get("date") or snapshot_date)[:10]
    day = date.fromisoformat(race_date)
    records = race.get("prediction_result", {}).get("overall_table", {}).get("records", [])
    if not records:
        return None
    race_info = dict(date=race_date, venue=race.get("venue", ""), distance=race.get("distance"))
    course, distance = indices(records, "コース指数"), indices(records, "距離指数")
    metas = {rank(h.get("horse_no")): h for h in race.get("horses") or []}
    references = {}
    if mode == "nar":
        debug = race.get("prediction_result", {}).get("debug_info") or {}
        shadow = debug.get("nar_newspaper_v2_shadow") or debug.get("nar_newspaper_v2_input_enriched_shadow")
        references = {
            rank(h.get("馬番")): h
            for h in evaluate_nar_rows(records, race_info, shadow)
        }
    view = []
    for row in records:
        no = rank(row.get("馬番"))
        if no is None:
            continue
        ability = rank(row.get("market_ability_rank"))
        if ability is None and mode == "nar":
            ability = rank(row.get("ability_rank"))
        meta = metas.get(no, {})
        grade = str(meta.get("training_short") or row.get("training_grade") or "").strip()[:1].upper()
        days = rest_days(row, day)
        view.append({
            "mode": mode, "no": str(no), "ability_rank": ability,
            "corner": rank(row.get("netkeiba_corner4_rank")),
            "nar_form_ref_prior_corner": references.get(no, {}).get("nar_form_ref_prior_corner"),
            "explorer_facts": {
                "training": grade, "rest_days": days,
                "rest_status": "verified" if days is not None else "unknown",
                "metrics": {
                    "ability": {"rank": ability},
                    "course": {"rank": course.get(no)},
                    "distance": {"rank": distance.get(no)},
                    "corner": rank(row.get("netkeiba_corner4_rank")),
                },
            },
        })
    ranked = sorted(
        (h for h in view if h["ability_rank"] is not None),
        key=lambda h: (h["ability_rank"], int(h["no"])),
    )
    pure = [str(h["no"]) for h in ranked[:3]] if len(ranked) >= 3 and ranked[0]["ability_rank"] == 1 else []
    frozen = jra_research_pair_three(view) if mode == "jra" else []
    watch = [
        h["no"] for h in with_frozen_reviews(view)
        if mode == "nar" and h["frozen_review_candidate"]
    ]
    return {
        "race_id": str(race.get("race_id") or ""),
        "date": race_date, "mode": mode,
        "venue": str(race.get("venue") or ""), "race": str(race.get("race_number") or ""),
        "version": FROZEN_VERSION, "pure3": pure,
        "jra_frozen3": frozen, "nar_watch": watch,
        "ability_complete": len(ranked) == len(view),
    }


def pair_key(a, b):
    return "-".join(str(n) for n in sorted((int(a), int(b))))


def payouts(entry):
    raw = entry.get("wide_pair_payouts_json")
    if raw and raw.strip():
        data = json.loads(raw)
        return {pair_key(*key.split("-")): int(value) for key, value in data.items()}
    winner, second, third = [rank(entry.get(k)) for k in ("winner_no", "second_no", "third_no")]
    if not all((winner, second, third)):
        raise ValueError("Missing official top three; no ROI calculation")
    # Do not claim complete wide ROI for dead-heats without an explicit map.
    if entry.get("third_no_extra"):
        raise ValueError("Joint third requires complete wide_pair_payouts_json")
    return {
        pair_key(winner, second): int(entry.get("wide12") or 0),
        pair_key(winner, third): int(entry.get("wide13") or 0),
        pair_key(second, third): int(entry.get("wide23") or 0),
    }


def calculate_three(numbers, entry):
    if len(numbers) != 3:
        return dict(stake=0, wide=0, quin=0)
    combos = {pair_key(a, b) for a, b in combinations(numbers, 2)}
    wide = payouts(entry)
    win_pair = pair_key(entry["winner_no"], entry["second_no"])
    return dict(stake=300,
                wide=sum(wide.get(pair, 0) for pair in combos),
                quin=int(entry.get("quin_pay") or 0) if win_pair in combos else 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", nargs="+", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-development-data", action="store_true",
                        help="Clearly label in-sample data; never count it toward future holdout.")
    args = parser.parse_args()
    with args.results.open(encoding="utf-8-sig", newline="") as stream:
        outcome = {str(r["race_id"]): r for r in csv.DictReader(stream)}
    output = []
    for archive in args.snapshots:
        with zipfile.ZipFile(archive) as z:
            snapshot = json.loads(z.read("snapshot.json"))
        for race in snapshot.get("races", []):
            item = research_for_race(race, snapshot.get("saved_at", "")[:10])
            if item is None:
                continue
            date_part = item["date"]
            if not args.allow_development_data and date_part < HOLDOUT_START:
                raise ValueError(f"{date_part} is development data; not a genuine holdout")
            # Never assert that a same-day saved snapshot was before the off time
            # without separately verifying the snapshot's saved timestamp.
            official = outcome.get(item["race_id"])
            if official is None:
                continue
            if official.get("date") and official["date"] != date_part:
                raise ValueError(f"Date mismatch in race {item['race_id']}")
            if official.get("mode") and official["mode"] != item["mode"]:
                raise ValueError(f"Mode mismatch in race {item['race_id']}")
            item["cohort"] = "development" if date_part < HOLDOUT_START else "prospective"
            item["winner"] = official["winner_no"]
            item["nar_watch_winner"] = official["winner_no"] in item["nar_watch"]
            item["nar_watch_won_count"] = 1 if item["nar_watch_winner"] else 0
            for key in ("pure3", "jra_frozen3"):
                result = calculate_three(item[key], official) if item[key] else dict(stake=0, wide=0, quin=0)
                item.update({f"{key}_{k}": v for k, v in result.items()})
            for key in ("pure3", "jra_frozen3", "nar_watch"):
                item[key] = "+".join(item[key])
            output.append(item)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        if output:
            writer = csv.DictWriter(stream, fieldnames=list(output[0]))
            writer.writeheader()
            writer.writerows(output)
    print(f"{len(output)} races written to {args.output}. "
          "Frozen research only; judge over multiple unseen weekends.")


if __name__ == "__main__":
    main()
