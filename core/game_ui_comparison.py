"""Read-only metric comparisons; never written to formal predictions."""
from .prediction_table_ui import number,fmt

TABS=[('final','① 最終印候補'),('corner','② 展開・4角'),('ability','③ 純能力'),
      ('course','④ コース'),('distance','⑤ 距離'),('training','⑥ 調教・状態'),
      ('star','⑦ ★指数'),('away','⑧ ☆指数'),('average','⑨ 3走平均'),('materials','⑩ 今回＋／−'),('changes','⑪ 斤量／騎手'),('research','⑫ 新AI総合（研究）')]
NOTICE='※該当する実績・有効な指数がある馬のみを対象に抽出しています。未取得馬は対象外です。'


def comparisons(view,mode):
    def rank(h):return number(h['rank']) if number(h['rank']) is not None else float('inf')
    def tie(h):return (rank(h),number(h['no']) or float('inf'))
    groups=[]
    for key,label in TABS:
        if key=='research':
            groups.append(dict(key=key,label=label,kind='research',cards=[],eligible=len(view),total=len(view),note='正式評価には反映しない研究表示'))
            continue
        if mode=='nar' and key=='training':
            cards=[dict(index=i,value=(h.get('profile') or {}).get('state','判定不可'),rank='指数推移・参考') for i,h in enumerate(view[:5])]
            groups.append(dict(key=key,label=label,kind='metric',cards=cards,eligible=len(view),total=len(view),note='調教による加点はしません。指数推移の説明は各馬詳細へ。'))
            continue
        if key in ('materials','changes'):
            from .game_ui_information import information
            groups.append(information(view,key,label))
            continue
        if key=='final':
            from .game_ui_candidate_evidence import candidates
            groups.append(candidates(view,label))
            continue
        elif key=='corner':
            pool=[h for h in view if number(h['corner']) is not None and number(h['corner'])>0]
            pool.sort(key=lambda h:(h['corner'],*tie(h)))
        elif key=='ability':
            pool=[h for h in view if number(h['ability']) is not None and number(h['ability_rank']) is not None and number(h['ability_rank'])>0]
            pool.sort(key=lambda h:(number(h['ability_rank']),*tie(h)))
        elif key=='training':
            pool=[h for h in view if h['training'] in ('A','B','C','D')]
            pool.sort(key=lambda h:('ABCD'.index(h['training']),rank(h),-(number(h['score']) or 0),number(h['no']) or 999))
        else:
            pool=[h for h in view if h[key]['value'] is not None]
            pool.sort(key=lambda h:(-h[key]['value'],*tie(h)))
        cards=[]
        for h in pool[:5]:
            if key=='final':value=h['score'];r=h['rank']+'位'
            elif key=='ability':value=h['ability'];r=h['ability_rank']+'位'
            elif key=='corner':value=str(h['corner'])+'番手';r='4角想定'
            elif key=='training':value=h['training'];r='正式'+h['rank']+'位' if h['rank']!='—' else '正式順位 —'
            else:value=fmt(h[key]['value']);r=str(h[key]['rank'])+'位' if h[key]['rank'] is not None else '順位 —'
            cards.append({'index':next(i for i,x in enumerate(view) if x['no']==h['no']), 'value':value,'rank':r})
        note=NOTICE if key in ('course','distance','star','away','average') else ''
        if key=='away':note+=' ☆は既存定義の同距離・別会場の直近3走実績です。'
        if key=='final' and len(pool)>5:note='正式候補は'+str(len(pool))+'頭。ここでは正式順の先頭5頭を表示し、全候補は下の一覧に保持しています。'
        groups.append({'key':key,'label':label,'eligible':len(pool),'total':len(view),'cards':cards,'note':note})
    return groups
