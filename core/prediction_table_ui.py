"""Read-only prediction table projection. Never changes prediction scores, ranks or marks."""
from html import escape
import math
import re
import unicodedata
from .jra_display_mark import jra_display_mark_from_row
from .jra_win_probability import annotate_jra_win_probabilities, probability_text, JRA_WIN_PROB_LABEL
from .nar_ability_rank import canonical_nar_ability_rank
from .position_signals import corner4_rank, nar_position_reference
from .condition_support import matching_recent_runs, annotate_condition_support, condition_support_text, condition_support_html

NAR_COLUMNS = ['純能力順位', '最終印', '✔︎注目度', '純能力', '馬番 / 馬名', '年齢',
               '騎手（継続 / 乗り替わり）', '騎手成績', '斤量', '脚質', 'netkeiba想定', '距離', 'コース', '★', '☆', 'コメント']
JRA_COLUMNS = ['JRA順位', 'JRAスコア', JRA_WIN_PROB_LABEL, '最終印', '馬番 / 馬名', '年齢',
               '騎手（継続 / 乗り替わり）', '騎手成績', '斤量', '脚質', 'netkeiba想定', '展開', '調教', '距離', 'コース', '★', '☆', '厩舎コメント']

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

def sex_age_text(row):
    for key in ('性齢', 'sex_age', '馬年齢', '年齢', '馬齢', 'age'):
        value=unicodedata.normalize('NFKC',text(row.get(key)))
        if re.fullmatch(r'(牡|牝|セ|セン|騸)\s*\d{1,2}(歳)?',value):
            return value
    age=age_text(row)
    if age!='—':return age+'歳'
    for key in ('年齢','age','馬年齢','馬齢'):
        value=number(row.get(key))
        if value is not None and value.is_integer() and 0<value<30:return f'{int(value)}歳'
    return '—'

def load_weight_text(row):
    weight=number(pick(row,'_display_current_load_weight','_current_load_weight','斤量','weight'))
    change=number(pick(row,'weight_change_market','_display_load_weight_change','_load_weight_change','斤量増減','weight_change'))
    detail=unicodedata.normalize('NFKC',text(pick(row,'斤量詳細','weight_detail')))
    if weight is None:
        match=re.search(r'(\d+(?:\.\d+)?)\s*kg',detail,re.I)
        weight=number(match[1]) if match else None
    if change is None:
        match=re.search(r'[（(]\s*([+\-±]\d+(?:\.\d+)?)\s*(?:kg)?\s*[)）]',detail,re.I)
        if match:change=number(match[1].replace('±',''))
    if weight is None:return '—'
    suffix=('（±0）' if change==0 else f'（{change:+.1f}）') if change is not None else ''
    return f'{weight:.1f}kg'+suffix

def netkeiba_position_text(row):
    path=text(pick(row,'netkeiba_position_path','_netkeiba_position_path','position_path_market','_estimated_position_path'))
    if 'top=' in path or 'left=' in path:path=''
    if path:path=re.sub(r'\s*→\s*',' → ',path)
    rank=corner4_rank(row)
    if rank is not None:return path+(' / ' if path else '')+f'4角{rank}番手'
    return path or '—'

def position_display_text(row, mode):
    value=netkeiba_position_text(row)
    if mode=='nar':
        rate=nar_position_reference(row)['nar_corner4_reference_win_rate']
        if rate is not None:value+=f' / 4角参考勝率 {rate:.1f}%'
    return value

def display_index_rows(rows, index_rows=(), race_info=None, race_mode=""):
    """Copy-only whole-field competition ranks. Never passed to rescue/scoring."""
    saved={horse_key(h):h for h in index_rows}
    out=[]
    for row in rows:
        h=dict(row);idx=saved.get(horse_key(row),{})
        for key,alias in [('distance_index','距離指数'),('course_index','コース指数')]:
            value=number(pick(idx,alias,key))
            if value is None:value=number(pick(row,alias,key))
            h['_display_'+key]=value
        out.append(h)
    for key in ('distance_index','course_index'):
        values=[h['_display_'+key] for h in out if h['_display_'+key] is not None]
        for h in out:
            value=h['_display_'+key]
            h[key+'_rank']=1+sum(x>value for x in values) if value is not None else None
    sources=[saved.get(horse_key(h),h) for h in rows]
    out = annotate_condition_support(out, sources, race_info or {}, race_mode)
    return annotate_jra_win_probabilities(out) if race_mode == "jra" else out

def index_cell_text(row,key):
    value=row.get('_display_'+key)
    rank=row.get(key+'_rank')
    return f'{fmt(value)} / {int(rank)}位' if rank is not None and value is not None else '—'

def index_badges_html(row):
    parts=[]
    for key,label in [('distance_index','距離指数'),('course_index','コース指数'),('star_index','★'),('away_same_distance_index','☆')]:
        rank=row.get(key+'_rank');value=row.get(key+'_value') if key in ('star_index','away_same_distance_index') else row.get('_display_'+key)
        background={1:'#e1edf9',2:'#edf3f9',3:'#f4f7fa'}.get(rank,'#f7f7f7')
        parts.append(f'<div class="index-badge" style="min-width:0;text-align:center;background:{background};border:1px solid #dbe1eb;border-radius:5px;padding:4px;">'
          +f'<div style="font-size:11px;">{label}</div><b style="font-size:17px;">{escape(fmt(value))}</b>'
          +f'<div style="font-size:11px;">{str(int(rank))+"位" if rank is not None else "—"}</div></div>')
    return '<div class="index-badges" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin:5px 0;">'+''.join(parts)+'</div>'

