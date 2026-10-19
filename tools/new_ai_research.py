"""Independent post-processing, never launches collector or predictor."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.new_ai_research import read_snapshot,calculate,freeze,digest

def main():
 p=argparse.ArgumentParser();p.add_argument('--keiba',required=True,type=Path);p.add_argument('--stats',required=True,type=Path)
 p.add_argument('--out',required=True,type=Path);p.add_argument('--export-dir',type=Path);p.add_argument('--race-id');p.add_argument('--scheduled-at')
 a=p.parse_args()
 if a.scheduled_at and not a.race_id:p.error('--scheduled-at requires --race-id')
 s,h=read_snapshot(a.keiba);races=[r for r in s['races'] if not a.race_id or r['race_id']==a.race_id]
 if not races:p.error('race not found')
 for race in races:
  report=calculate(race,h,a.stats,a.scheduled_at);f=freeze(report,a.out)
  if a.export_dir:
   a.export_dir.mkdir(parents=True,exist_ok=True)
   target=a.export_dir/(str(race['race_id'])+'_'+f['input_sha256']+'.json')
   content=json.dumps({'payload':f,'payload_sha256':digest(f)},ensure_ascii=False,indent=2)
   if target.exists() and target.read_text(encoding='utf-8')!=content:raise ValueError('Existing export differs')
   if not target.exists():target.write_text(content,encoding='utf-8')
  print(race['race_id'],f['input_sha256'],f['time_status'])
if __name__=='__main__':main()
