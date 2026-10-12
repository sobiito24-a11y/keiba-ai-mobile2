"""Export read-only supplementary assessments from an archive, without results.

Usage: python tools/export_supplementary_assessments.py INPUT.keiba OUTPUT.json
Does not rebuild formal ranks, infer missing membership, or write the archive.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.supplementary_assessment import annotate, no, KEY, VERSION


def export(path):
    raw=Path(path).read_bytes()
    with zipfile.ZipFile(path) as archive:
        snapshot=json.loads(archive.read('snapshot.json'))
    out=[]
    for race in snapshot.get('races',[]):
        data=race.get('prediction_result') or {};rows={};mode=race.get('race_mode')
        for name in ('overall_table','horse_evaluation'):
            for row in (data.get(name) or {}).get('records',[]):
                if no(row):rows.setdefault(no(row),{}).update({k:v for k,v in row.items() if v is not None})
        debug=data.get('debug_info') or {}
        formal=debug.get('jra_formal_comparison_snapshot' if mode=='jra' else 'nar_top5_corner_order') or {}
        for h in formal.get('rows' if mode=='jra' else 'horses',[]):
            key=no(h)
            if key not in rows:continue
            # Whitelist only saved formal facts; never latest scoring.
            for k in ('pure_ability_top5_group','nar_final_mark','nar_final_rank','jra_top5_rank','jra_top5_score','jra_pure_ability_score','jra_training_grade'):
                if k in h:rows[key][k]=h[k]
            if mode=='nar' and 'nar_final_mark' in h:rows[key]['_display_nar_mark']=h['nar_final_mark']
        assessed=annotate(list(rows.values()),mode=mode,race_info=data.get('race_info') or {})
        out.append(dict(race_id=race.get('race_id'),prediction_created_at=race.get('prediction_created_at'),mode=mode,
                        horses=[dict(horse_no=no(h),assessment=h[KEY]) for h in assessed]))
    return dict(version=VERSION,archive_sha256=hashlib.sha256(raw).hexdigest(),races=out,trial_only=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive');parser.add_argument('output');args=parser.parse_args()
    target=Path(args.output)
    if target.exists():raise SystemExit('Output already exists; choose a new audit filename')
    if target.resolve()==Path(args.archive).resolve():raise SystemExit('Cannot overwrite source archive')
    target.write_text(json.dumps(export(args.archive),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