def supplementary_card_html(row,mode):
    lines=[sex_age_text(row)+'　'+load_weight_text(row),'netkeiba想定：'+netkeiba_position_text(row)]
    if mode == 'jra':
        lines.insert(0, JRA_WIN_PROB_LABEL + ' ' + probability_text(row))
    if mode=='nar':
        rate=nar_position_reference(row)['nar_corner4_reference_win_rate']
        if rate is not None:lines.append(f'4角参考勝率 {rate:.1f}%（71Rバックテスト参考）')
    elif number(row.get('jra_position_bonus')) is not None:
        lines.append(f'位置bonus {number(row["jra_position_bonus"]):+.1f}')
    return '<div class="horse-position-detail" style="font-size:12px;">'+'<br>'.join(escape(s) for s in lines)+index_badges_html(row)+condition_support_html(row,mode)+'</div>'

def recent_condition_stars(row, race_info):
    """Only explicitly labelled last three starts; no 4th-start or max-index fallback."""
    same,away=matching_recent_runs(row,race_info)
    return {'★':'★'+fmt(max(r['value'] for r in same)) if same else '—',
            '☆':'☆ '+ ' / '.join(f"{r['venue']}{r['distance']:g} {fmt(r['value'])}" for r in away) if away else '—'}


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
                     +'<b style="font-size:13px;">'+escape(title)+'</b><div>'+'<br>'.join(escape(text(s)) for s in lines if text(s))+'</div>'+horse.get('badges_html','')+'<div>'+escape(text(horse.get('conditions')) or '')+'</div>'+horse.get('support_html','')+'</article>')
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
    for row in display_index_rows(rows, index_rows, race_info, race_mode):
        key=horse_key(row);saved=index.get(key,{})
        h=dict(saved);h.update(row)
        # Index provenance always prefers the matching saved overall row.
        idx=saved if saved else row
        stars=recent_condition_stars(idx,race_info)
        if row.get('star_index_rank') is not None:
            stars['★']+=f" / {row['star_index_rank']}位"
        if row.get('away_same_distance_index_rank') is not None:
            stars['☆']=f"☆{fmt(row['away_same_distance_index_value'])} / {row['away_same_distance_index_rank']}位（{stars['☆']}）"
        label=' '.join(x for x in [key,text(pick(h,'name','馬名'))] if x)
        style=text(pick(h,'脚質表示','running_style_display','脚質','running_style','style','running_style_market'))
        style={'逃げ':'逃','先行':'先','差し':'差','追込':'追'}.get(style,style) or '—'
        common={'馬番 / 馬名':label,'年齢':age_text(h),'騎手（継続 / 乗り替わり）':jockey_text(h),
                '騎手成績':jockey_place_text(h),'斤量':load_weight_text(h),
                '脚質':style,'距離':index_cell_text(row,'distance_index'),'コース':index_cell_text(row,'course_index'),**stars}
        final=(marks or {}).get(key)
        if race_mode=='jra':
            record={'JRA順位':fmt(pick(h,'jra_top5_rank','v1_final_rank')),'JRAスコア':fmt(h.get('jra_top5_score'),True),
                    JRA_WIN_PROB_LABEL:probability_text(row),
                    '最終印':(final if final is not None else jra_display_mark_from_row(row)) or '—',**common,
                    'netkeiba想定':position_display_text(h,race_mode),
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
                    'netkeiba想定':position_display_text(h,race_mode), 'コメント':comment}
            columns=NAR_COLUMNS
        records.append({k:record[k] for k in columns})
    return records

def prediction_table_html(records, race_mode):
    columns=JRA_COLUMNS if race_mode=='jra' else NAR_COLUMNS
    columns=['馬番 / 馬名']+[k for k in columns if k!='馬番 / 馬名']
    sticky='position:sticky;left:0;background:#fff;z-index:2;box-shadow:1px 0 #dbe1eb;'
    parts=['<div class="prediction-table-scroll" role="region" aria-label="詳細予想表" tabindex="0" style="max-width:100%;overflow-x:auto;">',
           '<table class="prediction-detail-table" style="border-collapse:collapse;width:max-content;font-size:12px;line-height:1.35;">',
           '<thead><tr>'+''.join('<th style="padding:4px 6px;white-space:nowrap;'+(sticky.replace('z-index:2','z-index:3').replace('#fff','#f4f6f8') if k=='馬番 / 馬名' else '')+'">'+escape(k)+'</th>' for k in columns)+'</tr></thead><tbody>']
    for row in records:
        parts.append('<tr>')
        for key in columns:
            value=text(row[key]);width=230 if key in ('コメント','厩舎コメント','☆') else 180 if key in ('馬番 / 馬名','★','騎手成績') else 100
            shown=value
            if len(value)>32:
                shown='<details><summary style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+escape(value[:28])+'…</summary><div style="white-space:normal;">'+escape(value)+'</div></details>'
            else:shown='<span style="white-space:nowrap;">'+escape(value)+'</span>'
            if key in ('距離','コース'):
                rank=re.search(r'/ (\d+)位',value)
                level=int(rank[1]) if rank else None
                color={1:'#e1edf9',2:'#edf3f9',3:'#f4f7fa'}.get(level,'transparent')
                shown=f'<span class="index-cell" style="white-space:nowrap;background:{color};padding:1px 3px;border-radius:3px;">'+escape(value)+'</span>'
            if key=='馬番 / 馬名':
                width=150
                shown='<span style="display:block;width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+escape(value)+'</span>'
            cell_sticky=sticky if key=='馬番 / 馬名' else ''
            parts.append(f'<td title="{escape(value,quote=True)}" style="{cell_sticky}min-width:{width}px;max-width:{width}px;padding:4px 6px;vertical-align:top;overflow-wrap:anywhere;border-top:1px solid #dbe1eb;">{shown}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)
