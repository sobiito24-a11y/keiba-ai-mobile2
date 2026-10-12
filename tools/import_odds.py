"""Keiba AI Data manual odds import. Creates a new archive, never calls a provider."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.independent_ai import from_result
from core.independent_ai_odds_io import read_archive,restore_race,import_file,attach_archive

def main():
    ap=argparse.ArgumentParser(description='保存済みオッズを.keibaコピーへ関連付ける（自動取得なし）')
    ap.add_argument('--keiba',required=True);ap.add_argument('--odds',required=True)
    ap.add_argument('--race-id',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args();target=Path(args.output)
    if target.exists():ap.error('出力先が存在します。元ファイルを上書きしません。')
    try:
        raw=Path(args.keiba).read_bytes();_,event=read_archive(raw)
        matches=[r for r in event['races'] if str(r['race_id'])==args.race_id]
        if len(matches)!=1:raise ValueError('レースを一意に確認できません')
        p=from_result(restore_race(matches[0]));p['race_id']=args.race_id
        f=Path(args.odds);quotes=import_file(f.read_bytes(),f.name,p)
        value=attach_archive(raw,p,quotes)
        with target.open('xb') as out:out.write(value)
        print(json.dumps({'status':'imported','race_id':args.race_id,'prices':sum(len(q['prices']) for q in quotes),'output':str(target),'note':'価格認識と鮮度・購入判断は別判定'},ensure_ascii=False))
    except (ValueError,OSError) as exc:ap.exit(2,str(exc)+'\n')

if __name__=='__main__':main()
