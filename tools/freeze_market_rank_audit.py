"""Freeze new allow-listed research input, or join results into a different file."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.market_rank_audit import build, seal, save_once, evaluate_frozen

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',help='prediction JSON, or fixed record when --result is supplied')
    p.add_argument('--output',required=True,help='directory for freeze; new result file for evaluation')
    p.add_argument('--result',help='separate result JSON containing race_id and outcome')
    a=p.parse_args(); src=json.loads(Path(a.input).read_text(encoding='utf-8'))
    if a.result:
        res=json.loads(Path(a.result).read_text(encoding='utf-8'))
        evaluated=evaluate_frozen(src,res['race_id'],res['outcome'])
        with Path(a.output).open('x',encoding='utf-8') as f:json.dump(evaluated,f,ensure_ascii=False,indent=2)
    else:
        print(save_once(seal(build(src['race_id'],src['mode'],src['horses'],src['metadata'])),a.output))
