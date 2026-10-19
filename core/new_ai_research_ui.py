"""Optional comparison panel; reads immutable research records only."""
import json
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
 layout='<style>.top-horses:has(.research-panel){display:block!important;min-width:0}.research-panel{width:100%;min-width:0;overflow-wrap:anywhere;white-space:normal}</style>'
 # Resolve data before rendering, using the original archive hash. No race-only DB fallback.
 if portable is None:
  return layout+'<div class="research-panel"><p>研究予想が未取得です。元ファイルと一致する研究結果がありません。研究後処理で作成した研究データ付きZIPを開いてください。手動復旧は詳細設定から行えます。</p></div>'
 payload=portable
 try:
  from .new_ai_research import VERSION,CONFIG
  if payload['race_id']!=str(race_key) or payload['version']!=VERSION or payload['config_sha256']!=digest(CONFIG):raise ValueError('identity')
  by={str(h['no']):h for h in payload['models']['A']['rows']}
  matches=len(by)==len(view) and all(str(h['no']) in by and h['name']==by[str(h['no'])]['name'] and formal_rank_matches(h,by[str(h['no'])]) and num(h.get('corner'))==by[str(h['no'])]['corner'] and (h['mode']=='nar' or displayed_score_matches(h['score'],by[str(h['no'])]['formal_score'])) for h in view)
  if not matches:raise ValueError('view mismatch')
 except (KeyError,TypeError,ValueError):
  return layout+'<div class="research-panel"><p>研究結果と表示レース・モデル版・正式値が一致しません。研究後処理を再実行してください。固定予想は上書きしません。</p></div>'
 e=lambda x:escape(str(x))
 def value(x):return '未取得' if x is None else f'{x:g}' if isinstance(x,(int,float)) else e(x)
 def movement(r):
  d=r.get('rank_change')
  return '未算出' if d is None else '維持' if d==0 else ('↑ 上昇 ' if d>0 else '↓ 下降 ')+value(abs(d))
 def reasons(r):
  labels={'jockey':'騎手','style':'脚質','corner':'4角'}
  points=' / '.join(labels.get(k,k)+' '+('補正不適用' if v is None else f'{v:+.3f}') for k,v in r['contributions'].items())
  evidence=[]
  for kind,st in r['evidence'].items():
   evidence.append(labels.get(kind,kind)+'：母数 '+value(st.get('n'))+'、3着内 '+value(st.get('top3'))+'、状態 '+str(st.get('status'))+'、期間 '+str(st.get('period_raw') or '未確認'))
  return '<p>'+e(points or '追加補正なし')+'</p>'+''.join('<p>'+e(x)+'</p>' for x in evidence)+'<p>未取得・未確認：'+e(' / '.join(r['missing']) or '項目欠損なし（時点確認は別）')+'</p><details><summary>根拠・既存材料の詳細</summary><pre>'+e(json.dumps({'根拠':r['evidence'],'参照のみ・加点なし':r['reference'],'純能力':r['ability'],'4角':r['corner']},ensure_ascii=False,indent=2))+'</pre></details>'
 models=[(k,v) for k,v in payload['models'].items() if k!='A']
 desired='F1' if payload['authority']=='JRA' else 'NAR_P_F1'
 selected=next((k for k,v in models if k==desired and v['complete']),next((k for k,v in models if v['complete']),models[0][0]))
 css='.top-horses:has(.research-panel){display:block!important;height:auto;max-height:none;overflow:visible;min-width:0}.research-panel{width:100%;min-width:0;max-width:100%;overflow-wrap:anywhere}.research-panel *{box-sizing:border-box}.research-panel p{white-space:normal}.research-controls{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.research-controls label{padding:10px;border:1px solid #53617a;border-radius:8px;cursor:pointer}.research-choice{position:absolute;opacity:0;width:1px;height:1px}.research-model{display:none;width:100%;min-width:0}.research-top5{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.research-card{padding:12px;border:1px solid #53617a;border-radius:10px;background:#142136;white-space:normal}.research-panel details{display:block;margin:10px 0;padding:10px;border:1px solid #36465e}.research-panel summary{cursor:pointer;white-space:normal;overflow-wrap:anywhere}.research-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.research-rise{color:#ffd26b}.research-panel .research-badge{display:inline-block;padding:4px 7px;background:#463b20;color:#ffdc86;border-radius:5px}.research-panel h4{margin:6px 0 12px}@media(max-width:600px){.research-top5{grid-template-columns:1fr}.research-panel{font-size:14px;line-height:1.7}.research-controls label{flex:1 0 70px;text-align:center}.research-card{width:100%}}'
 for i,(k,data) in enumerate(models):
  css+=f'#research-choice-{i}:checked ~ .research-model-{i}{{display:block}}#research-choice-{i}:checked ~ .research-controls label[for="research-choice-{i}"]{{background:#574a2e;color:#ffe199}}#research-choice-{i}:focus-visible ~ .research-controls label[for="research-choice-{i}"]{{outline:2px solid white}}'
 out='<style>'+css+'</style><div class="research-panel"><h3>新AI総合評価（研究）</h3><p>研究点は勝率ではありません。正式印・Top5・従来✓は変更しません。</p><p>'+e(payload['time_status'])+'</p><p>'+('JRA：保存正式実数点＋固定補正' if payload['authority']=='JRA' else 'NAR：保存純能力基準の参考評価。正式順位とは別尺度')+'</p><details><summary>モデル版・保存情報</summary><p>'+e(payload['version'])+' / '+e(payload['saved_at'])+'</p><p>元データSHA256 '+e(payload['keiba_sha256'])+'</p></details>'
 # Native radios work in both desktop and iPhone, without injected event handlers.
 for i,(k,data) in enumerate(models):out+=f'<input class="research-choice" type="radio" name="research-model" id="research-choice-{i}"'+(' checked' if k==selected else '')+'>'
 out+='<div class="research-controls" role="group" aria-label="研究モデル切替">'
 for i,(k,data) in enumerate(models):out+=f'<label for="research-choice-{i}">'+e(k.replace('NAR_P_','').replace('NAR_Pure','純能力'))+('（未計算）' if not data['complete'] else '')+'</label>'
 out+='</div>'
 for i,(k,data) in enumerate(models):
  out+=f'<section class="research-model research-model-{i}"><h4>'+e(k)+'</h4>'
  rows=sorted(data['rows'],key=lambda r:r['research_rank'] or 999)
  if data['complete']:
   out+='<h4>研究Top5</h4><div class="research-top5">'
   for r in rows[:5]:
    out+='<article class="research-card"><strong>研究'+value(r['research_rank'])+'位　'+e(r['no'])+' '+e(r['name'])+'</strong><p>正式'+value(r['formal_rank'])+'位 → 研究'+value(r['research_rank'])+'位</p><p>研究点 '+value(round(r['score'],3))+' ／ '+movement(r)+'</p>'+('<span class="research-badge">正式Top5外から浮上</span>' if r['new_top5'] else '')+'</article>'
   out+='</div><p>上昇馬：'+e(' / '.join(str(r['no'])+' '+r['name'] for r in rows if (r['rank_change'] or 0)>0) or 'なし')+'</p><p>下降馬：'+e(' / '.join(str(r['no'])+' '+r['name'] for r in rows if (r['rank_change'] or 0)<0) or 'なし')+'</p>'
  else:out+='<p>この方式は未計算：全頭分の基準点・必要統計が揃っていません。順位を推測せず、欠損を0点で代用しません。下の全頭一覧で不足理由を確認できます。</p>'
  out+='<h4>全頭順位・根拠</h4>'
  for r in rows:
   out+='<details><summary>'+e(r['no'])+' '+e(r['name'])+'｜正式'+value(r['formal_rank'])+' → 研究'+value(r['research_rank'])+'｜'+movement(r)+(' ★浮上' if r['new_top5'] else '')+'</summary><p>正式点 '+value(r['formal_score'])+' ／ 研究点 '+value(r['score'])+'</p>'+reasons(r)+'</details>'
  out+='</section>'
 return out+'</div>'
