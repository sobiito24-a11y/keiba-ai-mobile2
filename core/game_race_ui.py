"""Read-only game-style presentation. No selection, scoring or persistence."""
from html import escape
from pathlib import Path
import json
import re

from .prediction_table_ui import horse_key, text, pick, number, fmt, sex_age_text, load_weight_text, jockey_text, jockey_place_text
from .supplementary_assessment import annotate, KEY, rest_text, training
from .position_signals import corner4_rank
from .material_display import material_cells
from .game_ui_information import changes

ASSETS = Path(__file__).with_name('game_ui_assets')
FRAME_COLORS = {1: ('#f7f8fc', '#101522'), 2: ('#171a22', '#ffffff'),
                3: ('#db394f', '#ffffff'), 4: ('#2868d9', '#ffffff'),
                5: ('#f4d348', '#171a22'), 6: ('#20834e', '#ffffff'),
                7: ('#ee942d', '#171a22'), 8: ('#f295be', '#171a22')}
MARK_CLASSES = {'◎': 'honmei', '○': 'taiko', '▲': 'tanana', '✔': 'target',
                '✓': 'check', '△': 'osae', '☆': 'star'}


def frame_number(row):
    """Use explicit current-entry fields only; conflicts stay uncoloured."""
    values = {number(row[k]) for k in ('枠', '枠番', 'frame_number', 'frame_no', 'waku')
              if k in row and number(row[k]) is not None and 1 <= number(row[k]) <= 8 and number(row[k]).is_integer()}
    return int(next(iter(values))) if len(values) == 1 else None


def index_display(cell):
    # Consume the existing full-field index/rank cell; never re-rank here.
    match = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*/\s*(\d+)位\s*', text(cell))
    if not match or int(match[2]) < 1:
        return dict(value=None, rank=None, badge='未取得')
    rank = int(match[2])
    return dict(value=float(match[1]), rank=rank,
                badge='◎' if rank == 1 else '○' if rank <= 3 else '△' if rank <= 5 else '—')


def build_view(rows, records, source_rows=(), mode='jra', race_info=None, materials=None, frames=None):
    """A whitelisted projection of the existing UI records, in their exact order."""
    sources = {horse_key(h): h for h in source_rows}
    by = {horse_key(h): h for h in annotate(rows, source_rows, mode, race_info)}
    from .prediction_table_ui import display_index_rows
    indices = {horse_key(h):h for h in display_index_rows(rows, source_rows, race_info, mode)}
    out = []
    evidence_sources = {}
    for rec in records:
        no, _, name = rec['馬番 / 馬名'].partition(' ')
        row = dict(sources.get(no, {})); row.update({k:v for k,v in by.get(no, {}).items() if text(v)})
        evidence_sources[no] = row
        a = row.get(KEY) or {}
        idx=indices.get(no,{})
        source=sources.get(no,row)
        frame = frame_number(sources.get(no, {})) or frame_number(row)
        if frame is None and frames and no in frames:
            from .game_ui_frames import normalize_name
            item = frames[no]
            if normalize_name(item['name']) == normalize_name(name): frame = item['frame']
        odds = next((v for k in ('actual_odds', '単勝オッズ', 'オッズ', '単勝', 'odds', 'win_odds', 'market_odds')
                     if (v := number(text(row.get(k)).removesuffix('倍'))) is not None and v > 0), None)
        cells = material_cells(row, mode, (materials or {}).get(no))
        caution = rec.get('今回注意', cells['今回注意'])
        mark = text(rec.get('最終印')) or '—'
        rank_label = 'JRA順位' if mode == 'jra' else 'NAR最終順位'
        score_label = 'JRAスコア' if mode == 'jra' else 'NAR最終スコア'
        out.append(dict(no=no, name=name, mode=mode, frame=frame, mark=mark,
                        score_label=score_label, score=rec.get(score_label, '—'), rank=rec.get(rank_label, '—'),
                        ability=rec.get('純能力', '—'), ability_rank=rec.get('純能力順位', '—'),
                        odds=f'{odds:.1f}' if odds is not None and odds > 0 else '—',
                        formal_member=(row.get('pure_ability_top5_group') is True) if mode=='nar' else (number(rec.get('JRA順位')) is not None and 1<=number(rec.get('JRA順位'))<=5),
                        star=dict(value=idx.get('star_index_value'),rank=idx.get('star_index_rank')),
                        away=dict(value=idx.get('away_same_distance_index_value'),rank=idx.get('away_same_distance_index_rank')),
                        average=dict(value=number(pick(source,'平均指数','近3走平均','3走平均','recent3_avg','recent3_mean')),rank=None),
                        distance=index_display(rec.get('距離')), course=index_display(rec.get('コース')),
                        corner=corner4_rank(row), style=rec.get('脚質', '—'), development=a.get('development') or '—',
                        training=training(row) if mode == 'jra' else '', rest=rest_text(row),
                        stable=(a.get('stable') or {}).get('grade') or '—',
                        comment=text(pick(row, 'stable_comment_market', '厩舎コメント', '新聞コメント', 'stable_comment')) if mode == 'jra' else '',
                        overview=text(rec.get('コメント') or pick(row, '表示コメント', 'display_comment', '一言コメント')),
                        plus=rec.get('今回プラス', cells['今回プラス']), caution=caution,
                        stars={k: rec.get(k, '—') for k in ('★', '☆')},
                        age=sex_age_text(row), weight=load_weight_text(row), jockey=jockey_text(row),
                        jockey_stats=jockey_place_text(row),
                        **changes(row),
                        member=row.get('pure_ability_top5_group') if mode == 'nar' else None,
                        reference=a.get('reference_reason') if a.get('reference') else '',
                        check_reason=a.get('check_reason', ''), past=''))
    values=[h['average']['value'] for h in out if h['average']['value'] is not None]
    from .game_ui_candidate_evidence import evidence
    for h in out:
        v=h['average']['value']
        h['average']['rank']=1+sum(x>v for x in values) if v is not None else None
        h['candidate_evidence'] = evidence(h, evidence_sources[h['no']], race_info)
    return out


