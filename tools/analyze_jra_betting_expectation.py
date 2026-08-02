# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import types
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.purchase_conditions import (
    ASSETS_ANALYSIS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_REPORT_DIR,
    build_condition_json_payload,
    build_purchase_condition_report,
    enrich_analysis_records,
    load_jra_analysis_records,
    search_purchase_conditions,
    write_condition_outputs,
)
from core.ticket_strategy_analysis import evaluate_ticket_strategies


DEFAULT_COLLECTED_JRA_DIRS = [
    Path(r"C:\Users\28011\Documents\Codex\Codex\2026-06-26\new-chat\keiba_ai_mobile\collected_html_test5\jra"),
    PROJECT_ROOT / "collected_html_test5" / "jra",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search JRA purchase conditions from saved audit data or collected HTML.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--collected-jra-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--app-json-dir", type=Path, default=ASSETS_ANALYSIS_DIR)
    args = parser.parse_args()

    collected_dir = args.collected_jra_dir or find_default_collected_jra_dir()
    payouts_by_race: dict[str, dict[str, Any]] = {}
    html_meta: dict[str, Any] = {}

    if collected_dir is not None and collected_dir.exists():
        records, html_meta, payouts_by_race = load_collected_jra_html_records(collected_dir, args.manifest)
        records = enrich_analysis_records(records)
        meta = {
            "data_dir": str(collected_dir),
            "records_path": "collected_html",
            "payoff_path": "result_html",
            "race_count": int(records["race_id"].nunique()) if not records.empty else 0,
            "horse_count": int(len(records)),
            "source_columns": list(records.columns),
            **html_meta,
        }
    else:
        records, meta = load_jra_analysis_records(args.data_dir)

    all_frame, official, reference, avoid, search_meta = search_purchase_conditions(records)
    meta.update(search_meta)

    time_split = build_time_split_frame(all_frame)
    if payouts_by_race:
        ticket_all, ticket_official, ticket_reference, ticket_avoid = evaluate_ticket_strategies(
            records,
            payouts_by_race,
            source_race_count=int(meta.get("race_count", 0) or 0),
        )
    else:
        from core.purchase_conditions import build_ticket_strategy_detailed

        ticket_all = build_ticket_strategy_detailed(records, args.data_dir)
        ticket_official = ticket_all.copy()
        ticket_reference = pd.DataFrame()
        ticket_avoid = pd.DataFrame()

    paths = write_condition_outputs(records, all_frame, official, reference, avoid, time_split, ticket_all, meta, args.out_dir)
    extra_paths = write_ticket_outputs(
        args.out_dir,
        ticket_all,
        ticket_official,
        ticket_reference,
        ticket_avoid,
        official,
        reference,
        meta,
    )
    app_paths = write_app_json_outputs(args.app_json_dir, ticket_official, ticket_reference, official, reference, meta)

    # Backward-compatible output names used by earlier investigation reports.
    ticket_all.to_csv(args.out_dir / "ticket_strategy_summary.csv", index=False, encoding="utf-8-sig")
    feature_summary = build_feature_summary(records)
    feature_summary.to_csv(args.out_dir / "feature_expectation_summary.csv", index=False, encoding="utf-8-sig")
    condition_combo = all_frame[all_frame["条件数"].le(2)].copy() if "条件数" in all_frame.columns else all_frame.copy()
    condition_combo[[col for col in condition_combo.columns if col != "conditions"]].to_csv(
        args.out_dir / "condition_combo_ranking.csv", index=False, encoding="utf-8-sig"
    )
    (args.out_dir / "jra_betting_expectation_report.md").write_text(
        (args.out_dir / "jra_purchase_condition_report.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    print(f"data: {meta.get('race_count')}R / {meta.get('horse_count')} horses")
    print(f"collected source: {collected_dir if collected_dir else args.data_dir}")
    print(f"explored conditions: {meta.get('explored_conditions')}")
    print(f"official purchase conditions: {len(official)}")
    print(f"ticket strategies: {len(ticket_all)} total / {len(ticket_official)} official")
    print(f"output: {args.out_dir}")
    for name, path in {**paths, **extra_paths, **app_paths}.items():
        print(f"{name}: {path}")


def find_default_collected_jra_dir() -> Path | None:
    for path in DEFAULT_COLLECTED_JRA_DIRS:
        if path.exists():
            return path
    return None


def load_collected_jra_html_records(
    collected_dir: Path,
    manifest_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    install_runtime_stubs()
    from core.jra_notebook_logic import predict_jra_from_html

    manifest_info = inspect_manifest(manifest_path or collected_dir.parent / "manifest_20260802_095555.csv")
    horse_rows: list[dict[str, Any]] = []
    payouts_by_race: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    attempted_races = 0

    for race_dir in sorted(path for path in collected_dir.iterdir() if path.is_dir()):
        attempted_races += 1
        race_id = race_dir.name
        files = {path.stem.split("_")[-1]: path for path in race_dir.glob("*.html")}
        speed_path = files.get("speed")
        result_path = files.get("result")
        if speed_path is None:
            errors.append(f"{race_id}: speed HTML missing")
            continue
        if result_path is None:
            errors.append(f"{race_id}: result HTML missing")
            continue

        html_files: dict[str, str] = {}
        file_names: dict[str, str] = {}
        for suffix, key in [("speed", "speed"), ("newspaper", "newspaper"), ("oikiri", "oikiri"), ("style", "style")]:
            path = files.get(suffix)
            if path is not None:
                html_files[key] = read_text(path)
                file_names[key] = path.name
        try:
            prediction = predict_jra_from_html(html_files, file_names, fetch_past_detail=False)
            finish, payouts = parse_result_html(result_path)
        except Exception as exc:  # pragma: no cover - captured in generated audit report
            errors.append(f"{race_id}: prediction/result parse failed: {exc}")
            continue

        payouts_by_race[race_id] = payouts
        table = prediction.overall_table.copy()
        if table.empty:
            errors.append(f"{race_id}: prediction table empty")
            continue

        for _, row in table.iterrows():
            no = normalize_horse_no(row.get("馬番"))
            if not no:
                continue
            result_row = finish.get(no, {})
            finish_no = result_row.get("finish")
            record = row.to_dict()
            record.update(
                {
                    "race_id": race_id,
                    "race_name": prediction.race_name,
                    "実際の着順": finish_no,
                    "結果人気": result_row.get("result_popularity"),
                    "結果オッズ": result_row.get("result_odds"),
                    "単勝払戻": payouts.get("win", {}).get(no, 0) if finish_no == 1 else 0,
                    "複勝払戻": payouts.get("place", {}).get(no, 0) if finish_no and finish_no <= 3 else 0,
                    "odds_basis": "saved_prediction_html",
                }
            )
            horse_rows.append(record)

    records = pd.DataFrame(horse_rows)
    meta = {
        "collected_dir": str(collected_dir),
        "manifest": manifest_info,
        "attempted_races": attempted_races,
        "prediction_races": int(records["race_id"].nunique()) if not records.empty else 0,
        "prediction_errors": errors,
        "prediction_error_count": len(errors),
        "odds_basis": "保存HTMLのレース前オッズで条件判定、払戻は結果HTMLの確定払戻",
    }
    return records, meta, payouts_by_race


def install_runtime_stubs() -> None:
    try:
        import requests  # noqa: F401
    except Exception:
        requests_mod = types.ModuleType("requests")

        class _OfflineSession:
            def __init__(self) -> None:
                self.headers: dict[str, str] = {}

            def get(self, *_args: Any, **_kwargs: Any) -> Any:
                raise RuntimeError("offline analysis: external HTTP fetch disabled")

        requests_mod.Session = _OfflineSession  # type: ignore[attr-defined]
        sys.modules.setdefault("requests", requests_mod)

    try:
        import bs4  # noqa: F401
    except Exception:
        from lxml import html as lxml_html

        def class_xpath(class_name: str) -> str:
            return f"contains(concat(' ', normalize-space(@class), ' '), ' {class_name} ')"

        def selector_part_to_xpath(part: str) -> str:
            part = part.strip()
            if not part:
                return "*"
            if part.startswith("."):
                return f"*[{class_xpath(part[1:])}]"
            if part.startswith("#"):
                return f'*[@id="{part[1:]}"]'
            attr = re.fullmatch(r"\[([A-Za-z0-9_-]+)\]", part)
            if attr:
                return f"*[@{attr.group(1)}]"
            tag_class = re.fullmatch(r"([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)", part)
            if tag_class:
                return f"{tag_class.group(1)}[{class_xpath(tag_class.group(2))}]"
            return part

        def selector_to_xpath(selector: str) -> str:
            xpath = "."
            for part in [item for item in re.split(r"\s+", selector.strip()) if item]:
                xpath += "//" + selector_part_to_xpath(part)
            return xpath

        class MiniElement:
            def __init__(self, element: Any) -> None:
                self.element = element

            def __bool__(self) -> bool:
                return self.element is not None

            def __str__(self) -> str:
                return lxml_html.tostring(self.element, encoding="unicode")

            @property
            def title(self) -> "MiniElement | None":
                return self.select_one("title")

            def get(self, key: str, default: Any = None) -> Any:
                return self.element.attrib.get(key, default)

            def get_text(self, separator: str = " ", strip: bool = False) -> str:
                parts = list(self.element.itertext())
                if strip:
                    parts = [part.strip() for part in parts if part and part.strip()]
                return separator.join(parts)

            def select(self, selector: str) -> list["MiniElement"]:
                out = []
                for raw in str(selector).split(","):
                    try:
                        out.extend(self.element.xpath(selector_to_xpath(raw)))
                    except Exception:
                        pass
                return [MiniElement(item) for item in out]

            def select_one(self, selector: str) -> "MiniElement | None":
                values = self.select(selector)
                return values[0] if values else None

            def find(self, *_args: Any, **_kwargs: Any) -> None:
                return None

            def find_all(self, *_args: Any, **_kwargs: Any) -> list[Any]:
                return []

            def decompose(self) -> None:
                parent = self.element.getparent()
                if parent is not None:
                    parent.remove(self.element)

        class BeautifulSoup(MiniElement):
            def __init__(self, markup: Any, *_args: Any, **_kwargs: Any) -> None:
                super().__init__(lxml_html.fromstring(str(markup or "<html></html>")))

        bs4_mod = types.ModuleType("bs4")
        bs4_mod.BeautifulSoup = BeautifulSoup  # type: ignore[attr-defined]
        sys.modules.setdefault("bs4", bs4_mod)


def inspect_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    statuses: dict[str, int] = {}
    kinds: dict[str, int] = {}
    missing: list[dict[str, Any]] = []
    for row in rows:
        statuses[row.get("status", "")] = statuses.get(row.get("status", ""), 0) + 1
        kinds[row.get("kind", "")] = kinds.get(row.get("kind", ""), 0) + 1
        file_path = Path(row.get("path", ""))
        if row.get("status") != "saved" or not file_path.exists():
            missing.append(
                {
                    "race_id": row.get("race_id"),
                    "kind": row.get("kind"),
                    "status": row.get("status"),
                    "message": row.get("message"),
                }
            )
    return {
        "path": str(path),
        "exists": True,
        "rows": len(rows),
        "race_count": len({row.get("race_id") for row in rows}),
        "statuses": statuses,
        "kinds": kinds,
        "missing_count": len(missing),
        "missing": missing[:20],
    }


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp932", "euc-jp"):
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if "<html" in text.lower() or "netkeiba" in text.lower():
            return text
    return data.decode("utf-8", errors="replace")


def parse_result_html(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    html = read_text(path)
    tables = [flatten_columns(table) for table in pd.read_html(StringIO(html), flavor="lxml")]
    result_table = find_result_table(tables)
    finish: dict[str, dict[str, Any]] = {}
    if result_table is not None:
        rank_col = first_col(result_table, "着") or result_table.columns[0]
        horse_col = first_col(result_table, "馬", "番") or result_table.columns[2]
        name_col = first_col(result_table, "馬名")
        pop_col = first_col(result_table, "人気")
        odds_col = first_col(result_table, "単勝") or first_col(result_table, "オッズ")
        for _, row in result_table.iterrows():
            no = normalize_horse_no(row.get(horse_col))
            rank = to_int(row.get(rank_col))
            if not no or rank is None:
                continue
            finish[no] = {
                "finish": rank,
                "result_name": str(row.get(name_col, "") or "") if name_col else "",
                "result_popularity": to_int(row.get(pop_col)) if pop_col else None,
                "result_odds": to_float(row.get(odds_col)) if odds_col else None,
            }

    payouts: dict[str, Any] = {
        "win": {},
        "place": {},
        "wide": {},
        "quinella": {},
        "exacta": {},
        "trio": {},
        "trifecta": {},
    }
    for table in tables:
        if table.shape[1] < 3:
            continue
        for _, row in table.iterrows():
            kind = str(row.iloc[0])
            combo = str(row.iloc[1])
            amount = str(row.iloc[2])
            nums = re.findall(r"\d+", combo)
            pays = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", amount)]
            if "単勝" in kind and nums and pays:
                payouts["win"][nums[0]] = pays[0]
            elif "複勝" in kind and nums and pays:
                for no, pay in zip(nums, pays):
                    payouts["place"][no] = pay
            elif "ワイド" in kind and len(nums) >= 2 and pays:
                for pair, pay in zip(pairwise_numbers(nums), pays):
                    payouts["wide"][tuple(sorted(pair, key=int))] = pay
            elif "馬連" in kind and len(nums) >= 2 and pays:
                payouts["quinella"][tuple(sorted(nums[:2], key=int))] = pays[0]
            elif "馬単" in kind and len(nums) >= 2 and pays:
                payouts["exacta"][tuple(nums[:2])] = pays[0]
            elif "3連複" in kind and len(nums) >= 3 and pays:
                payouts["trio"][tuple(sorted(nums[:3], key=int))] = pays[0]
            elif "3連単" in kind and len(nums) >= 3 and pays:
                payouts["trifecta"][tuple(nums[:3])] = pays[0]
    return finish, payouts


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            " ".join(str(part) for part in col if str(part) and not str(part).startswith("Unnamed")).strip()
            for col in out.columns
        ]
    else:
        out.columns = [str(col) for col in out.columns]
    return out


def find_result_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    for table in tables:
        cols = " ".join(str(col) for col in table.columns)
        if "着" in cols and "馬" in cols and ("人気" in cols or "単勝" in cols):
            return table
    return tables[0] if tables else None


def first_col(df: pd.DataFrame, *needles: str) -> str | None:
    for col in df.columns:
        name = str(col)
        compact = re.sub(r"\s+", "", name)
        if all(needle in name or needle in compact for needle in needles):
            return col
    return None


def pairwise_numbers(nums: list[str]) -> list[tuple[str, str]]:
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None


def normalize_horse_no(value: Any) -> str:
    number = to_int(value)
    return str(number) if number is not None else ""


def write_ticket_outputs(
    out_dir: Path,
    ticket_all: pd.DataFrame,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    ticket_avoid: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    meta: dict[str, Any],
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "ticket_by_type": out_dir / "ticket_strategy_by_type.csv",
        "ticket_ranked": out_dir / "ticket_strategy_ranked.csv",
        "ticket_reference": out_dir / "ticket_strategy_reference.csv",
        "ticket_avoid": out_dir / "ticket_strategy_avoid.csv",
        "ticket_json": out_dir / "ticket_strategy_ranked.json",
        "ticket_report": out_dir / "jra_ticket_strategy_report.md",
    }
    by_type = ticket_all.sort_values(["ticket_type", "reliability_score", "return_rate"], ascending=[True, False, False]) if not ticket_all.empty else ticket_all
    by_type.to_csv(paths["ticket_by_type"], index=False, encoding="utf-8-sig")
    ticket_official.to_csv(paths["ticket_ranked"], index=False, encoding="utf-8-sig")
    ticket_reference.to_csv(paths["ticket_reference"], index=False, encoding="utf-8-sig")
    ticket_avoid.to_csv(paths["ticket_avoid"], index=False, encoding="utf-8-sig")
    payload = build_app_recommendation_payload(ticket_official, ticket_reference, official, reference, meta, ticket_only=True)
    paths["ticket_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["ticket_report"].write_text(build_ticket_report(ticket_all, ticket_official, ticket_reference, ticket_avoid, meta), encoding="utf-8")
    return paths


def write_app_json_outputs(
    app_json_dir: Path,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    meta: dict[str, Any],
) -> dict[str, Path]:
    app_json_dir.mkdir(parents=True, exist_ok=True)
    betting_payload = build_app_recommendation_payload(ticket_official, ticket_reference, official, reference, meta)
    condition_payload = build_condition_json_payload(official, reference, meta)
    ticket_payload = build_app_recommendation_payload(ticket_official, ticket_reference, official, reference, meta, ticket_only=True)
    paths = {
        "app_betting_json": app_json_dir / "betting_recommendations.json",
        "app_condition_json": app_json_dir / "purchase_condition_ranked.json",
        "app_ticket_json": app_json_dir / "ticket_strategy_ranked.json",
    }
    paths["app_betting_json"].write_text(json.dumps(betting_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["app_condition_json"].write_text(json.dumps(condition_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    paths["app_ticket_json"].write_text(json.dumps(ticket_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return paths


def build_app_recommendation_payload(
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    official: pd.DataFrame,
    reference: pd.DataFrame,
    meta: dict[str, Any],
    *,
    ticket_only: bool = False,
) -> dict[str, Any]:
    ticket_entries = ticket_entries_from_frame(pd.concat([ticket_official.head(20), ticket_reference.head(20)], ignore_index=True))
    condition_entries = [] if ticket_only else condition_entries_from_payload(build_condition_json_payload(official, reference, meta))
    return {
        "version": 2,
        "scope": "jra",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "race_count": int(meta.get("race_count", 0) or 0),
            "horse_count": int(meta.get("horse_count", 0) or 0),
            "source_race_count": int(meta.get("race_count", 0) or 0),
            "odds_basis": meta.get("odds_basis", "保存HTMLのレース前オッズで条件判定、払戻は結果HTMLの確定払戻"),
            "manifest": meta.get("manifest", {}),
        },
        "recommendations": ticket_entries + condition_entries,
    }


def ticket_entries_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if frame is None or frame.empty:
        return entries
    for _, row in frame.iterrows():
        entries.append(
            {
                "strategy_id": row.get("strategy_id"),
                "recommendation_kind": "ticket_strategy",
                "ticket_type": row.get("ticket_type"),
                "label": row.get("label"),
                "stance": row.get("stance"),
                "role_pattern": row.get("role_pattern"),
                "condition_labels": [row.get("label")],
                "sample_horses": int(row.get("purchase_points", 0) or 0),
                "sample_races": int(row.get("purchase_races", 0) or 0),
                "purchase_races": int(row.get("purchase_races", 0) or 0),
                "purchase_points": int(row.get("purchase_points", 0) or 0),
                "hit_rate": float(row.get("hit_rate", 0) or 0),
                "return_rate": float(row.get("return_rate", 0) or 0),
                "profit": float(row.get("profit", 0) or 0),
                "average_payout": float(row.get("average_payout", 0) or 0),
                "reliability_score": float(row.get("reliability_score", 0) or 0),
                "risk_label": row.get("risk_label"),
                "stars": row.get("stars"),
                "max_payout_contribution": float(row.get("max_payout_contribution", 0) or 0),
                "high_payout_dependency": row.get("high_payout_dependency"),
                "time_split_result": row.get("time_split_result"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "source_race_count": int(row.get("source_race_count", 0) or 0),
                "odds_basis": row.get("odds_basis"),
                "current_odds_note": row.get("current_odds_note"),
            }
        )
    return entries


def condition_entries_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("recommendations", [])
    for item in entries:
        if isinstance(item, dict):
            item.setdefault("recommendation_kind", "purchase_condition")
            item.setdefault("return_rate", max(float(item.get("win_roi", 0) or 0), float(item.get("place_roi", 0) or 0)))
            item.setdefault("risk_label", item.get("ranking_type", "参考"))
            item.setdefault("source_race_count", (payload.get("meta") or {}).get("race_count", 0))
    return entries


def build_ticket_report(
    ticket_all: pd.DataFrame,
    ticket_official: pd.DataFrame,
    ticket_reference: pd.DataFrame,
    ticket_avoid: pd.DataFrame,
    meta: dict[str, Any],
) -> str:
    lines = [
        "# JRA券種別買い方検証レポート",
        "",
        "AI点・印・能力評価・Parser・PredictionResult・PNG・既存買い目ロジックは変更せず、保存HTMLから再集計した分析です。",
        "",
        "## データ",
        f"- 対象レース数: {meta.get('race_count')}R",
        f"- 対象馬数: {meta.get('horse_count')}頭",
        f"- 収集manifest: {json.dumps(meta.get('manifest', {}), ensure_ascii=False)}",
        f"- オッズ基準: {meta.get('odds_basis')}",
        f"- 予想生成エラー: {meta.get('prediction_error_count', 0)}件",
        "",
        "## 正式ランキング",
        markdown_table(ticket_official.head(30), ["ticket_type", "label", "purchase_races", "purchase_points", "hit_rate", "return_rate", "profit", "average_payout", "max_payout_contribution", "risk_label"]),
        "",
        "## 参考ランキング",
        markdown_table(ticket_reference.head(30), ["ticket_type", "label", "purchase_races", "purchase_points", "hit_rate", "return_rate", "profit", "average_payout", "max_payout_contribution", "risk_label"]),
        "",
        "## 買わない方が良い条件",
        markdown_table(ticket_avoid.head(30), ["ticket_type", "label", "purchase_races", "hit_rate", "return_rate", "profit"]),
        "",
        "## 券種別全体",
        markdown_table(ticket_all.head(80), ["ticket_type", "label", "purchase_races", "purchase_points", "hit_rate", "return_rate", "profit", "risk_label"]),
        "",
        "## 注意",
        "現在はサンプル数が小さいため、正式条件でも過学習リスクがあります。100R、300R、500R、1000Rと増やすほど信頼度が上がる設計です。",
    ]
    return "\n".join(lines)


def build_time_split_frame(all_frame: pd.DataFrame) -> pd.DataFrame:
    if all_frame.empty:
        return pd.DataFrame()
    columns = [
        "条件内容",
        "ranking_type",
        "探索期間_該当馬数",
        "探索期間_単勝回収率",
        "探索期間_複勝回収率",
        "検証期間_該当馬数",
        "検証期間_単勝回収率",
        "検証期間_複勝回収率",
        "検証メモ",
    ]
    return all_frame[[col for col in columns if col in all_frame.columns]].copy()


def build_feature_summary(records: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    features = [
        ("AI順位", "ai_rank_eval"),
        ("AI点", "ai_score_eval"),
        ("能力評価値", "ability_value_eval"),
        ("SS/A/B/C/Z", "display_group_eval"),
        ("オッズ", "odds_eval"),
        ("人気", "popularity_eval"),
        ("距離指数", "距離指数_num"),
        ("コース指数", "コース指数_num"),
        ("★最高指数", "star_available_eval"),
        ("脚質", "脚質"),
        ("調教評価", "_調教評価記号"),
    ]
    for label, column in features:
        if column not in records.columns:
            continue
        series = records[column]
        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if clean.empty:
                continue
            values = pd.qcut(series.rank(method="first"), q=min(4, max(1, clean.size // 30)), duplicates="drop")
        else:
            values = series.astype(str)
        for value, group in records.groupby(values, dropna=False):
            if len(group) < 10:
                continue
            rows.append(feature_stats(label, str(value), group))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["単勝回収率", "複勝回収率", "対象数"], ascending=[False, False, False]).reset_index(drop=True)


def feature_stats(feature: str, value: str, group: pd.DataFrame) -> dict[str, object]:
    n = len(group)
    finish = pd.to_numeric(group["finish_eval"], errors="coerce")
    win_pay = pd.to_numeric(group["win_payoff_eval"], errors="coerce").fillna(0).sum()
    place_pay = pd.to_numeric(group["place_payoff_eval"], errors="coerce").fillna(0).sum()
    stake = n * 100
    return {
        "項目": feature,
        "条件": value,
        "対象数": n,
        "勝率": round(float(finish.eq(1).sum()) / n * 100, 1) if n else 0.0,
        "複勝率": round(float(finish.between(1, 3).sum()) / n * 100, 1) if n else 0.0,
        "単勝回収率": round(float(win_pay) / stake * 100, 1) if stake else 0.0,
        "複勝回収率": round(float(place_pay) / stake * 100, 1) if stake else 0.0,
    }


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame is None or frame.empty:
        return "該当なし"
    cols = [col for col in columns if col in frame.columns]
    if not cols:
        return "該当なし"
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in frame[cols].iterrows():
        values = []
        for col in cols:
            value = row.get(col)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                value = ""
            values.append(str(value).replace("|", "/").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)


if __name__ == "__main__":
    main()
