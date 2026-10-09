"""Read-only commentary facts. Historical ticket helpers are not used by commentary."""
from copy import deepcopy
from itertools import combinations
from html import escape
from .prediction_table_ui import horse_key, number, pick, text
from .condition_support import annotate_condition_support
from .nar_ability_rank import canonical_nar_ability_rank
from .jra_rank_display import official_jra_values

VERSION = "race_insight_explanation_v4_20261009"
# Input-only calibration, 2026-09-26/27. Median adjacent gaps at ability ranks 3..6.
# No finishes, payouts or probability fitting. Separate later-date evaluation required.
CLOSE_GAPS = {"jra": 1.2, "nar": 2.15}
GAP_CALIBRATION = {"dates": ["2026-09-26","2026-09-27"], "jra_flat_races":37,
                   "nar_races":54, "method":"median adjacent pure-score gaps at ranks 3..6"}

def valid_pick(row,*keys):
    return next((row[k] for k in keys if text(row.get(k)) not in ('','—','未取得','不明')),None)

def facts(result, display_rows, development):
    from .race_development import _rows
    source={horse_key(h):h for h in _rows(result)}
    indexed=[]
    for r in display_rows:
        h=dict(source.get(horse_key(r),{}))
        h.update({k:v for k,v in r.items() if text(v) not in ('','—','未取得','不明')})
        indexed.append(h)
    for key,alias in [('distance_index','距離指数'),('course_index','コース指数')]:
        values=[number(valid_pick(source.get(horse_key(h),h),alias,key)) for h in indexed]
        for h,v in zip(indexed,values):
            h[key+'_value']=v
            h[key+'_rank']=1+sum(x>v for x in values if x is not None) if v is not None else None
    indexed=annotate_condition_support(indexed,[source.get(horse_key(h),h) for h in indexed],result.race_info or {},result.race_mode)
    positions={h['horse_no']:h for h in development['horses']}
    shifts={h['horse_no']:h for h in development.get('development_shift_audit',{}).get('horses',[])}
    cal=(result.debug_info or {}).get('jra_win_probability_calibration' if result.race_mode=='jra' else 'nar_winprob_calibration',{})
    probabilities={horse_key(h):number(h.get(result.race_mode+'_win_probability')) for h in cal.get('horses',[])}
    out=[]
    for row in indexed:
        no=horse_key(row);p=positions.get(no,{})
        mode=result.race_mode
        if mode=='jra':
            from .jra_display_mark import jra_display_mark_from_row
            from .v1_logic import training_grade
            mark=jra_display_mark_from_row(row)
            rank,score=map(number,official_jra_values(row))
            pure=number(valid_pick(row,'jra_pure_ability_score','ver3_ability_core','_ver3_ability_core','market_ability_score'))
            pr=number(valid_pick(row,'jra_pure_ability_rank','pure_ability_rank','market_ability_rank','ability_rank'))
            member=rank is not None and rank<=5
            train=training_grade(row)
        else:
            from .nar_display_mark import display_mark
            mark=display_mark(row);rank=number(row.get('nar_final_rank'));score=None
            pure=number(valid_pick(row,'ver3_ability_core','_ver3_ability_core'))
            pr=canonical_nar_ability_rank(row);member=bool(row.get('pure_ability_top5_group'));train=''
        cond=[]
        for key,label in [('distance_index','距離'),('course_index','コース'),('star_index','★'),('away_same_distance_index','☆')]:
            v=number(row.get(key+'_value'));n=number(row.get(key+'_rank'))
            if v is not None and n is not None and n<=3:cond.append(f'{label}指数{v:g}（{int(n)}位）')
        f=dict(no=no,name=text(valid_pick(row,'馬名','name','horse_name')),mark=mark,formal_rank=rank,
               formal_score=score,member=member,pure=pure,pure_rank=pr,conditions=cond,
               condition_count=len(cond),style=p.get('running_style','不明'),group=p.get('corner4_group','unknown'),
               corner=p.get('corner4_rank'),pace=development['pace_prediction'],training=train,
               previous_training=text(valid_pick(row,'previous_training_grade','_previous_training_grade')),
               weight_change=number(valid_pick(row,'weight_change_market','_load_weight_change','斤量増減')),
               weight=number(valid_pick(row,'_current_load_weight','斤量')),
               rest_days=number(valid_pick(row,'_days_since_last','rest_days','layoff_days','_interval_days')),
               age=text(valid_pick(row,'性齢','sex_age','馬年齢','age')),
               jockey=text(valid_pick(row,'騎手','jockey_market')),
               jockey_change=text(valid_pick(row,'jockey_change_market','jockey_change_status')),
               probability=number(row.get(mode+'_win_probability')) if number(row.get(mode+'_win_probability')) is not None else probabilities.get(no),
               shift=shifts.get(no,{}).get('development_shift_shadow') is True,
               shift_reason=shifts.get(no,{}).get('development_shift_reason',''))
        f['pace_effect']=pace_effect(f)
        f['positive_domains']=(['condition'] if cond else [])+(['pace'] if f['pace_effect']=='plus' else [])
        f['risks']=[]
        if f['pace_effect']=='risk':f['risks'].append('H想定で前受けの消耗が懸念' if f['pace']=='H' else 'S想定で後ろから前を捕まえる必要')
        if mode=='jra' and train in ('C','D'):f['risks'].append('調教'+train+'で状態面は慎重に確認')
        if f['group']=='unknown':f['risks'].append('今回位置が不明で展開判断は保留')
        out.append(f)
    boundary=[h['pure'] for h in out if h['member'] and h['pure'] is not None]
    for h in out:
        h['gap_to_group']=max(0,min(boundary)-h['pure']) if boundary and h['pure'] is not None else None
        h['close_gap']=h['gap_to_group'] is not None and h['gap_to_group']<=CLOSE_GAPS[result.race_mode]
    return out