def mark_html(mark):
    kind = MARK_CLASSES.get(mark.replace('\ufe0e', '').replace('\ufe0f', ''), 'none')
    return f'<span class="mark {kind}" aria-label="最終印 {escape(mark)}">{escape(mark)}</span>'


def frame_html(n):
    if n not in FRAME_COLORS:
        return '<span class="frame missing" title="枠番未取得">—</span>'
    bg, fg = FRAME_COLORS[n]
    return f'<span class="frame" style="background:{bg};color:{fg}" title="{n}枠">{n}</span>'


def index_html(item):
    if item['value'] is None: return '<span class="muted">未取得</span>'
    return (f'<span class="index-value"><span class="index-symbol" title="指数の全頭内順位バッジ（適性の確実性ではありません）">{item["badge"]}</span>'
            f'<b>{fmt(item["value"])}</b><small>{item["rank"]}位</small></span>')


def training_html(value):
    return f'<span class="training grade-{escape(value)}">{escape(value) or "—"}</span>'


def evidence_html(value, positive):
    if value in ('', '—', '未計算', None): return '<span class="muted">—</span>'
    label = '今回プラス' if positive else '今回注意'
    return f'<span class="signal {"positive" if positive else "caution"}" title="{escape(value)}" aria-label="{label}あり。馬名を選択して詳細を確認">{"○" if positive else "△"}</span>'


def short_materials(value):
    if value in ('', '—', '未計算', None): return ''
    # Presentation snippets only; the full evaluated reasons stay in details.
    return ''.join('<li>'+escape(reason if len(reason) <= 44 else reason[:43]+'…')+'</li>'
                   for reason in value.split(' / '))


def odds_html(h, compact=False):
    win = escape(h.get('odds', '—'))
    place = escape(h.get('place_odds', '—'))
    label = escape(h.get('odds_label', '保存時オッズ'))
    return '<span class="race-price" title="'+label+'"><span>単勝 '+win+'</span><span>複勝 '+place+'</span></span>'


