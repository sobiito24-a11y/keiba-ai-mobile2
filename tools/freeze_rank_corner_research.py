"""Explicit research command, never called from normal prediction/save paths.

Input JSON: race_id, mode, rows (normalized pre-race facts), metadata.
Output is an exclusive NEW research JSON; no .keiba file is written.
Result/actual corner/payout joining belongs to a separate post-race process.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.rank_corner_research import comparison_rows, freeze, join_outcomes, write_frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--registry', type=Path, help='Shared duplicate-race registry across both repos/output folders')
    parser.add_argument('--phase', choices=['historical_research', 'future_validation'], default='historical_research')
    parser.add_argument('--csv', type=Path, help='Optional new research comparison CSV')
    parser.add_argument('--outcomes', type=Path, help='Join ONLY: input must be frozen research JSON; output is a separate post-race artifact')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    if args.output.exists() or (args.csv and args.csv.exists()):
        parser.error('Output already exists; never overwrite research artifacts')
    if args.outcomes:
        if args.phase != 'historical_research' or args.csv:
            parser.error('Outcome joining must be a separate command from pre-race freezing/CSV creation')
        joined = join_outcomes(data, json.loads(args.outcomes.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(joined, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        print(joined['prediction_hash'])
        return
    result = freeze(data['race_id'], data['mode'], data['rows'], data.get('metadata'))
    write_frozen(args.output, result, registry_dir=args.registry, phase=args.phase)
    if args.csv:
        rows = comparison_rows(result)
        with args.csv.open('x', encoding='utf-8-sig', newline='') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    print(result['input_hash'])


if __name__ == '__main__':
    main()
