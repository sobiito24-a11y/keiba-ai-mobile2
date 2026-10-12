"""Copy-only supplementary assessments. Never imported by scoring/mark selection.

Rules are exploratory explanations, not calibrated win probabilities. Raw saved
fields remain untouched; all generated values live in _supplementary_display.
"""
import math
import re
from html import escape
from .position_signals import corner4_rank
from .nar_ability_rank import canonical_nar_ability_rank

VERSION = 'supplementary_display_v1_20261012'
KEY = '_supplementary_display'


def text(v):
    return '' if v is None or str(v).strip().lower() in ('nan','none','<na>','—','未取得') else str(v).strip()


def first(row, *keys):
    return next((row[k] for k in keys if text(row.get(k))), None)


def number(v):
    if isinstance(v, bool): return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError): return None


def no(row):
    n = number(first(row, '馬番','number','horse_no','馬'))
    return str(int(n)) if n is not None else ''


def style(row):
    s = text(first(row,'netkeiba_old_style','netkeiba_running_style','脚質表示','running_style_display','脚質','running_style','style','running_style_market'))
    return {'逃げ':'逃','先行':'先','差し':'差','追込':'追','追い込み':'追'}.get(s,s)


def position(row):
    return text(first(row,'netkeiba_corner4_position','_estimated_position_corner4_label','position_corner4_label_market','corner4_position_label'))


def training(row):
    m = re.match(r'^([ABCD])(?:\b|\s|$)', text(first(row,'jra_training_grade','training_grade','調教評価','training_market')))
    return m[1] if m else ''


def rest(row):
    n = number(first(row,'_days_since_last','レース間隔日数','rest_days','_新聞前走間隔日数'))
    if n is None or n < 0 or not n.is_integer(): return None
    return int(n)


def rest_text(row):
    days = rest(row)
    if days is None: return 'データなし'
    if days < 30: return f'{days}日'
    # Calendar-independent approximation, explicitly labelled as approximate.
    half_months = int(days / 30.4375 * 2)
    months, half = divmod(half_months, 2)
    return f'{days}日（約{months}か月'+('半' if half else '')+'）'


# Explicit clause patterns, not sentiment word counts. Each matched quote is
# retained. A missing/truncated clause cannot establish a strong assessment.
POSITIVE = {
    '状態': r'仕上が(?:り(?:は|も|が)?(?:良好|万全|いい|良い)|りました|っている)|力を出せる(?:態勢|状態)|状態(?:は|も|が)?(?:良好|上向|いい|良い)|動き(?:は|も|が)?(?:良化|良い|いい)|調子(?:は|も|が)?(?:上向|いい|良い)',
    '条件適性': r'(?:距離|コース|条件|外回り|千四|千二|千六)(?:は|も|が)?(?:合う|向く|得意|好材料)|(?:距離|コース)適性(?:は|も)?(?:高い|ある)',
    '改善': r'(?:前走より|前回より|使って|叩いて).{0,12}(?:良化|良く|上向|良い)|(?:課題|敗因).{0,8}(?:解消|改善)',
}
NEGATIVE = r'もうひとつ|もう一つ|不安|物足り|良化途上|割引|重い|重かった|厳しい|まだ.{0,8}(?:不足|重)|(?:合わ|向か|良く|よく|仕上がって|上向いて)い?ない'
CONDITIONAL = r'次第|なら|れば|たら|かもしれ|どうか|未知|条件付き|はまれば|ハマれば'
NEGATION = r'(?:では|とは|も|と)?(?:言えない|いえない|思わない)|わけではない|ことはない|(?:良く|よく|合わ|向か|仕上がって|上向いて)い?ない|とは限らない'


