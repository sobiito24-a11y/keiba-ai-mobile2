"""Optional comparison panel; reads immutable research records only."""
import json,os,sqlite3
from pathlib import Path
from html import escape
from .new_ai_research import digest,num

def displayed_score_matches(value,exact):
    # UI formats the saved score to one decimal; compare using that same precision.
    n=num(value)
    return n is not None and exact is not None and abs(n-exact)<=0.051

def formal_rank_matches(h,saved):
    shown=num(h.get('rank'));rank=saved.get('formal_rank')
    if shown==rank:return True
    # Existing NAR UI deliberately hides ranks outside formal Top5.
    return h.get('mode')=='nar' and shown is None and rank is not None and rank>5 and h.get('formal_member') is False

def panel(view,race_key,portable=None):
 records=[]
 if portable is not None:
  records=[(json.dumps(portable,ensure_ascii=False),digest(portable))]
 else:
  path=Path(os.environ.get('KEIBA_RESEARCH_PREDICTIONS',str(Path(__file__).resolve().parents[1]/'research'/'predictions.sqlite')))
  if not path.is_file():return '<p>研究予想が未取得です。研究JSONと元.keibaを読み込んでください。</p>'
  c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
  try:records=c.execute('SELECT payload,payload_hash FROM new_ai_frozen WHERE race_id=? ORDER BY saved_at DESC',(str(race_key),)).fetchall()
  finally:c.close()
 if not records:return '<p>このレースの研究予想がありません。</p>'
 payload=None
 for raw,hashvalue in records:
  f=json.loads(raw)
  if digest(f)!=hashvalue:continue
  aa=f['models']['A']['rows'];by={str(h['no']):h for h in aa}
  if len(by)==len(view) and all(str(h['no']) in by and h['name']==by[str(h['no'])]['name'] and formal_rank_matches(h,by[str(h['no'])]) and num(h.get('corner'))==by[str(h['no'])]['corner'] and (h['mode']=='nar' or displayed_score_matches(h['score'],by[str(h['no'])]['formal_score'])) for h in view):payload=f;break
 if payload is None:return '<p>保存研究予想と現在の正式値が一致しません。研究後処理を再実行してください。以前の固定予想は上書きしません。</p>'
 e=lambda x:escape(str(x))
 html='<style>.top-horses:has(.research-panel){display:block;height:auto;max-height:650px;overflow:auto}.research-panel{width:100%;min-width:0}.research-panel details{display:block;margin:10px 0;padding:8px;border:1px solid #36465e}.research-panel pre{white-space:pre-wrap;overflow-wrap:anywhere}.research-panel summary{cursor:pointer}</style><div class="research-panel"><p>研究点は勝率ではありません。正式印・Top5へ反映しません。</p><p>'+e(payload['time_status'])+' / '+e(payload['version'])+'</p>'
 html+='<p>'+('JRA：保存正式実数点へ補正' if payload['authority']=='JRA' else 'NAR：正式順位は比較基準。研究点は保存純能力から算出する別尺度')+' / 保存 '+e(payload['saved_at'])+'</p>'
 for model,data in payload['models'].items():
  if model=='A':continue
  html+='<details '+('open' if model in ('F1','NAR_P_F1') else '')+'><summary>'+e(model)+'</summary>'
  if not data['complete']:html+='<p>比較不可：全頭分の基準点・必要統計が揃っていません。欠損を0点で代用しません。</p>'
  ordered=sorted(data['rows'],key=lambda r:r['research_rank'] or 999)
  html+='<p>研究上位5頭：'+e(' / '.join(str(r['no'])+' '+r['name']+'［正式'+str(r['formal_rank'])+'位→研究'+str(r['research_rank'])+'位・'+str(round(r['score'],3))+'点］'+(' ★浮上' if r['new_top5'] else '') for r in ordered[:5]) if data['complete'] else '未算出')+'</p>'
  for r in ordered:
   change=r['rank_change'];movement='未算出' if change is None else '維持' if change==0 else ('上昇 ' if change>0 else '下降 ')+str(abs(change))
   html+='<details><summary>'+e(str(r['no'])+' '+r['name'])+' 正式'+e(r['formal_rank'])+'位 → 研究'+e(r['research_rank'])+'位 / '+e(movement)+(' ★正式Top5外から浮上' if r['new_top5'] else '')+'</summary>'
   html+='<p>正式点 '+e(r['formal_score'])+' / 研究点 '+e(r['score'])+'</p>'
   html+='<p>加点：'+e({k:v for k,v in r['contributions'].items() if v is not None and v>0})+' / 減点：'+e({k:v for k,v in r['contributions'].items() if v is not None and v<0})+'</p>'
   html+='<p>未取得・未確認：'+e(r['missing'])+' / '+e(payload['time_status'])+'</p><pre>'+e(json.dumps({'母数と根拠':r['evidence'],'参照のみ・加点なし':r['reference'],'純能力':r['ability'],'4角':r['corner']},ensure_ascii=False,indent=2))+'</pre></details>'
  html+='</details>'
 return html+'</div>'