def pace_effect(h):
    pace,group,style,corner=h['pace'],h['group'],h['style'],h['corner']
    if pace=='S' and corner is not None and 1<=corner<=6:return 'plus'
    if pace=='S' and group in ('middle','back'):return 'risk'
    if pace=='H' and group=='front':return 'risk'
    if pace=='H' and group in ('middle','back') and style in ('差','追'):return 'plus'
    return 'unknown' if pace not in ('S','M','H') or group=='unknown' else 'neutral'

def label(h):
    return h['mark']+h['no']+h['name']

def mark_order(h):
    """Ordering for explanation only. Never assign/replace a mark."""
    order = {'◎': 0, '○': 1, '▲': 2, '✔︎': 3, '✔': 3, '△': 4, '✓': 5, '☆': 6}
    return (order.get(h['mark'], 7), h['formal_rank'] or 999, int(h['no']))


def has_mark(h):
    return str(h.get('mark', '')).strip().replace('\ufe0e', '').replace('\ufe0f', '') in ('◎', '○', '▲', '✔', '△', '✓', '☆', '注目', '注意馬')


def marked_roles(horses, extra):
    formal = sorted([h for h in horses if h['member'] and has_mark(h)], key=mark_order)
    centers = [h for h in formal if h['mark'] in ('◎', '○')][:2]
    if not centers:
        centers = formal[:1]  # Saved mark remains authoritative, not pure rank.
    # Include all remaining marked horses, including a sixth tied formal member.
    opponents = sorted([h for h in horses if has_mark(h) and h not in centers and h not in extra],
                       key=lambda h: (not h['member'], mark_order(h)))
    return centers, opponents


def ability_comparison(h, anchor):
    if h['pure'] is None:
        return '純能力が未取得で、上位馬との能力差は確認できない。'
    rank = f"（全頭{int(h['pure_rank'])}位）" if h['pure_rank'] else ''
    line = f"純能力は{h['pure']:g}{rank}。"
    if anchor and anchor['no'] != h['no'] and anchor['pure'] is not None:
        delta = h['pure'] - anchor['pure']
        if abs(delta) < 1e-9:
            line += label(anchor) + 'と同値で、今回は条件と運び方を比較したい。'
        elif delta > 0:
            line += label(anchor) + f'を{delta:.2f}上回り、能力面ではこの馬にも強みがある。'
        else:
            line += label(anchor) + f'を{-delta:.2f}下回る。'
            if h['pace_effect'] == 'plus':
                line += ('前で脚を残せる位置は利点だが、能力差のある相手に最後まで粘れるか。' if h['pace']=='S' else '差す流れは助けになる一方、前の消耗が小さければ能力差が課題として残る。')
            elif h['conditions']:
                line += '能力では及ばない分、得意条件で記録した指数を比較したい。'
            elif h['pace_effect'] == 'risk':
                line += '厳しい流れになれば能力差に加えて運び方も課題になるが、競り合いの有無を確認したい。'
    return line


def narrative_horses(horses):
    """Prose-only copies. Never feed this context into selection or audit facts."""
    forward = [h for h in horses if h['group'] == 'front']
    values = [h['pure'] for h in forward if h['pure'] is not None]
    complete = len(values) == len(forward) and len(values) >= 2
    context = dict(escape_count=sum(h['style'] == '逃' for h in horses),
                   unknown_styles=sum(h['style'] not in ('逃', '先', '差', '追') for h in horses),
                   front_max=max(values) if complete else None)
    return {h['no']: dict(h, narrative_context=context) for h in horses}


