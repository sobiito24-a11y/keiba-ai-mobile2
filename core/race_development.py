"""Read-only race explanation; no score, mark, probability or purchase producer."""
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import re

from .prediction_table_ui import horse_key, number, pick, text
from .position_signals import corner4_rank
from .nar_race_diagnostics import normalize_position_group
from .nar_ability_rank import canonical_nar_ability_rank

KEY = 'race_development_display'
VERSION = 'race_development_display_v5_natural_commentary'
STYLE_KEYS = ('netkeiba_old_style', 'netkeiba_running_style', '脚質表示',
              'running_style_display', '脚質', 'running_style', 'style', 'running_style_market')
POSITION_KEYS = ('netkeiba_corner4_position', '_estimated_position_corner4_label',
                 'position_corner4_label_market', 'corner4_position_label')
PACE_KEYS = ('netkeiba_pace', '_netkeiba_pace', 'predicted_pace', '予測ペース', 'pace')


def style_label(value):
    value = text(value)
    aliases = {'逃げ':'逃', '先行':'先', '差し':'差', '追込':'追', '追い込み':'追'}
    return aliases.get(value, value) if value in (*aliases, '逃', '先', '差', '追') else '不明'


def _source(row, keys):
    for key in keys:
        if text(row.get(key)):
            return row[key], key
    return None, None


def _rows(result):
    # Whole field, joined by horse number; no positional/index join.
    rows = {}
    for table in (result.overall_table, result.horse_evaluation):
        if table is None:
            continue
        for row in table.to_dict('records'):
            key = horse_key(row)
            if not key:
                continue
            target = rows.setdefault(key, {})
            target.update({k: v for k, v in row.items() if text(v)})
    # Read only frozen formal results, never run today's rank producer for old files.
    debug = result.debug_info or {}
    payload = debug.get('jra_formal_comparison_snapshot' if result.race_mode == 'jra' else 'nar_top5_corner_order') or {}
    for h in payload.get('rows', payload.get('horses', [])):
        key = horse_key(h)
        if key in rows:
            rows[key].update({k: h[k] for k in ('jra_top5_rank', 'jra_top5_score', 'nar_final_rank',
                                                'jra_final_mark', 'nar_final_mark', 'pure_ability_top5_group',
                                                'v1_final_mark', 'ver3_final_mark') if k in h})
    values = list(rows.values())
    if result.race_mode == 'nar' and values and all('pure_ability_top5_group' in r for r in values):
        from .nar_check_selection import select
        # Reuse current bounded selection on copies, never invent new checks.
        return select(values)
    return values


def newspaper_inputs(html, race_id, mode):
    """Only the newspaper's explicit historical style table / existing position parser."""
    from bs4 import BeautifulSoup
    from .course_materials import parse_netkeiba_course_materials
    parsed = parse_netkeiba_course_materials(html, expected_mode=mode)
    if not race_id or parsed.race_id != str(race_id) or (parsed.detected_mode and parsed.detected_mode != mode):
        return {}
    styles = {}
    soup = BeautifulSoup(html, 'html.parser')
    for row in soup.select('tr'):
        heading = row.find('th')
        label = style_label(heading.get_text(strip=True) if heading else '')
        if label == '不明':
            continue
        for node in row.select('.Kyaku_Type_Num'):
            no = node.get_text(strip=True)
            if no.isdigit():
                styles.setdefault(no, set()).add(label)
    return dict(styles={k: next(iter(v)) if len(v) == 1 else '不明' for k, v in styles.items()},
                pace=parsed.pace, positions=parsed.position_categories.get('corner4', {}),
                ranks=parsed.position_ranks.get('corner4', {}))


