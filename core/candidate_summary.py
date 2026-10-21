"""Presentation of existing dated race facts; never used to change model A."""
from datetime import date, timedelta

def interval_label(profile, mode):
    days=profile.get('rest_days')
    if days is None or days<=0:return '間隔不明'
    if mode=='nar' and days<=13:return f'{days}日（短期連戦）'
    runs=profile.get('runs') or []
    try: previous=date.fromisoformat(runs[0]['date'].replace('/','-'))
    except (ValueError,IndexError,KeyError,TypeError):return '間隔不明'
    current=previous+timedelta(days=days)
    weeks=((current-timedelta(days=current.weekday()))-(previous-timedelta(days=previous.weekday()))).days//7
    if weeks<=0:return f'{days}日（同週出走）'
    if weeks==1:return '連闘'
    if days<=35:return f'中{weeks-1}週'
    if 40<=days<=50:return '約1ヶ月半'
    if 165<=days<=195:return '約半年'
    return f'約{days/30.4375:.0f}ヶ月'

def distance_label(profile):
    state=((profile.get('condition_facts') or {}).get('conditions',{}).get('distance') or {}).get('state','missing')
    return '同距離 '+{'placed':'3着内','started':'経験あり','absent':'履歴なし','missing':'不明'}[state]

def summary(h):
    p=h.get('profile') or {};star=p.get('stability_stars')
    labels=[h.get('jockey','—'),h.get('style','不明'), '近走 '+('★'*star+'☆'*(5-star) if star else '―')]
    if h.get('mode')=='jra':labels.append('調教 '+(h.get('training') or '―'))
    return labels+[distance_label(p),interval_label(p,h.get('mode'))]
