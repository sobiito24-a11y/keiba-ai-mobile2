"""Read-only prediction table projection. Never scores, ranks or assigns marks."""
from html import escape
import math
import re
import unicodedata
from .jra_display_mark import jra_display_mark_from_row
from .nar_ability_rank import canonical_nar_ability_rank

NAR_COLUMNS = ['純能力順位', '最終印', '✔︎注目度', '純能力', '馬番 / 馬名', '年齢',
               '騎手（継続 / 乗り替わり）', '騎手成績', '脚質', '想定位置', '距離', 'コース', '★', '☆', 'コメント']
JRA_COLUMNS = ['JRA順位', 'JRAスコア', '最終印', '馬番 / 馬名', '年齢',
               '騎手（継続 / 乗り替わり）', '騎手成績', '脚質', 'netkeiba推定', '展開', '調教', '距離', 'コース', '★', '☆', '厩舎コメント']

def text(value):
    if value is None: return ''
    s=str(value).strip()
    return '' if s.lower() in ('', 'none', 'nan', '<na>', 'nat') else s

def pick(row, *keys):
    for key in keys:
        value=row.get(key)
        if text(value): return value
    return None

def number(value):
    if isinstance(value, bool):return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):return None

def fmt(value, decimal=False):
    v=number(value)
    return (f'{v:.1f}' if decimal else f'{v:g}') if v is not None else text(value) or '—'

def horse_key(row):
    v=pick(row,'number','馬番','馬','horse_no')
    n=number(v)
    return str(int(n)) if n is not None and n.is_integer() else text(v)

def recent_condition_stars(row, race_info):
    """Only explicitly labelled last three starts; no 4th-start or max-index fallback."""
    venue=text(pick(race_info,'racecourse','venue','track'))
    distance=number(race_info.get('distance'))
    runs=row.get('_past_runs')
    if not venue or distance is None or not isinstance(runs,list):return {'★':'—','☆':'—'}
    same=[];away=[]
    order={'前走':0,'2走前':1,'3走前':2}
    valid=[r for r in runs if isinstance(r,dict) and r.get('label') in order]
    for run in sorted(valid,key=lambda r:order[r['label']]):
        course=text(pick(run,'racecourse','venue','track','previous_track'))
        value=number(run.get('value'))
        if not course or value is None or number(run.get('distance'))!=distance:continue
        if course==venue:same.append(value)
        else:away.append(f'{course}{distance:g} {fmt(value)}')
    return {'★':'★'+fmt(max(same)) if same else '—', '☆':'☆ '+ ' / '.join(away) if away else '—'}

def jockey_place_text(row):
    """Read an explicit saved place percentage; never infer from wins or starts."""
    raw=pick(row,'jockey_course_top3_rate','_jockey_course_place_rate','jockey_course_place_rate','騎手コース複勝率','jockey_place_rate','騎手複勝率')
    rate=number(text(raw).replace('％','%').replace('%',''))
    if rate is None:
        for key in ('jockey_course_stats_market','騎手コース成績','jockey_course_stats','jockey_display_market','騎手詳細'):
            saved=unicodedata.normalize('NFKC',text(row.get(key)))
            explicit=re.search(r'(?:複勝率|複)\s*(\d+(?:\.\d+)?)\s*%',saved)
            triple=re.search(r'\d+(?:\.\d+)?%\s*[-/]\s*\d+(?:\.\d+)?%\s*[-/]\s*(\d+(?:\.\d+)?)%',saved)
            match=explicit or triple
            if match:
                rate=number(match[1]);break
    return f'複勝率 {rate:g}%' if rate is not None and 0<=rate<=100 else '複勝率 —'

def recommended_cards_html(horses):
    """Render the supplied, already-selected horses without choosing new candidates."""
    cards=[]
    for horse in horses:
        title=' '.join(text(horse.get(k)) for k in ('mark','number','name') if text(horse.get(k)))
        lines=[text(horse.get('role')),*horse.get('lines',[])]
        cards.append('<article class="recommended-horse" style="min-width:0;border:1px solid #dbe1eb;border-radius:8px;padding:8px;font-size:12px;line-height:1.5;overflow-wrap:anywhere;">'
                     +'<b style="font-size:13px;">'+escape(title)+'</b><div>'+'<br>'.join(escape(text(s)) for s in lines if text(s))+'</div></article>')
    return '<div class="recommended-horses" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0;">'+''.join(cards)+'</div>'

def age_text(row):
    value=unicodedata.normalize('NFKC',text(pick(row,'馬年齢','年齢','性齢','馬齢','age','sex_age')))
    match=re.fullmatch(r'(?:牡|牝|セ|セン|騸)?\s*(\d{1,2})(?:歳)?',value)
    return match[1] if match else '—'

def jockey_text(row):
    name=text(pick(row,'騎手','jockey','jockey_market'))
    detail=text(row.get('騎手詳細'))
    status=text(pick(row,'jockey_change_market','jockey_change'))
    if '継続' in detail or status=='継続':status='継続'
    elif any(s in detail for s in ['乗替','乗り替わり']) or status in ('乗替','乗り替わり'):status='乗替'
    else:status='—'
    if not name and detail:name=detail.split('【',1)[0]
    # Some saved names already carry the same explicit change annotation.
    tag=re.search(r'[（(](継|継続|替|乗替)[）)]$',name)
    if tag:
        if status=='—':status='継続' if tag[1] in ('継','継続') else '乗替'
        name=name[:tag.start()]
    return f'{name}（{status}）' if name else '—'