def position_sentence(h):
    position = {'front': '前方', 'middle': '中団', 'back': '後方'}.get(h['group'])
    if h['corner'] is None and not position:
        return '今回位置が不明のため、脚質だけで展開有利とは判断できない。'
    prefix = f"4角{h['corner']:g}番手" if h['corner'] is not None else position
    if h['pace_effect'] == 'plus':
        if h['pace'] == 'S':
            return prefix + '想定。前で落ち着いて運べれば位置を生かせるが、後続との能力差や仕掛け次第で、前残りとは決め切れない。'
        evidence = ('能力・適性の裏付けは未確認で、' if h['pure'] is None else
                    '能力差と条件指数を併せて見る必要があり、' if h['conditions'] else
                    '条件指数上位の裏付けは確認できず、')
        return prefix + '想定。前が競って消耗すれば差す余地はある。' + evidence + 'H想定だけで届くとは判断しない。'
    if h['pace_effect'] == 'risk':
        if h['pace'] != 'H':
            return prefix + '想定。Sペースで前が脚を残す場合は追い上げが課題だが、能力差と仕掛け次第で届く余地もある。'
        context = h.get('narrative_context', {})
        escapes = context.get('escape_count')
        line = prefix + 'の前方想定。'
        if escapes is None or context.get('unknown_styles'):
            line += '過去脚質に未確認の情報があり、先行争いの激しさは読み切れない。Hペース想定でも消耗は決め付けられない。'
        elif escapes >= 2:
            line += f'過去脚質で逃げに分類された馬が{escapes}頭おり、今回も前で競り合う形なら負担が増す。'
        else:
            line += 'Hペース想定でも、過去脚質の逃げ馬の少なさだけでは今回の競り合いや消耗は読み切れない。'
        if h['pure'] is not None and context.get('front_max') == h['pure']:
            line += '前方勢の中では純能力が最も高く、競らずに運べれば粘り込みも考えたい。'
        if h['conditions']:
            line += h['conditions'][0] + 'も支えになるが、道中の負担を補えるかは確認点。'
        elif h['pure'] is None:
            line += '能力・条件の裏付けが不足し、粘れるかの判断は保留。'
        else:
            line += '残れるかは前方勢との能力差と道中の負担次第。'
        return line
    if h['shift'] and h['pace'] in ('H', 'M'):
        return prefix + '想定。普段より控えて脚を溜められるかが鍵になる。'
    if h['pace'] not in ('S', 'M', 'H'):
        return prefix + '想定だが、ペース未取得のため有利不利は保留。'
    if h['group'] == 'back':
        return prefix + 'の後方想定。Mペースでは前の馬が簡単には止まらない可能性があり、追い上げるタイミングが重要。'
    if h['group'] == 'middle':
        return prefix + 'の中団想定。前を射程に入れたまま直線へ向けるかを見たい。'
    return prefix + '想定。前で運べる半面、後続に目標にされる形で脚を残せるか。'


def state_sentence(h, mode):
    parts = []
    if mode == 'jra':
        grade, previous = h['training'], h['previous_training']
        if grade in ('A', 'B', 'C', 'D'):
            if previous in ('A', 'B', 'C', 'D') and previous != grade:
                direction = '改善' if 'ABCD'.index(grade) < 'ABCD'.index(previous) else '低下'
                parts.append(f'調教は前走{previous}から{grade}へ{direction}。')
            else:
                parts.append('調教' + grade + ('で仕上がりの確認は慎重にしたい。' if grade in ('C', 'D') else 'も今回の状態を確認する材料。'))
        else:
            parts.append('調教評価が未取得で、状態面の裏付けは不足。')
        if h['rest_days'] is not None:
            parts.append(f"前走から{h['rest_days']:g}日。")
    if h['weight_change'] is not None and h['weight_change'] != 0:
        parts.append(f"斤量は前走比{h['weight_change']:+g}kg。" +
                     ('前走より重い斤量への対応が確認点。' if h['weight_change'] > 0 else '負担は軽くなるが、それだけで好走とは判断しない。'))
    if h['jockey'] and h['jockey_change']:
        change = h['jockey_change']
        if change in ('継続', '乗替'):
            parts.append('騎手は' + h['jockey'].replace('(替)', '') + 'の' + ('継続騎乗。' if change == '継続' else '乗り替わり。'))
    return ''.join(parts)


def leading_features(h):
    """Narrative facts only. Do not feed these into candidate selection."""
    features = ['純能力'] if h['pure_rank'] == 1 else []
    features += [c.split('指数', 1)[0] + ('指数' if not c.startswith(('★', '☆')) else '')
                 for c in h['conditions'] if '（1位）' in c]
    return features