def build(result, html='', source_race_id=None):
    rows = _rows(result)
    info = result.race_info or {}
    race_id = info.get('race_id') or source_race_id
    extra = newspaper_inputs(html, race_id, result.race_mode) if html else {}
    horses = []
    pace_values = set()
    for source in [info, *rows]:
        raw, _ = _source(source, PACE_KEYS)
        if text(raw).upper() in ('S', 'M', 'H'):
            pace_values.add(text(raw).upper())
    if extra.get('pace') in ('S', 'M', 'H'):
        pace_values = {extra['pace']}
    pace = next(iter(pace_values)) if len(pace_values) == 1 else '不明'
    for row in rows:
        no = horse_key(row)
        raw_style, style_source = _source(row, STYLE_KEYS)
        style = style_label(raw_style)
        if no in extra.get('styles', {}):
            style, style_source = extra['styles'][no], 'newspaper.Kyaku_Type_Num'
        position, position_source = _source(row, POSITION_KEYS)
        if not position:
            path, path_source = _source(row, ('netkeiba_position_path', '_netkeiba_position_path', 'position_path_market', '_estimated_position_path'))
            if '→' in text(path):
                position, position_source = text(path).split('→')[-1].strip(), path_source
        rank = corner4_rank(row)
        numeric_no = int(no) if no.isdigit() else None
        if not position and numeric_no in extra.get('positions', {}):
            position, position_source = extra['positions'][numeric_no], 'newspaper.position_categories.corner4'
        if rank is None:
            rank = extra.get('ranks', {}).get(numeric_no)
        group = normalize_position_group(position)
        delta = ''
        if style in ('差', '追') and group == 'front':
            delta = 'いつもより前で運べる想定'
        elif style in ('逃', '先') and group == 'back':
            delta = '通常より後ろになる想定'
        pure_rank = canonical_nar_ability_rank(row) if result.race_mode == 'nar' else number(pick(row, 'jra_pure_ability_rank', 'ability_rank', 'market_ability_rank'))
        horses.append(dict(horse_no=no, horse_name=text(pick(row, '馬名', 'name', 'horse_name')),
            running_style=style, running_style_source=style_source,
            corner4_rank=rank, corner4_position=text(position) or None, corner4_group=group,
            corner4_source=position_source, position_difference=delta, pure_ability_rank=pure_rank,
            formal_rank=number(row.get('jra_top5_rank' if result.race_mode == 'jra' else 'nar_final_rank')),
            average_index=number(pick(row, '平均指数', 'average_index', '3走平均')),
            training_grade=text(pick(row, 'jra_training_grade', 'training_grade', '調教評価')) if result.race_mode == 'jra' else None,
            rest_days=number(pick(row, 'rest_days', 'layoff_days', 'interval_days', '_interval_days'))))
    styles = {s: sorted([h['horse_no'] for h in horses if h['running_style'] == s], key=lambda n:number(n) or float('inf')) for s in ('逃', '先', '差', '追', '不明')}
    groups = {g: [h['horse_no'] for h in sorted(horses, key=lambda h:(h['corner4_rank'] or float('inf'), number(h['horse_no']) or float('inf')))
                   if h['corner4_group'] == g] for g in ('front', 'middle', 'back', 'unknown')}
    def names(numbers):
        return '・'.join('⑳' if n == '20' else (chr(0x2460+int(n)-1) if n.isdigit() and 1 <= int(n) < 20 else n+'番') for n in numbers)
    points = []
    if styles['逃']:
        points.append(names(styles['逃'][:3]) + ('が脚質上の主導権候補。' if len(styles['逃']) == 1 else 'など逃げ脚質の馬が複数。'))
    if len(styles['先']) > 1:
        points.append(f"先行脚質は{len(styles['先'])}頭。今回の4角想定と併せて確認。")
    pace_sentence = {'H':'既存予測はH（速め）。前の馬の消耗次第では差し勢にも浮上余地がある。',
                     'M':'既存予測はM（標準）。4角の位置取りと能力評価を併せて確認したい。',
                     'S':'既存予測はS（遅め）。前で運ぶ馬の残り目に注意したい。'}.get(pace, '予測ペースは未取得または保存値が不一致のため不明。')
    points.append(pace_sentence)
    data = dict(model_version=VERSION, race_mode=result.race_mode, race_id=race_id,
        generated_at=datetime.now(timezone.utc).isoformat(), source='existing_prediction_inputs_only',
        pace_prediction=pace, running_style_groups=styles, corner4_groups=groups,
        development_summary=points,
        horses=horses, horse_count=len(horses))
    return compose_commentary(data, rows, result.race_mode)