def prediction_table_records(rows, index_rows, race_info, race_mode, *, marks=None, rescue=()):
    """rows are already enriched by the existing display pipeline; marks are supplied unchanged."""
    index={horse_key(h):h for h in index_rows}
    rescued={str(h['number']):h for h in rescue}
    records=[]
    for row in rows:
        key=horse_key(row);saved=index.get(key,{})
        h=dict(saved);h.update(row)
        # Index provenance always prefers the matching saved overall row.
        idx=saved if saved else row
        stars=recent_condition_stars(idx,race_info)
        label=' '.join(x for x in [key,text(pick(h,'name','馬名'))] if x)
        style=text(pick(h,'脚質表示','running_style_display','脚質','running_style','style','running_style_market'))
        style={'逃げ':'逃','先行':'先','差し':'差','追込':'追'}.get(style,style) or '—'
        common={'馬番 / 馬名':label,'年齢':age_text(h),'騎手（継続 / 乗り替わり）':jockey_text(h),
                '騎手成績':jockey_place_text(h),
                '脚質':style,'距離':fmt(pick(idx,'距離指数','distance_index')),'コース':fmt(pick(idx,'コース指数','course_index')),**stars}
        final=(marks or {}).get(key)
        if race_mode=='jra':
            path=text(pick(h,'netkeiba_position_path','_netkeiba_position_path','position_path_market','_estimated_position_path'))
            if 'top=' in path or 'left=' in path:path=''
            corner=number(pick(h,'netkeiba_corner4_rank','_netkeiba_corner4_rank'))
            if corner is not None:
                path+=(' / ' if path else '')+f'4角{corner:g}番手'
            record={'JRA順位':fmt(pick(h,'jra_top5_rank','v1_final_rank')),'JRAスコア':fmt(h.get('jra_top5_score'),True),
                    '最終印':(final if final is not None else jra_display_mark_from_row(row)) or '—',**common,
                    'netkeiba推定':path or text(pick(h,'netkeiba_corner4_position','position_corner4_label_market')) or '—',
                    '展開':text(pick(h,'v1_pace_eval','shadow_pace_eval','pace_mark_market')) or '—',
                    '調教':text(pick(h,'jra_training_grade','training_grade','調教評価','training_market')) or '—',
                    '厩舎コメント':text(pick(h,'stable_comment_market','厩舎コメント','stable_comment')) or '—'}
            columns=JRA_COLUMNS
        else:
            warning=text(h.get('nar_warning_candidate')).lower() not in ('','false','0','—')
            attention='✔︎ 条件' if key in rescued else '✔︎' if warning or text(final).replace('\ufe0e','') in ('✓','✔') else '—'
            comment=text(pick(h,'表示コメント','display_comment','一言コメント','コメント','評価／検討材料','評価/検討材料')) or '—'
            if key in rescued:comment=rescued[key]['nar_condition_rescue_reason'] + (' / '+comment if comment!='—' else '')
            record={'純能力順位':fmt(canonical_nar_ability_rank(row)), '最終印':final or '—','✔︎注目度':attention,
                    '純能力':fmt(pick(h,'nar_pure_ability_score','market_ability_score','ability_value','saved_ability_value'),True),**common,
                    '想定位置':text(pick(h,'estimated_position_label','position_path_market','推定位置','想定位置')) or '—', 'コメント':comment}
            columns=NAR_COLUMNS
        records.append({k:record[k] for k in columns})
    return records

def prediction_table_html(records, race_mode):
    columns=JRA_COLUMNS if race_mode=='jra' else NAR_COLUMNS
    parts=['<div class="prediction-table-scroll" role="region" aria-label="詳細予想表" tabindex="0" style="max-width:100%;overflow-x:auto;">',
           '<table class="prediction-detail-table" style="border-collapse:collapse;width:max-content;font-size:12px;line-height:1.35;">',
           '<thead><tr>'+''.join('<th style="padding:4px 6px;white-space:nowrap;">'+escape(k)+'</th>' for k in columns)+'</tr></thead><tbody>']
    for row in records:
        parts.append('<tr>')
        for key in columns:
            value=text(row[key]);width=230 if key in ('コメント','厩舎コメント','☆') else 180 if key in ('馬番 / 馬名','★','騎手成績') else 100
            shown=value
            if len(value)>32:
                shown='<details><summary style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+escape(value[:28])+'…</summary><div style="white-space:normal;">'+escape(value)+'</div></details>'
            else:shown='<span style="white-space:nowrap;">'+escape(value)+'</span>'
            parts.append(f'<td title="{escape(value,quote=True)}" style="min-width:{width}px;max-width:{width}px;padding:4px 6px;vertical-align:top;overflow-wrap:anywhere;border-top:1px solid #dbe1eb;">{shown}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)
