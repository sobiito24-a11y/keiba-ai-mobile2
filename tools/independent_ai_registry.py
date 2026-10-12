"""Import UI's pre-race record, or join official outcomes. Never execute purchases."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.independent_ai_registry import register,settle_saved
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['register','settle']);p.add_argument('json_file');p.add_argument('--root',required=True);p.add_argument('--race-id');a=p.parse_args()
    value=json.loads(Path(a.json_file).read_text(encoding='utf-8'))
    if a.command=='register':print(register(a.root,value))
    else:
        result=settle_saved(a.root,a.race_id,value);print(json.dumps({k:result[k] for k in ('race_id','stake','payout','roi')},ensure_ascii=False))
if __name__=='__main__':main()