def compose_commentary(data, rows, mode):
    """Presentation-only projection. Eligibility comes from existing formal output."""
    data = deepcopy(data)
    source = {horse_key(r): r for r in rows}
    formal, checks = [], []
    for h in data['horses']:
        row = source.get(h['horse_no'], {})
        rank = number(pick(row, '_display_jra_top5_rank', 'jra_top5_rank')) if mode == 'jra' else number(row.get('nar_final_rank'))
        if mode == 'jra':
            from .jra_display_mark import jra_display_mark_from_row
            mark = jra_display_mark_from_row(row)
            member = rank is not None and 1 <= rank <= 5
            check = mark == '✓'
        else:
            from .nar_display_mark import formal_mark
            mark = formal_mark(row)
            member = bool(row.get('pure_ability_top5_group')) and bool(mark)
            check = row.get('nar_check_selected') is True
        support = not member and (check or mark in ('✔︎', '✔'))
        h.update(formal_rank=rank, formal_mark=mark, formal_candidate=member, selected_check=check and not member,
                 development_support_mark=(mark if mark in ('✔︎', '✔') else '✓') if support else '')
        if member:
            formal.append(h)
        elif support:
            checks.append(h)
    formal.sort(key=lambda h:(h['formal_rank'] or float('inf'), number(h['horse_no']) or float('inf')))
    # Final marks are authoritative, even if the existing role layer differs
    # from score rank. Do not invent ◎○▲ from a new ordering here.
    main = sorted([h for h in data['horses'] if h['formal_mark'] in ('◎','○','▲')],
                  key=lambda h:('◎','○','▲').index(h['formal_mark']))
    def name(h, mark=False):
        return (h['formal_mark'] if mark else '')+h['horse_no']+h['horse_name']
    pace = data['pace_prediction']
    def position(h):
        return (f"4角{h['corner4_rank']}番手" if h['corner4_rank'] is not None else '4角順位未取得') + ('・'+h['corner4_position'] if h['corner4_position'] else '')
    def impact(h):
        group, rank, style = h['corner4_group'], h['corner4_rank'], h['running_style']
        if pace == '不明' or (rank is None and group == 'unknown'):
            return '材料不足', 'ペースまたは今回位置が未取得のため展開評価は保留'
        if pace == 'S':
            if rank is not None and rank <= 6:
                return 'プラス', 'S想定で前が残る形なら前残りの恩恵候補'
            if rank is not None and rank > 6 or group in ('middle','back'):
                return '注意', 'S想定では前を捕まえる必要があり、前方勢と同じ残り目評価にはしない'
            return '中立', 'S想定の前方カテゴリだが、具体的な4角順位がなく前残り候補の判定は保留'
        if pace == 'H':
            if group == 'front':
                return '注意', 'H想定で前の消耗を受けやすく、粘り込みには注意'
            if group in ('middle','back') and style in ('差','追'):
                return 'プラス', 'H想定で前が消耗すれば、中団・後方から差す形に浮上余地'
            return '中立', 'H想定では追走と末脚の使い方が鍵。保存された脚質では差し浮上を積極評価しない'
        return '中立', 'M想定では極端な前残り・差し有利を置かず、この位置からの運びを確認'
    intro = '本線は'+ '、'.join(name(h,True) for h in main)+'。' if main else '本線は◎○▲の正式印が未取得のため特定できません。'
    missing = [m for m in ('◎','○','▲') if not any(h['formal_mark']==m for h in main)]
    if main and missing:
        intro += '今回の正式表示に'+ '・'.join(missing)+'はありません。'
    def numbers(horses):
        return '・'.join(h['horse_no'] for h in horses)
    # Group the main horses by the same reading instead of repeating templates.
    readings = {}
    for h in main:
        label, reason = impact(h)
        readings.setdefault((label, reason), []).append(h)
    phrases = []
    for (label, reason), horses in readings.items():
        subject = numbers(horses)
        if label == 'プラス':
            phrase = 'は前目で運べるため、前残りの恩恵を受けやすい' if pace == 'S' else 'は中団・後方から差す形で浮上余地がある'
        elif label == '注意':
            phrase = 'は中団以降から前を捕まえる必要があり、差し届かずには注意' if pace == 'S' else 'は前で消耗する可能性があり、粘り込みが鍵'
        elif label == '材料不足':
            phrase = 'は位置またはペースの情報が足りず、展開との相性は保留'
        else:
            phrase = 'は極端な展開の有利不利を置かず、位置取りと末脚を確認したい'
        phrases.append(subject+phrase+'。')
    intro += ('予測ペースは不明。' if pace == '不明' else pace+'ペース想定。') + ''.join(phrases)
    plus = []
    # Outside marked support first. Escape horses already have a pacemaker
    # explanation: prioritize other marked runners to avoid repeating that role.
    eligible = sorted(checks,key=lambda h:(h['running_style']=='逃',h['corner4_rank'] or float('inf'),number(h['horse_no']) or float('inf'))) + [h for h in formal if h['formal_mark'] not in ('◎','○','▲')]
    for h in eligible:
        if impact(h)[0] == 'プラス' and len(plus) < 2:
            plus.append(dict(horse_no=h['horse_no'], horse_name=h['horse_name'],
                reason=('既存'+h['development_support_mark']+'・正式Top5圏外。' if h['development_support_mark'] else '正式Top5候補。')+
                       f"脚質：{h['running_style']}、{position(h)}。"+impact(h)[1]+'。'))
    selected_plus = {h['horse_no'] for h in plus}
    extras = [h for h in eligible if h['horse_no'] in selected_plus]
    extra_lines = []
    for outside in (True, False):
        group = [h for h in extras if bool(h['development_support_mark']) == outside]
        if not group:
            continue
        labels = '、'.join((h['development_support_mark'] if outside else h['formal_mark'])+name(h) for h in group)
        ranks = sorted({h['corner4_rank'] for h in group if h['corner4_rank'] is not None})
        rank_text = ''
        if ranks:
            # Only compress consecutive ranks; do not imply intermediate positions.
            rank_text = str(ranks[0]) if len(ranks)==1 else (str(ranks[0])+'〜'+str(ranks[-1]) if ranks[-1]-ranks[0]==len(ranks)-1 else '・'.join(map(str,ranks)))
            rank_text = 'が4角'+rank_text+'番手想定。'
        else:
            rank_text = 'は中団・後方から運ぶ想定。'
        extra_lines.append(('Top5外では' if outside else '本線以外では')+labels+rank_text+
            ('前残りの形なら相手候補として警戒。' if pace=='S' else '前が消耗する形なら相手候補として警戒。'))
    leaders = sorted([h for h in data['horses'] if h['running_style']=='逃'], key=lambda h:number(h['horse_no']) or float('inf'))
    if len(leaders)>1:
        key_sentence = '逃げ候補は'+numbers(leaders)+'。どちらが主導権を取るかで前の残り方が変わりそう。' if len(leaders)==2 else '逃げ候補は'+numbers(leaders)+'。主導権争いが前の残り方を左右しそう。'
    elif leaders:
        key_sentence = '展開の鍵は'+numbers(leaders)+'。単独で逃げられるか、先行勢との競り合いになるかがポイント。'
    else:
        key_sentence = '逃げ候補は確認できず、先行勢のどの馬が主導権を取るかが鍵。'
    caution, changes = [], {}
    for h in sorted(data['horses'],key=lambda h:number(h['horse_no']) or float('inf')):
        if not h['position_difference']:
            continue
        forward = h['running_style'] in ('差','追') and h['corner4_group']=='front'
        if forward:
            reason = '普段'+{'差':'差し','追':'追込'}[h['running_style']]+'だが今回は前目の想定。'
            reason += {'S':'S想定なら前で運べる点はプラスになり得る。','H':'H想定では前で消耗する可能性もある。','M':'M想定では普段と違う位置で脚をためられるかが鍵。'}.get(pace,'ペースが不明のため、この位置取りが有利かは判断を保留。')
        else:
            reason = '普段'+{'逃':'逃げ','先':'先行'}.get(h['running_style'],h['running_style'])+'だが今回は後方想定。'
            reason += {'S':'S想定では前を捕まえにくく、位置取りの変化に注意。','H':'H想定なら前の消耗が助けになる可能性もあり、普段と違う運びで末脚を使えるかが鍵。','M':'M想定では普段より後ろからどこで動くかが鍵。'}.get(pace,'ペースが不明のため、この位置取りが有利かは判断を保留。')
        changes.setdefault(reason, []).append(h)
        caution.append(dict(horse_no=h['horse_no'],horse_name=h['horse_name'],reason=reason))
    commentary = [intro]
    if extra_lines:
        commentary.append(' '.join(extra_lines))
    commentary.append(key_sentence)
    if changes:
        commentary.append(' '.join(('・'.join(name(h) for h in horses) if len(horses)==1 else numbers(horses))+'は'+reason for reason,horses in changes.items()))
    data['development_summary'] = ['逃げ脚質'+str(len(data['running_style_groups']['逃']))+'頭・先行脚質'+str(len(data['running_style_groups']['先']))+'頭。',
                                  '予測ペース：'+pace+'。']
    data.update(commentary_version=VERSION, race_commentary=commentary,
                development_plus_horses=plus, development_caution_horses=caution)
    data.pop('development_watch_horses', None)
    return data