def condition_sentence(h):
    firsts = [c for c in h['conditions'] if '（1位）' in c]
    if len(firsts) >= 2:
        return '、'.join(firsts) + 'と複数の条件指数で全頭1位。'
    if firsts:
        others = [c for c in h['conditions'] if c not in firsts]
        return firsts[0] + 'が強み。' + ('加えて' + '、'.join(others[:2]) + 'も記録。' if others else '')
    if any(c.startswith('★') for c in h['conditions']):
        return '、'.join(h['conditions'][:3]) + '。同会場・同距離の実績も比較材料になる。'
    return '、'.join(h['conditions'][:3]) + 'を記録。'


def secondary_note(h):
    parts = ['正式候補圏外の補助印。']
    if h['conditions']:
        parts.append(h['conditions'][0] + '。')
    if h['pace_effect'] == 'risk':
        parts.append(position_sentence(h))
    elif h['corner'] is not None:
        parts.append(f"4角{h['corner']:g}番手想定。")
    else:
        parts.append('4角順位は未取得。')
    return ''.join(parts)


def describe(h, mode, role, anchor=None):
    rank = h['formal_rank']
    line = label(h) + ('は' + ('JRA正式' if mode == 'jra' else 'NAR最終') + f'{int(rank)}位。' if rank is not None else '。')
    if role == 'opponent' and not h['member']:
        # Keep existing secondary marks visible without treating them as new recommendations.
        return line + secondary_note(h)
    line += ability_comparison(h, anchor)
    if h['conditions']:
        line += condition_sentence(h)
    elif role == 'additional':
        line += '条件指数上位の裏付けは確認できず、適性面には留保が必要。'
    if role == 'additional':
        if h['gap_to_group'] is not None:
            line += f"正式候補圏の下限とは{h['gap_to_group']:.2f}差。"
            if not h['close_gap']:
                line += '能力差は小さいと扱えず、位置取り変化だけで埋められるとは限らない。'
        if h['shift']:
            line += h['shift_reason'].rstrip('。') + 'という材料もある。'
        line += '条件が噛み合う場合の注目にとどめたい。'
    line += position_sentence(h)
    line += state_sentence(h, mode)
    return line


def tickets(numbers,axes=()):
    nums=sorted(set(numbers),key=int);axis=set(axes)
    if not axis.issubset(nums) or len(axis)>2:raise ValueError('invalid axes')
    return [list(c) for c in combinations(nums,3) if axis.issubset(c)]

def make_tickets(horses,centers,nav=None):
    if len(horses)<3:return dict(style='見送り',axes=[],combinations=[],reason='候補の根拠が揃わず3頭を組めない')
    if nav and nav.get('purchase_grade') in ('D','B'):
        return dict(style='見送り',axes=[],combinations=[],reason='既存購入ナビの見送り判断を優先' if nav.get('purchase_grade')=='D' else '既存購入ナビはワイド中心のため3連複案は保留')
    # Axis candidates require independent evidence. Do not use hidden axis Shadow.
    strong=[h for h in centers if h['pure_rank'] is not None and h['pure_rank']<=2 and
            h['conditions'] and h['pace_effect']=='plus' and not h['risks']]
    axes=[]
    if len(strong)==1:axes=[strong[0]['no']]
    elif len(strong)==2 and not nav:axes=[h['no'] for h in strong]
    # JRA nav allows only its existing axis; B/C guidance must not become a new fixed axis.
    if nav:
        existing=str((nav.get('axis_candidate') or {}).get('number',''))
        axes=[existing] if nav.get('purchase_grade')=='A' and existing in axes else []
    nums=[h['no'] for h in horses]
    combos=tickets(nums,axes)
    if nav and nav.get('purchase_grade')=='C' and len(combos)>10:
        return dict(style='見送り',axes=[],combinations=[],reason='既存ナビの少点数方針に対して候補が広く、3連複案は保留')
    return dict(style=('2頭軸' if len(axes)==2 else '1頭軸') if axes else 'BOX',axes=axes,combinations=combos,
                reason='能力・条件・展開が揃う中心を軸にする参考案' if axes else '中心を固定する根拠が揃わないためBOXで比較')

def section_html(sections):
    rendered = []
    for section in sections:
        rendered.append('<h4>【' + escape(section['title']) + '】</h4>')
        if section.get('groups'):
            for group in section['groups']:
                rendered.append('<h5 class="insight-subheading" style="font-size:13px;margin:10px 0 5px">■ ' + escape(group['title']) + '</h5>')
                rendered.extend('<p>' + escape(p) + '</p>' for p in group['paragraphs'])
        else:
            rendered.extend('<p>' + escape(p) + '</p>' for p in section['paragraphs'])
    return ''.join(rendered)