def stable_assessment(value):
    raw = text(value)
    clauses = [s.strip() for s in re.split(r'[。！？\n]', raw) if s.strip()]
    positive, negative, conditional = [], [], []
    for clause in clauses:
        # Question headings must not become affirmative evidence.
        clean = re.sub(r'^[ＱQ]\s*[^〈<]*[〈<][^〉>]*[〉>]\s*', '', clause)
        # Do not turn explicit absence of worry into a negative signal.
        risk_text = re.sub(r'不安(?:は|も)?(?:ない|ありません)', '', clean)
        neg = bool(re.search(NEGATIVE, risk_text))
        cond = bool(re.search(CONDITIONAL, clean))
        if neg: negative.append(clean)
        if cond: conditional.append(clean)
        if re.search(NEGATION, clean): continue
        for domain, pattern in POSITIVE.items():
            for segment in re.split(r'が[、,]|が(?=状態|仕上|展開)|けれど|ただし|しかし|だが', clean):
                if re.search(pattern, segment) and not re.search(NEGATIVE+'|'+NEGATION, segment):
                    positive.append({'domain':domain,'quote':segment})
                    break
    domains = {p['domain'] for p in positive}
    truncated = '…' in raw or raw.endswith('...')
    grade = '◎' if len(domains)>=2 and not (negative or conditional or truncated) else '○' if positive else ''
    return dict(grade=grade,positive=positive,cautions=list(dict.fromkeys(negative)),conditions=list(dict.fromkeys(conditional)),truncated=truncated,trial=True)


def basic(row, mode):
    st = stable_assessment(first(row,'stable_comment_market','厩舎コメント','stable_comment')) if mode=='jra' else None
    return dict(version=VERSION,development='',development_reason='位置だけでは展開有利を判定しない',
                legacy_development=text(first(row,'v1_pace_eval','shadow_pace_eval','pace_mark_market')),
                rest_days=rest(row),rest_text=rest_text(row),training=training(row),stable=st,
                reference=False,reference_candidate=False,reference_reason='',check_reason='',
                price_note=('保存コメントの価格は取得時刻・種別を本表示では確認できず、収益性の根拠にしない' if re.search(r'配当|妙味|単勝.+倍', text(first(row,'一言コメント','コメント','表示コメント'))) else ''))


