"""Paper-only ticket decisions and append-only settlement. No prediction writes."""
from copy import deepcopy
from datetime import datetime,timezone
from html import escape
import hashlib,json,math
VERSION='paper_betting_v1_20261016'
KINDS=('win','place','wide','quinella')
LABELS=dict(win='単勝',place='複勝',wide='ワイド',quinella='馬連')
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def num(v):
 try:
  n=float(str(v).removesuffix('位'));return n if math.isfinite(n) else None
 except (ValueError,TypeError):return None
def facts(h,mode):
 ev=h.get('candidate_evidence') or {};audit=ev.get('audit') or {};days=(audit.get('rest') or {}).get('days')
 plus=list(ev.get('plus') or []);minus=list(ev.get('minus') or [])
 if mode=='nar' and days is not None and days>=36:minus.append('休養36日以上（探索仮説・一律除外なし）')
 if mode=='jra' and days is not None and days>=180:minus.append('180日以上休養')
 if mode=='jra' and days is not None and days>=70 and h.get('training') in ('C','D'):minus.append('70日以上＋調教C/D')
 if num(h.get('rank')) and num(h.get('ability_rank')) and abs(num(h['rank'])-num(h['ability_rank']))>=3:minus.append('正式順位と純能力順位の差3以上')
 return dict(plus=list(dict.fromkeys(plus)),minus=list(dict.fromkeys(minus)),days=days)
def candidates_jra(horses):
 return [h for h in horses if num(h.get('rank'))==1 and num(h.get('ability_rank'))==1],legacy_value(horses)
def candidates_nar(horses):
 return [h for h in horses if h.get('formal_member') is True and num(h.get('rank')) in (1,2) and num(h.get('ability_rank')) in (1,2)],legacy_value(horses)
def legacy_value(horses):
 priced=[(h,num(h.get('odds'))) for h in horses]
 if any(v is None or v<1 for _,v in priced):return []
 found=[]
 for h,v in priced:
  popularity=1+sum(other<v for _,other in priced);a=num(h.get('ability_rank'));r=num(h.get('rank'))
  if h.get('formal_member') is True and r in (2,3,4,5) and a in (1,2,3,4) and 8<=v<=35 and popularity>=4:
   found.append((-(popularity-a),r,num(h['no']) or 999,h))
 return [h for *_,h in sorted(found,key=lambda x:x[:3])[:2]]
def build(horses,mode,identity,observation=None):
 source=deepcopy(horses);strong,value=(candidates_jra(source) if mode=='jra' else candidates_nar(source))
 def candidate(h,kind):
  f=facts(h,mode);return dict(h,assessment=f,selection_reason=('正式1位と純能力1位が一致' if mode=='jra' else '正式・純能力とも2位以内') if kind=='strong' else '旧比較条件：正式2〜5位・能力1〜4位・単勝8〜35倍・人気4位以下。利益優位性未確認')
 strong=[candidate(h,'strong') for h in strong[:2]];value=[candidate(h,'value') for h in value[:2]]
 # Independent partner screening from the full formal set, never fixed to rank1.
 partners=[]
 for h in source:
  f=facts(h,mode)
  if h.get('formal_member') is True and num(h.get('ability_rank')) in (1,2,3) and f['plus'] and not f['minus']:
   partners.append(candidate(h,'strong'))
 partners.sort(key=lambda h:(num(h.get('ability_rank')) or 999,num(h.get('rank')) or 999,num(h['no']) or 999))
 tickets=[];selected=strong+value
 for kind in KINDS:
  choices=[]
  for h in selected:
   f=h['assessment'];a=num(h.get('ability_rank'))
   if not f['plus']:continue
   if kind=='win' and a not in (1,2):continue
   if kind=='place' and len(source)<5:continue
   if kind in ('wide','quinella'):
    partner=next((p for p in partners if p['no']!=h['no']),None)
    if not partner:continue
    if kind=='quinella' and (a not in (1,2) or num(partner.get('ability_rank')) not in (1,2) or f['minus']):continue
    ns=sorted([int(h['no']),int(partner['no'])]);reason=h['selection_reason']+'／相手：純能力上位・好走根拠あり・取得済み注意なし'
   else:partner=None;ns=[int(h['no'])];reason=h['selection_reason']
   if any(c['horses']==ns for c in choices):continue
   price=next((p for p in (observation or {}).get('prices',[]) if p['kind']==kind and sorted(p['horses'])==ns),None)
   choices.append(dict(horses=ns,stake=100,reason=reason,partner=partner,price=price,status='要確認',warnings=f['minus']+(['実オッズ未取得'] if not price else []),relative_payout_score=math.sqrt(float(h['odds'])*float(partner['odds'])) if partner and num(h.get('odds')) and num(partner.get('odds')) else None))
  tickets.append(dict(kind=kind,status='要確認' if choices else '見送り',choices=choices[:2],reason='未校正の紙上候補。価格鮮度・注意材料を確認' if choices else '券種に必要な本人・相手の根拠が不足'))
 return dict(version=VERSION,race_id=identity['race_id'],mode=mode,input_hash=digest(dict(horses=source,identity=identity)),strong=strong,value=value,classification='A' if strong else 'B' if value else 'C',tickets=tickets,odds=deepcopy(observation),unvalidated=True)
