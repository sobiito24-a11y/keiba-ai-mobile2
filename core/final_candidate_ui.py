"""Unmarked final-candidate comparison. All changes are presentation only."""
from html import escape
import re

from .prediction_table_ui import fmt, number
from .final_candidate_selection import select_indices, formal_score
from .final_candidate_metrics import project


def text(value):
    if value is None or value == '' or value == '—':
        return '―'
    return str(value)


def numeric(value):
    value = number(value)
    return fmt(value) if value is not None else '未取得'


def metric(item):
    item = item or {}
    rank = number(item.get('rank'))
    return '<b>'+escape(numeric(item.get('value')))+'</b>'+(
        '<small>'+escape(fmt(rank))+'位</small>' if rank is not None else '')


def run_html(run):
    return ('<b>'+escape(numeric(run.get('time_index')))+
            (' <span class="maximum-match" title="保存された最高指数と一致">★</span>' if run.get('is_maximum') else '')+
            '</b><small>'+escape(text(run.get('condition')))+'</small><small>'+escape(text(run.get('date')))+'</small>')


def facts_html(h, m):
    stability = m.get('stability') or {}
    weight=number(m.get('weight_delta'))
    weight_text='未取得' if weight is None else '±0kg' if weight==0 else f'{weight:+g}kg'
    items = [('近走安定度', stability.get('text')), ('騎手', m.get('jockey_change')),
             ('斤量増減', weight_text), ('同距離実績', m.get('same_distance')),
             ('同コース実績', m.get('same_course')),
             ('プラス材料', m.get('plus')), ('注意材料', m.get('caution'))]
    # Existing material strings also carry judgement glyphs (e.g. "○ 調教B").
    # Keep their factual text here and leave the original strings untouched.
    items=[(k,re.sub(r'[◎○▲✔✓△][\ufe0e\ufe0f]?\s*','',text(v)) if k in ('プラス材料','注意材料') else v) for k,v in items]
    return '<dl class="final-facts">'+''.join(
        '<div><dt>'+escape(k)+'</dt><dd>'+escape(text(v))+'</dd></div>' for k, v in items)+'</dl>'


def detail_html(h, m):
    # Keep the existing full prediction card in the all-runner analysis. This
    # expansion only presents saved facts, without a formal mark/rank/score.
    p = h.get('profile') or {}
    body = '<section class="final-details-body"><h4>保存された詳細情報</h4>'+facts_html(h, m)
    # Generic AI overviews can contain the formal marks/order. They remain in
    # the original all-runner detail, outside this unmarked comparison.
    for key, label in [('comment', '厩舎コメント')]:
        if h.get(key) and not re.search(r'[◎○▲✔✓△]|正式\s*\d+\s*位|最終(?:評価)?スコア',h[key]):
            body += '<p><b>'+label+'</b> '+escape(text(h[key]))+'</p>'
    matchups = p.get('matchups') or []
    if matchups:
        body += '<h4>過去の直接対決</h4>'
        for row in matchups:
            body += '<p>'+escape(' / '.join(text(row.get(k)) for k in ('date', 'venue', 'distance', 'opponent')))+\
                '：着順 '+escape(text(row.get('finish')))+' / 相手 '+escape(text(row.get('opponent_finish')))+'</p>'
    body += '<p class="final-footnote">最高指数の★は保存された最高値との一致、近走安定度は指数のばらつきです。取得できない指数は未取得と表示します。</p></section>'
    return body


def identity(h, i, target):
    odds=number(h.get('odds'))
    popularity=number(h.get('popularity'))
    price=('単勝 '+fmt(odds)+'倍' if odds is not None else '単勝 未取込')+(' · '+fmt(popularity)+'人気' if popularity is not None else '')
    return ('<button type="button" class="final-name" data-final-toggle="'+str(i)+'" aria-expanded="false" aria-controls="'+target+'">'+
            '<strong>'+escape(text(h.get('name')))+'</strong><span>'+escape(text(h.get('age')))+
            ' · '+escape(text(h.get('jockey')))+'</span><span class="final-observed-odds">'+escape(price)+'</span><small>詳細を開く <span aria-hidden="true">⌄</span></small></button>')


