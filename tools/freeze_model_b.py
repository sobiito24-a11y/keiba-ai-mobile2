"""Offline, explicit fitting only. Never imported by the prediction pipeline."""
import argparse,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.model_b_features import SETS,TRANSFORM_VERSION
from core.model_b import digest,VERSION

def main():
    import pandas as pd
    import sklearn
    from sklearn.linear_model import LogisticRegression
    parser=argparse.ArgumentParser();parser.add_argument('audit_csv');parser.add_argument('output');args=parser.parse_args()
    source=Path(args.audit_csv);data=pd.read_csv(source)
    artifact=dict(transform_version=TRANSFORM_VERSION,train_end=str(data.date.max()),training_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),library_version=sklearn.__version__,status='exploratory_post_hoc_selection_not_forward_proof',models={})
    for mode in ('JRA','NAR'):
        subset=data[data['mode']==mode];models={}
        for method in ('B1','B2','B3','B4','SELECTED'):
            cols=SETS[method+'_'+mode] if method in ('B3','B4','SELECTED') else SETS[method]
            fitted=LogisticRegression(C=.12,max_iter=1000,solver='lbfgs').fit(subset[cols].fillna(0),subset.top3.astype(int))
            models[method]=dict(version=VERSION+'_'+mode+'_'+method,features=cols,coefficients=fitted.coef_[0].tolist(),intercept=float(fitted.intercept_[0]),training_races=int(subset.race_id.nunique()),training_horses=len(subset),coefficient_status='提供研究の固定C=.12でオフライン学習・以後凍結')
        artifact['models'][mode]=models
    artifact['artifact_sha256']=digest(artifact)
    dest=Path(args.output)
    if dest.exists():raise SystemExit('既存モデルの上書き禁止：別出力先を指定してください')
    dest.write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