def snapshot(result):
    saved = (result.debug_info or {}).get(KEY)
    return deepcopy(saved) if isinstance(saved, dict) else build(result)


def attach(result, html_files=None):
    if not isinstance((result.debug_info or {}).get(KEY), dict):
        files = html_files or {}
        html = files.get('newspaper') or files.get('newspaper_context') or ''
        # Some existing producer paths omit race_id in race_info. Verify the
        # newspaper against the input speed/entry page, without editing race_info.
        from bs4 import BeautifulSoup
        def own_id(source):
            soup = BeautifulSoup(source, 'html.parser')
            ids = set()
            for tag in soup.select('link[rel="canonical"], meta[property="og:url"]'):
                match = re.search(r'race_id=(\d{12})(?:\D|$)', tag.get('href', tag.get('content', '')))
                if match:
                    ids.add(match[1])
            return next(iter(ids)) if len(ids) == 1 else None
        newspaper_id = own_id(html) if html else None
        evidence = [own_id(files[k]) for k in ('speed','shutuba') if files.get(k)]
        verified_id = newspaper_id if evidence and all(i == newspaper_id for i in evidence) else None
        result.debug_info = {**(result.debug_info or {}), KEY: build(result, html, verified_id)}
    return result


def restore(result, payload):
    saved = payload.get(KEY) or (payload.get('mobile_snapshot') or {}).get(KEY)
    if isinstance(saved, dict):
        result.debug_info = {**(result.debug_info or {}), KEY: deepcopy(saved)}


