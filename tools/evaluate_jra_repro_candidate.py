"""Explicit historical research replay; never changes an input .keiba file.

Results JSON is joined only after every candidate has been calculated.
"""
import argparse
import copy
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.models import PredictionResult
from core.jra_repro_candidate import evaluate_repro_candidate


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for h in rows for k in h))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)


def evaluate(paths, results_path, output):
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    rows, replays, exclusions, manifest = [], [], [], []
    for path in map(Path, paths):
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append({'path': str(path), 'sha256': checksum})
        for race in json.loads(zipfile.ZipFile(path).read('snapshot.json'))['races']:
            if race['race_mode'] != 'jra':continue
            raw = copy.deepcopy(race['prediction_result']);info = raw.get('race_info') or {}
            rid = race['race_id'];race_date = info.get('race_date') or race['date']
            time = re.search(r'(\d{1,2}:\d{2})発走', info.get('race_data', ''))
            post = datetime.fromisoformat(race_date + 'T' + time[1]) if time else None
            created = datetime.fromisoformat(race['prediction_created_at'])
            reason = ('障害' if '障' in str(info.get('surface'))+str(info.get('race_data')) else
                      '発走時刻不明' if post is None else '発走後生成' if created >= post else '')
            frozen = race.get('jra_win_probability_calibration', {}).get('horses', [])
            if not frozen or any(h.get('jra_top5_rank') is None or h.get('jra_top5_score') is None for h in frozen):
                reason = reason or '保存正式順位・スコア不足'
            if reason:
                exclusions.append({'race_id':rid,'reason':reason});continue
            for key in ('horse_evaluation', 'overall_table'):
                table = raw[key];raw[key] = pd.DataFrame(table['records'], columns=table['columns']) if table else None
            info['race_id'] = rid;raw['race_info'] = info
            result = PredictionResult(**raw);before = copy.deepcopy(result)
            payload = evaluate_repro_candidate(result, formal_rows=frozen, evaluated_at='historical_reference_replay')
            replays.append(payload)
            pd.testing.assert_frame_equal(result.overall_table, before.overall_table)
            pd.testing.assert_frame_equal(result.horse_evaluation, before.horse_evaluation)
            for horse in payload['horses']:
                # Every non-reproduction component must explain the saved score.
                old = horse['candidate_score']-horse['repro_bonus']+horse['old_repro_bonus']
                if abs(old-horse['formal_score']) > 1e-8:
                    raise ValueError(f'{rid}/{horse["horse_no"]}: saved score has another difference')
                rows.append({'race_id':rid, 'date':race_date, 'venue':race['venue'],
                             'race_number':int(rid[-2:]), 'prediction_created_at':created.isoformat(),
                             'scheduled_start_time':post.isoformat(),
                             **{k:v for k,v in horse.items() if k!='input_audit'},
                             'valid_runs':horse['input_audit']['valid_runs'],
                             'missing_reason':horse['input_audit']['missing_reason']})
        assert hashlib.sha256(path.read_bytes()).hexdigest()==checksum
    # Outcomes enter only here, downstream of model creation.
    results = json.loads(Path(results_path).read_text(encoding='utf-8'))
    for h in rows:h['finish'] = results.get(h['race_id'], {}).get(h['horse_no'])
    summaries, races, swaps = [], [], []
    for date in ['all'] + sorted({h['date'] for h in rows}):
        subset = [h for h in rows if date=='all' or h['date']==date]
        for label, field in [('A saved','formal_rank'),('B repro repair','candidate_rank'),('C pure','pure_rank')]:
            winners = [h for h in subset if h['finish']==1]
            valid = [h for h in winners if h[field] is not None]
            summaries.append({'date':date,'model':label,'races':len({h['race_id'] for h in subset}),
                              'result_races':len(valid),'top1':sum(h[field]<=1 for h in valid),
                              'top3':sum(h[field]<=3 for h in valid),'top5':sum(h[field]<=5 for h in valid),
                              'mean_winner_rank':sum(h[field] for h in valid)/len(valid) if valid else None})
    for rid in sorted({h['race_id'] for h in rows}):
        field=[h for h in rows if h['race_id']==rid]
        winner=next((h for h in field if h['finish']==1),None)
        if winner:
            races.append({**winner,'change': '改善' if winner['candidate_rank']<winner['formal_rank'] else '悪化' if winner['candidate_rank']>winner['formal_rank'] else '不変'})
        for h in field:
            if (h['formal_rank']<=5)!=(h['candidate_rank']<=5):
                swaps.append({**h,'swap':'追加' if h['candidate_rank']<=5 else '除外'})
    for name, data in [('horse_comparison',rows),('metrics',summaries),('winner_changes',races),('top5_swaps',swaps),('exclusions',exclusions)]:
        write_csv(output/(name+'.csv'),data)
    (output/'candidate_replays.json').write_text(json.dumps(replays,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    (output/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# JRA再現性入力修正版：開発・診断用の参考再計算',
          '正式予想は保存値を使用。今回結果は評価専用。未使用データでの未来検証ではありません。',
          f'対象 {len(replays)}R / {len(rows)}頭。再現性非ゼロ {sum(h["repro_bonus"]>0 for h in rows)}頭。',
          f'再現性区分 {dict(Counter(h["repro_grade"] for h in rows))}',
          '|日付|モデル|R|結果R|Top1|Top3|Top5|勝ち馬平均順位|','|---|---|---:|---:|---:|---:|---:|---:|']
    for s in summaries:
        text.append('|'+ '|'.join(str(s[k]) for k in ('date','model','races','result_races','top1','top3','top5','mean_winner_rank'))+'|')
    text += ['', '## 京都11R 個別比較', '|馬名|正式順位|修正順位|正式点|修正点|再現性|加点|着順|','|---|---:|---:|---:|---:|---|---:|---:|']
    for h in rows:
        if h['race_id']=='202608040111' and h['horse_no'] in ('6','18','8'):
            text.append('|'+ '|'.join(str(h[k]) for k in ('horse_name','formal_rank','candidate_rank','formal_score','candidate_score','repro_grade','repro_bonus','finish'))+'|')
    text += ['', '各馬の根拠と出典・欠損・競合はcandidate_replays.json、改善/悪化の内訳はwinner_changes.csv、Top5入替はtop5_swaps.csv。',
             '当時のCanonical印が保存されていない場合は正式式の参考印と明記し、保存印と混同していません。',
             '勝率は既存の温度8.5・一様縮小0.35による参考変換。修正版用に再校正していません。']
    (output/'REPRO_VALIDATION_REPORT.md').write_text('\n\n'.join(text),encoding='utf-8')
    print(json.dumps({'races':len(replays),'horses':len(rows),'grades':dict(Counter(h['repro_grade'] for h in rows)), 'metrics':summaries},ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshots',nargs='+',required=True);parser.add_argument('--results',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();evaluate(args.snapshots,args.results,args.output)