def render(view, label=''):
    indices = select_indices(view)
    if not indices:
        return '<p class="no-data">保存された正式候補はありません</p>'
    jra = bool(view and view[0].get('mode') == 'jra')
    calculated=any((view[i].get('final_metrics') or {}).get('average_calculated') for i in indices)
    headers = [('馬番', ''), ('馬名・騎手', ''), ('最終評価スコア', 'final-score'),
               ('純能力', ''), ('距離指数', ''), ('コース指数', ''), ('3走前', ''),
               ('2走前', ''), ('前走', ''), ('3走平均', ''), ('★最高指数', ''),
               ('想定脚質・4角', '')]
    if jra:
        headers.append(('調教', ''))
    headers += [('前走間隔', ''), ('その他の判断材料', '')]
    head = ''.join('<th scope="col"'+(' class="final-score" hidden' if cls else '')+'>'+name+'</th>' for name, cls in headers)
    desktop, mobile = [], []
    for i in indices:
        h = view[i]
        m = h.get('final_metrics') or project(h)
        runs = m['runs']
        score = formal_score(h)
        corner=number(m.get('corner'))
        corner_text=fmt(corner)+'番手' if corner is not None else '未取得'
        score_html = '<span class="final-score-value">'+escape(numeric(score))+'</span>'
        desktop_id, mobile_id = 'final-desktop-detail-'+str(i), 'final-mobile-detail-'+str(i)
        cells = [escape(text(h.get('no'))), identity(h, i, desktop_id), score_html,
                 metric(m.get('ability')), metric(m.get('distance')), metric(m.get('course')),
                 *(run_html(r) for r in runs), '<b>'+escape(numeric(m.get('average')))+'</b>',
                 '<b>'+escape(numeric(m.get('maximum')))+'</b>',
                 escape(text(m.get('style')))+'<small>4角 '+escape(corner_text)+'</small>']
        if jra:
            cells.append(escape(text(m.get('training'))))
        cells += [escape(text(m.get('rest'))), facts_html(h, m)]
        desktop.append('<tr class="final-candidate-row" data-candidate-index="'+str(i)+'">'+''.join(
            '<td'+(' class="final-score" hidden' if c == 2 else '')+'>'+value+'</td>' for c, value in enumerate(cells))+'</tr>')
        desktop.append('<tr id="'+desktop_id+'" class="final-detail-row" hidden><td colspan="'+str(len(headers))+'">'+detail_html(h, m)+'</td></tr>')
        metrics = [('純能力', metric(m.get('ability'))), ('距離指数', metric(m.get('distance'))),
                   ('コース指数', metric(m.get('course'))), ('3走平均', '<b>'+escape(numeric(m.get('average')))+'</b>'),
                   ('★最高指数', '<b>'+escape(numeric(m.get('maximum')))+'</b>')]
        mobile.append('<article class="final-mobile-card" data-candidate-index="'+str(i)+'"><header><b class="final-number">'+escape(text(h.get('no')))+
                      '</b>'+identity(h, i, mobile_id)+'</header><p class="final-position">'+escape(text(m.get('style')))+
                      ' · 4角 '+escape(corner_text)+'</p><div class="final-score" hidden>最終評価スコア '+score_html+'</div>'+\
                      '<dl class="final-metrics">'+''.join('<div><dt>'+k+'</dt><dd>'+v+'</dd></div>' for k, v in metrics)+'</dl>'+\
                      '<div class="final-recent">'+''.join('<section><h4>'+r['label']+'</h4>'+run_html(r)+'</section>' for r in runs)+'</div>'+\
                      '<div class="final-state">'+('<span>調教 '+escape(text(m.get('training')))+'</span>' if jra else '')+\
                      '<span>前走間隔 '+escape(text(m.get('rest')))+'</span></div>'+facts_html(h, m)+\
                      '<div id="'+mobile_id+'" hidden>'+detail_html(h, m)+'</div></article>')
    return ('<section class="final-candidates" data-order="no"><div class="final-toolbar"><label for="candidate-sort">表示順</label>'+\
            '<select id="candidate-sort"><option value="no" selected>馬番順</option><option value="score">スコア順</option></select>'+\
            '<span class="final-order-note">馬番順では最終評価スコアを表示しません</span></div>'+\
            '<p class="final-footnote">過去走は3走前 → 2走前 → 前走。★最高指数と近走安定度は別の情報です。'+('3走平均の保存値がない馬は、確認できた3走の指数の平均を表示します。' if calculated else '')+'</p>'+\
            '<div class="final-table-scroll" tabindex="0" aria-label="最終候補の指数比較・横スクロール"><table class="final-table"><thead><tr>'+head+\
            '</tr></thead><tbody>'+''.join(desktop)+'</tbody></table></div><div class="final-mobile">'+''.join(mobile)+'</div></section>')
