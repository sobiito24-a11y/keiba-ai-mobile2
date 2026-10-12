"""Provider contract and virtual decisions. No scraping, subscriptions or betting APIs."""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from copy import deepcopy
from .independent_ai import number,digest,JST

def timestamp(value):
    try:
        t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t if t.tzinfo else None
    except (ValueError,TypeError):return None

class UnconfiguredProvider:
    available=False
    reason='正規データ提供元が未接続です。購入期待値確認待ち。'
    def fetch(self,race_id):raise ValueError(self.reason)

class AuthorizedJsonProvider:
    """Admin-provisioned HTTPS bridge only after contractual display/transfer approval."""
    available=True
    def __init__(self,config):
        self.config=dict(config)
        url=urlparse(self.config.get('endpoint',''))
        if not (self.config.get('enabled') is True and self.config.get('rights_confirmed') is True
                and self.config.get('authorization_reference') and self.config.get('source')
                and url.scheme=='https' and url.hostname and not url.username and not url.password):
            raise ValueError('取得・転送・画面表示の許諾が確認されたHTTPS接続設定が必要です')
    def fetch(self,race_id):
        import requests
        headers={'Accept':'application/json'}
        if self.config.get('token'):headers['Authorization']='Bearer '+self.config['token']
        response=requests.get(self.config['endpoint'],params={'race_id':race_id},headers=headers,timeout=10,allow_redirects=False)
        if response.status_code!=200:raise ValueError('オッズ提供元から取得できませんでした')
        if len(response.content)>2_000_000:raise ValueError('オッズ応答サイズが不正です')
        data=response.json()
        if data.get('race_id')!=race_id or data.get('source')!=self.config['source']:raise ValueError('オッズのレース・提供元が一致しません')
        data=deepcopy(data);data['received_at']=datetime.now(JST).isoformat()
        data['authorization_reference']=self.config['authorization_reference']
        return data

def provider(config=None):
    if not config or not config.get('enabled'):return UnconfiguredProvider()
    return AuthorizedJsonProvider(config)

def evaluate_history(prediction,history,now=None):
    """Latest observation per ticket; never refresh an old price by merging uploads."""
    now=now or datetime.now(JST)
    out=evaluate(prediction,None,now);seen=set();rows=[];reasons=[]
    for q in reversed(history):
        value=evaluate(prediction,q,now);reasons.append(value['reason'])
        allowed=set()
        for price in q.get('prices',[]):
            key=(price.get('kind'),tuple(sorted(price.get('horses',[]))))
            if key not in seen:allowed.add(key)
            seen.add(key)
        # Cancellation affects earlier observations of the same horse, across all kinds.
        for n in q.get('withdrawn',[]):
            for old in history:
                for price in old.get('prices',[]):
                    if n in price['horses']:seen.add((price['kind'],tuple(sorted(price['horses']))))
        for row in value['price_evaluations']:
            if (row['kind'],tuple(row['horses'])) in allowed:
                rows.append(dict(row,observed_at=q.get('observed_at'),source=q.get('source')))
    out['price_evaluations']=rows;out['quote_history']=deepcopy(history)
    eligible=sorted([r for r in rows if r['conservative_gross_return']>1.1],key=lambda r:(-r['conservative_gross_return'],r['kind'],r['horses']))[:1]
    if eligible:
        out.update(status='virtual_candidate',reason='試験版の仮想購入候補。確率は未校正・利益優位性は未確認です。',candidates=[dict(eligible[0],virtual_stake_yen=100)],max_virtual_loss_yen=100)
    elif rows:out['reason']='見送り：価格下限とモデル間変動を考慮すると余裕が不足'
    elif reasons:out['reason']=reasons[0]
    return out

def evaluate(prediction,quote=None,now=None,max_age_seconds=120):
    now=now or datetime.now(JST)
    out=dict(version='virtual_purchase_v3_2',status='skip',reason='購入期待値確認待ち：オッズ未取得',
        proven_recommendation=False,candidates=[],price_evaluations=[],max_virtual_loss_yen=0,actual_purchase=False,
        prediction_hash=digest(prediction),evaluated_at=now.isoformat(),quote=deepcopy(quote))
    if not quote:return out
    if quote.get('price_status') in ('predicted_odds','timestamp_unknown'):
        return dict(out,reason='見送り：予想オッズまたは価格時刻不明の保存HTMLです。最新価格として扱いません')
    post=timestamp((prediction.get('input') or {}).get('post_time'));generated=timestamp(prediction.get('generated_at'))
    observed=timestamp(quote.get('observed_at'));received=timestamp(quote.get('received_at'))
    if quote.get('race_id')!=prediction.get('race_id') or not quote.get('source') or not quote.get('authorization_reference'):
        return dict(out,reason='レースID・提供元・利用許諾情報を確認できません')
    if not all((post,generated,observed,received)):
        return dict(out,reason='予測・発走・価格の時刻を確認できません')
    if not generated<post or now>=post or observed>=post or received>=post:
        return dict(out,reason='発走前の予測・価格として確認できません')
    if not observed<=received<=now or (now-observed).total_seconds()>max_age_seconds:
        return dict(out,reason='価格が古いか、取得時刻の整合性がありません')
    horses={h['horse_no']:h for h in prediction.get('horses',[])}
    from .independent_ai_html_odds import norm
    identities=quote.get('identities',{})
    pairs={tuple(sorted(p['horses'])):p for p in prediction.get('wide',[])}
    seen=set()
    for price in quote.get('prices',[]):
        kind=price.get('kind');ns=price.get('horses',[])
        if kind not in ('win','place','wide') or not isinstance(ns,list) or not all(isinstance(n,int) for n in ns):continue
        key=tuple(sorted(ns))
        if len(set(key))!=len(key) or len(key)!=(2 if kind=='wide' else 1) or (kind,key) in seen:continue
        if any(n not in horses or norm(identities.get(str(n),''))!=norm(horses[n]['name']) for n in key):continue
        if set(key).intersection(quote.get('withdrawn',[])):continue
        seen.add((kind,key));low=number(price.get('low'));high=number(price.get('high'))
        if low is None or high is None or not 1<=low<=high:continue
        if kind=='wide':
            h=pairs.get(key)
            if h is None:continue
            p=h['probability'];bound=h['range'][0]
        else:
            h=horses.get(key[0])
            if h is None:continue
            p=h[kind];bound=h[kind+'_range'][0]
        out['price_evaluations'].append(dict(kind=kind,horses=list(key),probability=p,probability_lower=bound,
            odds_low=low,odds_high=high,reference_gross_return=p*low,conservative_gross_return=bound*low,
            uncertainty='モデル間の変動幅であり保証下限ではない'))
    if not out['price_evaluations']:return dict(out,reason='完全な券種別価格がありません')
    # A displayed numerical EV is only a reference when calibration is unproven.
    eligible=[p for p in out['price_evaluations'] if p['conservative_gross_return']>1.1]
    if not eligible:return dict(out,reason='見送り：不確実性と価格下限を考慮すると余裕が不足')
    chosen=sorted(eligible,key=lambda p:(-p['conservative_gross_return'],p['kind'],p['horses']))[:1]
    return dict(out,status='virtual_candidate',reason='未校正モデルの仮想購入候補（実証済み推奨ではありません）。価格下限とモデル間変動を考慮した試験判断です',
        candidates=[dict(p,virtual_stake_yen=100) for p in chosen],max_virtual_loss_yen=100)
