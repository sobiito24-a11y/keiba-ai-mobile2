"""Read-only five-horse presentation; original three-horse select/freeze stay intact."""
from html import escape
from .jra_corner4_shadow import select, MARK_PRIORITY


def candidates(view, race_key=''):
    state = select(view, race_key)
    if state['status'] != 'ready':
        return dict(state, comparison=[])
    selected = {h['no'] for h in state['shadow']}
    pool = [h for h in state['frozen_input']['input']
            if h['mark'] in MARK_PRIORITY and h['no'] not in selected]
    pool.sort(key=lambda h: (h['ability_rank'], MARK_PRIORITY[h['mark']], h['no']))
    return dict(state, comparison=[dict(h, selection_reason='中心候補以外の印馬から純能力順位で追加') for h in pool[:2]])


def text(value):
    return '—' if value is None or str(value).strip() in ('', 'None', 'nan') else str(value)


def card(item, horse):
    from .game_race_ui import frame_html, mark_html
    ev = horse.get('candidate_evidence') or {}
    audit = ev.get('audit') or {}
    jockey = audit.get('jockey') or {}
    weights = audit.get('weight') or {}
    rest = audit.get('rest') or {}
    plus = text(horse.get('plus')); minus = text(horse.get('caution'))
    def pair(label, value):
        return '<div><dt>'+escape(label)+'</dt><dd>'+escape(text(value))+'</dd></div>'
    delta = horse.get('weight_delta')
    delta_text = f'{delta:+.1f}kg' if isinstance(delta, (int, float)) else '—'
    current = weights.get('current')
    weight = f'{current:g}kg' if isinstance(current, (int, float)) else horse.get('weight')
    rest_text = str(rest['days'])+'日（前走から）' if rest.get('status') == 'verified' and rest.get('days') is not None else horse.get('rest') or '未取得'
    upgrade = jockey.get('upgrade')
    upgrade_text = 'あり（既存判定）' if upgrade is True else '該当なし（既存判定）' if upgrade is False else '未取得'
    upgrade_reasons = [v for v in ev.get('plus', []) if '騎手強化' in v] if upgrade is True else []
    # Only existing positive-material text explicitly describing a class change.
    conditions = [v.strip() for v in (plus+' / '+minus).split(' / ') if any(k in v for k in ('昇級','降級','クラス変更'))]
    development = '○（既存の展開有利評価）' if horse.get('development') in ('◎','○') else '該当なし／未取得'
    fields = [('純能力指数',horse.get('ability')),('正式スコア',horse.get('score')),
              ('展開有利',development),('調教',horse.get('training')),('斤量',weight),('斤量増減',delta_text),
              ('条件変化',' / '.join(conditions) or '未取得'),('休養・間隔',rest_text),
              ('騎手',horse.get('jockey')),('継続／乗替',horse.get('jockey_change_text')),
              ('騎手ポイントUP',upgrade_text)]
    details = pair('ポイントUP根拠',' / '.join(upgrade_reasons) or '—')+pair('保存騎手成績',horse.get('jockey_stats'))
    details += pair('騎手成績条件',jockey.get('jockey_stat_condition'))
    details += pair('騎手成績母数',jockey.get('current_jockey_sample_size'))
    for key,label in [('distance','距離'),('course','コース')]:
        metric=horse.get(key) or {}
        value='—' if metric.get('value') is None else str(metric['value'])+' / '+text(metric.get('rank'))+'位'
        details += pair(label+'指数（既存）',value)
    details += pair('条件実績',' / '.join(text(v) for v in (horse.get('stars') or {}).values()))
    details += pair('既存の好走根拠',' / '.join(ev.get('plus',[])))
    details += pair('既存の不安材料',' / '.join(ev.get('minus',[])))
    return ('<article class="corner4-shadow-entry"><details class="shadow-horse-details"><summary class="shadow-horse-heading">'
            +frame_html(horse.get('frame'))+'<strong>'+escape(str(item['no'])+' '+item['name'])
            +'</strong>'+mark_html(text(horse.get('mark')))+'<span class="shadow-toggle" aria-hidden="true">⌄</span></summary>'
            +'<div class="shadow-horse-body"><small>純能力'+escape(str(item['ability_rank']))+'位 · 正式'+escape(text(item['formal_rank']))
            +'位 · 4角想定'+escape(str(item['corner4_rank']))+'番手</small><p>'+escape(item['selection_reason'])+'</p>'
            +'<dl class="shadow-facts">'+''.join(pair(k,v) for k,v in fields)+'</dl>'
            +'<p class="shadow-positive">今回プラス：'+escape(plus)+'</p><p class="shadow-negative">今回注意：'+escape(minus)+'</p>'
            +'<details><summary>適性・騎手・根拠の詳細</summary><dl class="shadow-facts">'+details+'</dl></details></div></details></article>')


def html(view, race_key=''):
    if not view or view[0].get('mode') != 'jra': return ''
    state=candidates(view,race_key)
    intro=('<section class="corner4-shadow" aria-label="JRA 最終候補5頭（研究用）">'
           '<div class="corner4-shadow-heading"><h3>JRA｜最終候補5頭（研究用）</h3></div>'
           '<p class="corner4-shadow-note">正式予想・購入推奨ではありません。印馬から比較対象を整理した研究情報です。</p>')
    if state['status'] != 'ready':return intro+'<p>未判定：'+escape(state['reason'])+'</p></section>'
    by={int(h['no']):h for h in view}
    result=intro
    for title,key,style in [('中心候補3頭','shadow','central'),('比較候補'+str(len(state['comparison']))+'頭','comparison','additional')]:
        result+='<h4>'+title+'</h4><div class="corner4-shadow-cards '+style+'">'
        result+=''.join(card(h,by[h['no']]) for h in state[key]) or '<p>該当候補なし</p>'
        result+='</div>'
    result+='<p class="corner4-shadow-note">比較：純能力順3頭 '+escape(' ／ '.join(str(h['no'])+' '+h['name'] for h in state['baseline']))+'</p>'
    result+='<p class="corner4-shadow-note">固定JSONは従来の中心3頭用です。追加2頭は表示専用で、保存済み固定記録を変更しません。</p>'
    return result+'</section>'
