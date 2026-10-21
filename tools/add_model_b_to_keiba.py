"""Offline only. Write a new .keiba containing A and frozen retrospective B."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.model_b_archive import add_to_copy

def main():
    p=argparse.ArgumentParser(description='既存予想を保護して研究B付きの別ファイルを作成');p.add_argument('input');p.add_argument('output');a=p.parse_args()
    source=Path(a.input).resolve();dest=Path(a.output).resolve()
    if source==dest or dest.exists():p.error('出力には新しいファイル名を指定してください（上書き禁止）')
    data,audit=add_to_copy(source.read_bytes())
    with dest.open('xb') as f:f.write(data)
    print(json.dumps(dict(output=str(dest),races=audit),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