def freeze(decision,before_result=False):
 r=deepcopy(decision);r.update(fixed_at=datetime.now(timezone.utc).isoformat(),user_declared_before_result=bool(before_result),prospective_eligible=False,persistence='download_required')
 r['record_hash']=digest(r);return r
def verify(record):
 value=deepcopy(record);expected=value.pop('record_hash',None)
 if expected!=digest(value):raise ValueError('判断記録のハッシュが一致しません')
 return record
def settle(record,results):
 verify(record)
 if str(results.get('race_id'))!=str(record['race_id']):raise ValueError('レースID不一致')
 outcomes=[]
 for t in record['tickets']:
  for c in t['choices']:
   matches=[r for r in results.get('tickets',[]) if r.get('kind')==t['kind'] and sorted(r.get('horses',[]))==c['horses']]
   r=matches[0] if len(matches)==1 else None
   status=r.get('status') if r else 'unknown'
   payout=num(r.get('payout_per_100')) if r else None
   if status not in ('hit','miss','refund') or (status=='hit' and (payout is None or payout<0)):status='unknown'
   returned=c['stake'] if status=='refund' else 0 if status=='miss' else payout*c['stake']/100 if status=='hit' else None
   outcomes.append(dict(kind=t['kind'],horses=c['horses'],stake=c['stake'],status=status,returned=returned))
 known=[r for r in outcomes if r['returned'] is not None];cost=sum(r['stake'] for r in known);returns=sum(r['returned'] for r in known)
 return dict(record_hash=record['record_hash'],race_id=record['race_id'],settled_at=datetime.now(timezone.utc).isoformat(),outcomes=outcomes,unknown=len(outcomes)-len(known),cost=cost,returns=returns,roi=returns/cost*100 if cost else None,source=results.get('source'),note='未取得は0円扱いしない。元判断は変更しない')
def html(decision):
 e=lambda v:escape(str(v));parts=['<details style="padding:12px;background:#102239;border:1px solid #355273;border-radius:10px;margin:12px 0"><summary>馬券判断（検証版）</summary><p>紙上検証・未校正。購入推奨や利益保証ではありません。全候補は要確認です。</p>']
 for key,label in [('strong','強軸候補'),('value','妙味候補')]:
  parts.append('<h3>'+label+'</h3>')
  if not decision[key]:parts.append('<p>該当なし・見送り</p>')
  for h in decision[key]:
   f=h['assessment'];parts.append('<p><b>'+e(h['mark']+' '+h['no']+' '+h['name'])+'</b> 正式'+e(h['rank'])+'位／能力'+e(h['ability_rank'])+'位 · 単勝'+e(h['odds'])+'／複勝'+e(h.get('place_odds','—'))+'<br>選出：'+e(h['selection_reason'])+'<br>＋'+e('／'.join(f['plus']) or '根拠不足')+'<br>−'+e('／'.join(f['minus']) or '取得済み注意なし・欠損は要確認')+'<br>4角 '+e(h.get('corner'))+'／調教 '+e(h.get('training'))+'／休養 '+e(h.get('rest'))+'／斤量 '+e(h.get('weight'))+'</p>')
 for t in decision['tickets']:
  parts.append('<h4>'+LABELS[t['kind']]+'：'+t['status']+'</h4><p>'+e(t['reason'])+'</p>')
  for c in t['choices']:
   parts.append('<p>'+e('－'.join(map(str,c['horses'])))+'（紙上100円） '+e(c['reason'])+'<br>'+e('／'.join(c['warnings']))+'</p>')
   if c['relative_payout_score'] is not None:parts.append('<small>配当感の相対指標 '+e(round(c['relative_payout_score'],2))+'：実オッズ・期待値ではありません</small>')
 parts.append('<p>判断記録の固定・ダウンロード・結果照合は全頭表の下の「馬券判断の記録・結果照合」で行います。</p></details>');return ''.join(parts)