def card_html(h):
    e = escape
    designation = ''
    if h['mode'] == 'nar':
        designation = '正式Top5候補' if h['member'] is True else '追加✓・正式Top5圏外' if h['mark'] == '✓' else '正式Top5圏外' if h['member'] is False else '正式候補情報 未取得'
    stats = [(h['score_label'], h['score']+' / '+h['rank']+'位' if h['rank'] != '—' else h['score']+' / —'),
             ('純能力', h['ability']+' / '+h['ability_rank']+'位' if h['ability_rank'] != '—' else h['ability']+' / —')]
    blocks = ''.join(f'<div class="stat"><span>{e(k)}</span><strong>{e(v)}</strong></div>' for k,v in stats)
    blocks += ''.join(f'<div class="stat index-stat"><span>{label}</span>{index_html(h[key])}</div>' for key,label in [('distance','距離指数'),('course','コース指数')])
    tags = [('脚質', h['style']), ('4角想定', str(h['corner'])+'番手' if h['corner'] is not None else '—')]
    if h['mode'] == 'jra': tags += [('展開有利',h['development']),('調教',h['training'] or '—'),('厩舎評価',h['stable'])]
    if h['rest']: tags.append(('休養',h['rest']))
    raw = f'<article class="horse-detail" data-card="{e(h["no"])}"><div class="card-heading">{frame_html(h["frame"])}<div><span class="eyebrow">{e(designation)}</span><h3>{mark_html(h["mark"])} {e(h["no"])} <span>{e(h["name"])}</span></h3></div><div class="price"><small>{e(h.get("odds_label", "保存時オッズ"))}</small>{odds_html(h)}</div></div>'
    raw += f'<div class="identity">{e(h["age"])} <span>{e(h["weight"])}</span> <span>{e(h["jockey"])}</span></div><div class="stats">{blocks}</div>'
    raw += '<div class="facts">'+''.join(f'<span><small>{e(k)}</small> {training_html(v) if k=="調教" else e(v)}</span>' for k,v in tags)+'</div>'
    raw += '<div class="stars">'+metric_html(h.get('star',{}),'★')+metric_html(h.get('away',{}),'☆')+'</div>'
    raw += '<div class="materials">'
    for key,label in [('plus','今回プラス'),('caution','今回注意')]:
        reasons = short_materials(h[key])
        if reasons: raw += f'<section class="{key}"><h4>{label}</h4><ul>{reasons}</ul></section>'
    raw += '</div>'
    if h.get('candidate_evidence'):
        ev=h['candidate_evidence']
        raw += '<details><summary>最終印候補の好走根拠・不安材料</summary>'
        for key,label in [('plus','＋好走根拠'),('minus','−不安材料'),('neutral','中立の参考情報')]:
            raw += '<p><b>'+label+'</b>：'+e(' / '.join(ev[key]) or '—')+'</p>'
        raw += '<details><summary>根拠の元数値・情報源</summary><div class="past">'+e(json.dumps(ev['audit'],ensure_ascii=False,indent=2))+'</div></details></details>'
    if h['overview']: raw += '<details><summary>総合コメント</summary><p>'+e(h['overview'])+'</p></details>'
    if h['mode'] == 'jra': raw += '<details><summary>厩舎コメント原文</summary><p>'+e(h['comment'] or '未取得')+'</p></details>'
    raw += '<details><summary>材料の全文・騎手実績・過去走</summary><p>騎手の過去実績：'+e(h['jockey_stats'])+'</p>'
    for key,label in [('plus','今回プラス'),('caution','今回注意'),('reference','研究用参考注目'),('check_reason','追加✓の対象確認')]:
        if h[key] and h[key] != '—': raw += f'<p><b>{label}</b>：{e(h[key])}</p>'
    raw += '<div class="past">'+e(h['past'] or '過去走情報 未取得')+'</div></details></article>'
    return raw


def corner4_shadow_html(view, race_key=''):
    from .jra_shadow_panel import html
    return html(view, race_key)