def annotate(rows, source_rows=(), mode='jra', race_info=None):
    """Whole-field context required. Never write to rows/sources/race_info."""
    sources = {no(h):h for h in source_rows}
    merged=[]
    for r in rows:
        h=dict(sources.get(no(r),{}));h.update(r)
        # A blank presentation field must not hide an explicit saved interval.
        if rest(h) is None and rest(sources.get(no(r),{})) is not None:
            h['_days_since_last']=rest(sources[no(r)])
        merged.append(h)
    context=list(sources.values()) if len(sources)>len(merged) else merged
    known=sum(style(h) in ('逃','先','差','追') for h in context)
    escapes=sum(style(h)=='逃' for h in context)
    forward=sum(style(h) in ('逃','先') for h in context)
    indexed={}
    for field,alias in [('distance','距離指数'),('course','コース指数')]:
        vals={no(h):number(first(h,alias,field+'_index','_display_'+field+'_index')) for h in context}
        indexed[field]={n:1+sum(x>v for x in vals.values() if x is not None) if v is not None else None for n,v in vals.items()}
    candidates=[]
    for i,h in enumerate(merged):
        a=basic(h,mode);h[KEY]=a
        dr=indexed['distance'].get(no(h));cr=indexed['course'].get(no(h))
        a.update(distance_rank=dr,course_rank=cr,style_known=known,field_count=len(context),escape_count=escapes,forward_count=forward)
        pace_values={text(first(x,'netkeiba_pace','_netkeiba_pace','provider_pace_market','predicted_pace')) for x in context}
        pace_values.discard('');pace_values.update([text((race_info or {}).get('netkeiba_pace'))] if (race_info or {}).get('netkeiba_pace') else [])
        pace=next(iter(pace_values)) if len(pace_values)==1 else ''
        a['pace']=pace
        if mode=='jra':
            pr=number(first(h,'jra_pure_ability_rank','pure_ability_rank','market_ability_rank'))
            support=(pr is not None and 1<=pr<=5) or any(x is not None and x<=3 for x in (dr,cr))
            complete=len(context)>0 and known==len(context)
            s=style(h);pos=position(h)
            route=''
            if complete and support and corner4_rank(h) is not None:
                if pace=='H' and escapes>=2 and forward>=3 and s in ('差','追') and pos in ('中団','後方'):
                    route='H想定・複数の逃げ脚質＋中団/後方想定の差し脚質・能力/適性上位。先行争いが生じる形なら浮上余地'
                elif pace=='S' and escapes==1 and forward<=2 and s in ('逃','先') and pos in ('先団','前方'):
                    route='S想定・逃げ先行脚質が少数＋前方想定・能力/適性上位。前が競らず運べる形なら利点'
            a['development']='◎' if route else ''
            a['development_reason']=route or ('脚質構成に欠損があり展開有利は未判定' if not complete else 'ペース・脚質構成・想定位置・能力適性の複合根拠不足（不利判定ではない）')
        else:
            pr=canonical_nar_ability_rank(h);group=h.get('pure_ability_top5_group');corner=corner4_rank(h)
            if group is True:a['check_reason']='正式候補内（追加✓の対象外）'
            elif group is not False:a['check_reason']='正式候補集合未取得のため追加✓対象を判定しない'
            elif pr is None:a['check_reason']='純能力順位未取得'
            elif pr>8:a['check_reason']=f'純能力{pr}位で現行追加✓の能力8位以内基準外。条件材料と印選出は別判定'
            elif corner is None:a['check_reason']='4角想定未取得'
            elif corner>6:a['check_reason']=f'4角{corner}番手で現行追加✓の6番手以内基準外'
            elif h.get('nar_check_selected') is True:a['check_reason']='現行追加✓の条件・頭数上限を通過'
            else:a['check_reason']='能力・位置条件内。表示は既存✓の優先順・頭数上限による選抜結果を使用'
            mark=text(first(h,'_display_nar_mark','nar_submark','nar_final_mark','最終印','ver3_final_mark','印'))
            unmarked=mark in ('','無印','-') and h.get('nar_check_selected') is not True
            improving=text(h.get('state_label_market'))=='持ち直し'
            history=bool(text(h.get('condition_reason_market'))) and '過去走あり' in text(h.get('condition_reason_market'))
            match=group is False and unmarked and pr is not None and pr>=9 and dr is not None and dr<=3 and cr is not None and cr<=3 and (improving or history)
            a['reference_candidate']=match
            if match:
                a['reference_reason']=f'距離指数{dr}位・コース指数{cr}位／'+('近況持ち直し' if improving else '同条件の過去走あり')+'。正式✓ではない未検証の参考注目'
                candidates.append((dr+cr,pr,i))
    for _,_,i in sorted(candidates)[:(1 if len(context)<=9 else 2)]:merged[i][KEY]['reference']=True
    return merged


def auxiliary_html(row, mode):
    a=row.get(KEY) or basic(row,mode)
    lines=[]
    if mode=='jra':
        lines.append('休養：'+a['rest_text'])
        if a['rest_days'] is not None and a['rest_days']>=70:
            lines.append(f"{a['rest_days']}日ぶり。"+('今回調教'+a['training']+'。' if a['training'] else '')+'間隔の長さによる実戦面の不確実性は残る')
        st=a['stable']
        if st and (st['grade'] or st['cautions']):
            lines.append('厩舎評価（試験）：'+(st['grade'] or '—'))
            lines += [p['domain']+'：'+p['quote'] for p in st['positive']]
            lines += ['経過・留意：'+x for x in st['cautions']]
            lines += ['条件付き：'+x for x in st['conditions']]
        lines.append('展開有利：'+a['development_reason'])
    else:
        if a['check_reason']:lines.append(a['check_reason'])
        if a['price_note']:lines.append(a['price_note'])
        if a['reference']:lines.append('参考注目：'+a['reference_reason'])
    return '<div class="supplementary-assessment" style="font-size:12px;line-height:1.5;overflow-wrap:anywhere;">'+'<br>'.join(escape(x) for x in lines)+'</div>'