def render_html(result, mobile=False, display_rows=None):
    data = compose_commentary(snapshot(result), display_rows if display_rows is not None else _rows(result), result.race_mode)
    by = {h['horse_no']: h for h in data['horses']}
    def label(no):
        h = by[no]
        return escape(no+' '+h['horse_name'])
    def candidates(style):
        values = data['running_style_groups'][style]
        return ' / '.join(label(no) for no in values[:3]) + (f' ほか{len(values)-3}頭' if len(values)>3 else '') if values else 'なし'
    pace = escape(data['pace_prediction']) + {'H':'（速め）','M':'（標準）','S':'（遅め）'}.get(data['pace_prediction'],'')
    composition = ' / '.join(f'{s} {len(v)}' for s,v in data['running_style_groups'].items())
    overview = '<section class="development-card"><h4>展開予想</h4><p>予測ペース：'+pace+'</p><p>脚質構成（全'+str(data['horse_count'])+'頭）<br>'+composition+'</p>'
    overview += '<p>逃げ候補：'+candidates('逃')+'</p><p>先行候補：'+candidates('先')+'</p>'
    overview += '<ul>'+''.join('<li>'+escape(s)+'</li>' for s in data['development_summary'])+'</ul><h4>4コーナー展開予想</h4>'
    for group,title in [('front','先団'),('middle','中団'),('back','後方'),('unknown','位置カテゴリ不明')]:
        chips = []
        for no in data['corner4_groups'][group]:
            h = by[no]; suffix = f"（4角{h['corner4_rank']}番手）" if h['corner4_rank'] else '（順位不明）'
            chips.append('<span class="development-horse" title="'+label(no)+'">'+label(no)+escape(suffix)+'</span>')
        overview += '<p><b>'+title+'</b></p><div class="development-line">'+(''.join(chips) or 'なし')+'</div>'
    overview += '</section>'
    commentary = '<section class="development-card"><h4>レース考察</h4>'+''.join('<p>'+escape(s)+'</p>' for s in data['race_commentary'])
    commentary += '</section>'
    css = '<style>.development-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;margin:10px 0}.development-card{min-width:0;border:1px solid #dbe1eb;border-radius:8px;padding:10px;font-size:13px;overflow-wrap:anywhere}.development-card h4{margin:5px 0}.development-card p{margin:7px 0}.development-line{display:flex;flex-wrap:wrap;gap:4px}.development-horse{background:#f2f5f9;border-radius:4px;padding:3px 5px;font-size:12px}@media(max-width:600px){.development-grid{grid-template-columns:1fr}}</style>'
    content = '<div class="development-grid">'+overview+commentary+'</div>'
    return css + ('<details class="development-panel"><summary>展開・レース考察を見る</summary>'+content+'</details>' if mobile else content)