def document(view, race_key='', paper_decision=None):
    css = (ASSETS/'race.css').read_text(encoding='utf-8')
    script = (ASSETS/'race.js').read_text(encoding='utf-8')
    mode = view[0]['mode'] if view else 'jra'
    cols = ['枠','馬番・馬名','最終印','単勝／複勝','JRAスコア' if mode=='jra' else 'NAR最終スコア','純能力','4角想定']
    if mode == 'jra': cols += ['展開有利','調教']
    cols += ['休養','距離','コース','★','☆','今回プラス','今回注意']
    rows = []
    for i,h in enumerate(view):
        cells = [frame_html(h['frame']), f'<button class="horse-select" data-select="{i}" aria-pressed="false"><b>{escape(h["no"])}</b><span>{escape(h["name"])}</span></button>', mark_html(h['mark']), odds_html(h),
                 f'<span class="score">{escape(h["score"])}</span><small>{escape(h["rank"])}位</small>' if h['rank']!='—' else f'<span class="score">{escape(h["score"])}</span><small>順位 —</small>',
                 f'<b>{escape(h["ability"])}</b><small>{escape(h["ability_rank"])}位</small>' if h['ability_rank']!='—' else escape(h['ability']),
                 str(h['corner'])+'番手' if h['corner'] is not None else '—']
        if mode == 'jra': cells += [escape(h['development']), training_html(h['training'])]
        cells += [escape(h['rest']) or '—', index_html(h['distance']), index_html(h['course']), metric_html(h['star'],'★'), metric_html(h['away'],'☆'), evidence_html(h['plus'],True), evidence_html(h['caution'],False)]
        rows.append(f'<tr data-row="{i}" data-horse="{escape(h["no"])}">'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>')
    data = json.dumps(dict(tabs=comparison_data(view,mode),cards=[card_html(h) for h in view], names=[h['no']+' '+h['name'] for h in view], race_key=race_key),ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            +'<style>'+css+'</style><body><main>'+corner4_shadow_html(view,race_key)+comparison_html(view,mode)+paper_html(view,race_key,paper_decision)+'<div class="section-heading"><div><span class="eyebrow">RACE LINEUP</span><h2>全頭予想一覧</h2></div><span class="count">'+str(len(view))+'頭</span></div>'
            +'<p class="help">馬名をタップして詳細へ。表は横・縦にスクロールできます。</p>'
            +'<div class="table-scroll" tabindex="0" aria-label="全頭予想一覧・横スクロール"><table><thead><tr>'+''.join('<th scope="col">'+escape(c)+'</th>' for c in cols)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
            +'<p class="legend">距離・コースの記号は指数順位：◎1位 · ○2〜3位 · △4〜5位 · —6位以下。枠番未取得は無色。</p>'
            +'<div class="section-heading"><div><span class="eyebrow">HORSE PROFILE</span><h2>馬別サマリーカード</h2></div></div><p id="selection-status" class="sr-only" aria-live="polite"></p><div id="selected-card"></div>'
            +'<noscript>馬別カードを表示するにはJavaScriptを有効にしてください。</noscript></main><script type="application/json" id="race-data">'+data+'</script><script>'+script+'</script></body></html>')


def theme_css():
    return '<style>'+(ASSETS/'app.css').read_text(encoding='utf-8')+'</style>'


def race_header(result):
    info = result.race_info or {}
    name = text(result.race_name or pick(info,'race_name','レース名')) or 'レース情報'
    values = [('区分',result.race_mode.upper()),('開催日',pick(info,'race_date','date','開催日')),
              ('競馬場',pick(info,'racecourse','venue','競馬場')),('R',pick(info,'race_number','R','レース番号')),
              ('発走',pick(info,'post_time','start_time','発走時刻')),('距離',pick(info,'distance_label','distance','距離')),
              ('コース',pick(info,'surface','芝ダート')),('馬場',pick(info,'going','馬場状態')),
              ('ペース',pick(info,'netkeiba_pace','pace_prediction','predicted_pace'))]
    # Extract only explicit strings already present in the saved race header.
    if not values[4][1]:
        match=re.search(r'(\d{1,2}:\d{2})\s*発走',text(pick(info,'race_data','raw')))
        if match: values[4]=('発走',match[1])
    if not values[3][1]:
        from .newspaper_v2_inputs import race_id
        rid=race_id(result)
        if re.fullmatch(r'\d{12}',rid):values[3]=('R',str(int(rid[-2:])))
    if not values[-1][1]:
        rows=result.overall_table.to_dict('records') if result.overall_table is not None else []
        p={text(pick(h,'netkeiba_pace','_netkeiba_pace','provider_pace_market')) for h in rows}
        p.discard('')
        if len(p)==1 and next(iter(p)) in ('H','M','S'):values[-1]=('ペース',next(iter(p)))
    return '<section class="game-race-header"><span class="game-eyebrow">KEIBA AI / RACE BRIEFING</span><h2>'+escape(name)+'</h2><div class="game-race-meta">'+''.join('<span><small>'+escape(k)+'</small> '+escape(text(v) or '—')+'</span>' for k,v in values)+'</div></section>'


def render_component(view, race_key, paper_decision=None):
    # Declare from an importable module: Streamlit's __main__ can be transient.
    import streamlit.components.v1 as components
    component = components.declare_component("game_race_lineup", path=str(ASSETS))
    shown = component(html=document(view, race_key,paper_decision), key='game_lineup_'+race_key, default=None)
    if view and view[0].get('mode') == 'jra':
        # Separate research export; never writes to prediction snapshots or .keiba.
        from datetime import datetime, timezone
        from .jra_corner4_shadow import select, freeze
        import streamlit as st
        report = select(view, race_key)
        if report['status'] == 'ready':
            storage_key = 'jra_corner4_fixed_' + str(race_key)
            st.caption('研究用。オッズ欠損は補完しません。固定時刻だけでは発走前の証明になりません。JSONは端末へ保存してください。')
            if storage_key not in st.session_state and st.button('現在の研究候補を固定', key=storage_key+'_button'):
                st.session_state[storage_key] = freeze(view, race_key, datetime.now(timezone.utc).isoformat())
            exported = st.session_state.get(storage_key)
            if exported is None:
                return shown
            if exported['input_sha256'] != report['input_sha256']:
                st.warning('表示入力が固定時と異なります。ダウンロードは以前に固定した候補です。上書きしません。')
            filename = re.sub(r'[^0-9a-zA-Z_-]', '_', str(race_key)) + '_jra_corner4_shadow.json'
            st.download_button(
                '研究用・注目3頭の固定JSONを保存（発走前に）',
                json.dumps(exported, ensure_ascii=False, indent=2),
                file_name=filename, mime='application/json',
                key='jra_corner4_shadow_download_' + str(race_key),
            )
    return shown


def metric_html(item,label):
    if item.get('value') is None:return '<span class="muted">—</span>'
    rank=str(item['rank'])+'位' if item.get('rank') is not None else '—'
    return '<span class="metric-inline">'+escape(label)+' <b>'+escape(fmt(item['value']))+'</b> / '+rank+'</span>'


def comparison_data(view,mode):
    from .game_ui_comparison import comparisons
    groups=comparisons(view,mode)
    for group in groups:
        html=[]
        if group.get('kind')=='candidates':
            group['html']=candidate_html(view,group)
            continue
        if group.get('kind')=='information':
            group['html']=information_html(view,group)
            continue
        for c in group['cards']:
            h=view[c['index']]
            html.append('<button class="top-horse" data-top-select="'+str(c['index'])+'">'+
                        '<span class="top-identity">'+frame_html(h['frame'])+mark_html(h['mark'])+'<b>'+escape(h['no'])+'</b></span>'+
                        '<span class="top-name">'+escape(h['name'])+'</span><span class="top-odds">単勝 '+escape(h['odds'])+'</span>'+
                        '<span class="top-value">'+escape(c['value'])+'</span><span class="top-rank">'+escape(c['rank'])+'</span></button>')
        group['html']=''.join(html) or '<p class="no-data">該当データなし</p>'
    return groups


def comparison_html(view,mode):
    from .game_ui_comparison import TABS
    buttons=''.join('<button role="tab" aria-selected="'+('true' if k=='final' else 'false')+'" data-tab="'+k+'">'+escape(label)+'</button>' for k,label in TABS if mode=='jra' or k!='training')
    return '<section class="metric-comparison"><div class="metric-tabs" role="tablist" aria-label="比較指標">'+buttons+'</div><div id="metric-count"></div><div id="top-horses" class="top-horses" role="tabpanel" tabindex="0" aria-label="選択指標の比較・横縦スクロール"></div><p id="metric-note"></p></section>'


def information_html(view, group):
    from .game_ui_information import reasons
    if not group['rows']:return '<p class="no-data">該当馬なし</p>'
    headers=['枠','馬番・馬名','正式印']+(['今回＋','今回−'] if group['key']=='materials' else ['斤量増減','騎手'])
    html=[]
    for i in group['rows']:
        h=view[i]
        cells=[frame_html(h['frame']),'<button class="horse-select" data-top-select="'+str(i)+'"><b>'+escape(h['no'])+'</b><span>'+escape(h['name'])+'</span></button>',mark_html(h['mark'])]
        if group['key']=='materials':
            for k,c in [('plus','positive'),('caution','caution')]:
                value=' / '.join(reasons(h.get(k)))
                cells.append('<span class="info-reason '+c+'" title="'+escape(value)+'">'+escape(value or '—')+'</span>')
        else:
            delta=h.get('weight_delta')
            value='—' if delta is None else '±0kg' if delta==0 else f'{delta:+.1f}kg'
            color='positive' if delta is not None and delta<0 else 'caution' if delta is not None and delta>0 else 'muted'
            cells.extend(['<span class="'+color+'">'+escape(value)+'</span>',escape(h.get('jockey_change_text','—'))])
        html.append('<tr>'+''.join('<td>'+c+'</td>' for c in cells)+'</tr>')
    return '<table class="information-table"><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(html)+'</tbody></table>'


def candidate_html(view, group):
    if not group['rows']:return '<p class="no-data">最終印候補なし</p>'
    headers=['枠','馬番・馬名','最終印','AIスコア順位','＋好走根拠','−不安材料']
    rows=[]
    for i in group['rows']:
        h=view[i];ev=h.get('candidate_evidence') or {}
        rank=escape(h['rank']+'位' if h['rank']!='—' else '—')
        score=escape(h['score'])
        desktop_rating=score+'／'+rank if number(h['score']) is not None else rank
        empty=not ev.get('plus') and not ev.get('minus')
        rating='<span class="candidate-desktop-rank">'+desktop_rating+'</span><span class="candidate-mobile-rating"><span>AIスコア <b>'+score+'</b>／'+rank+'</span><span>純能力'+escape(h['ability_rank']+'位' if h['ability_rank']!='—' else ' —')+'</span></span>'
        rating += odds_html(h)
        if empty:rating+='<span class="candidate-empty-note">表示できる根拠・不安材料なし</span>'
        cells=[frame_html(h['frame']),'<button class="horse-select" data-top-select="'+str(i)+'" title="'+escape(h['no']+' '+h['name'])+'"><b>'+escape(h['no'])+'</b><span>'+escape(h['name'])+'</span></button>',mark_html(h['mark']),rating]
        for key,color in [('plus','positive'),('minus','caution')]:
            value=' / '.join(ev.get(key,[]))
            label='＋好走根拠' if key=='plus' else '−不安材料'
            cell='<span class="candidate-mobile-label" aria-label="'+label+'">'+('＋' if key=='plus' else '−')+'</span><span class="info-reason '+(color if value else 'muted')+'" title="'+escape(value)+'">'+escape(value or '—')+'</span>'
            if key=='plus' and ev.get('neutral'):
                neutral=' / '.join(ev['neutral'])
                cell+='<span class="info-reason neutral" title="'+escape(neutral)+'">'+escape(neutral)+'</span>'
            cells.append(cell)
        rows.append('<tr data-candidate-select="'+str(i)+'">'+''.join('<td'+(' class="candidate-empty-material"' if (j==4 and not ev.get('plus')) or (j==5 and not ev.get('minus')) else '')+'>'+c+'</td>' for j,c in enumerate(cells))+'</tr>')
    return '<table class="candidate-table"><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def paper_html(view,race_key,paper_decision=None):
    from .paper_betting import build,html
    return html(paper_decision or build(view,view[0]['mode'] if view else 'jra',dict(race_id=race_key)))
