"""The normal A-only comparison workspace; no prediction or persistence."""
import json
from pathlib import Path

from .prediction_table_ui import number
from .final_candidate_selection import formal_score
from .race_explorer_common import index_html, material_text, number_badge, plain, value
from .race_explorer_cards import detail_html, pickup_html
from .race_explorer_visuals import ability_html, development_html


def _run(run):
    return '<b class="metric-number">'+value(run.get('time_index'))+(' <span class="maximum-match" title="保存された最高指数と一致">★</span>' if run.get('is_maximum') else '')+'</b><small>'+value(run.get('condition'))+'</small><small>'+value(run.get('date'))+'</small>'


def _text(item):
    if isinstance(item,(list,tuple)):
        return ' / '.join(str(v) for v in item if v)
    return str(item or '')


def _summary(facts):
    labels=[]
    for title,key in [('プラス','plus'),('注意','caution')]:
        raw=material_text(_text(facts.get(key)))
        if raw and raw not in ('—','―','未取得'):
            labels.append('<span class="lineup-material '+key+'" title="'+plain(raw)+'"><small>'+title+'</small>'+plain(raw)+'</span>')
    return ''.join(labels) or '<span class="muted">未取得</span>'


def lineup_html(view):
    jra=bool(view and view[0].get('mode')=='jra')
    columns=[('自分の✓','user'),('馬番','number'),('馬名・性齢・騎手','name'),('現行A最終評価','score'),
             ('純能力','ability'),('距離指数','distance'),('コース指数','course'),('3走前','run-old'),
             ('2走前','run-middle'),('前走','run-latest'),('3走平均','average'),('★最高指数','maximum'),
             ('4角想定','corner'),('前走間隔','rest')]
    if jra:columns.append(('調教','training'))
    columns += [('斤量・前走比','weight'),('判断材料','materials'),('単勝・人気','odds')]
    rows=[]
    for h in sorted(view,key=lambda h:(number(h.get('no')) is None,number(h.get('no')) or 0)):
        facts=h.get('explorer_facts') or {}; metrics=facts.get('metrics') or h.get('final_metrics') or {}
        runs={r.get('label'):r for r in facts.get('runs',[]) if isinstance(r,dict)}
        no=plain(h.get('no')); name=plain(h.get('name'))
        score=formal_score(h); rank=number(h.get('rank'))
        cells=[('<input type="checkbox" class="user-horse-check" data-user-check="'+no+'" aria-label="自分のチェック '+no+' '+name+'">'),number_badge(h),
               '<button type="button" class="horse-select" data-horse-open="'+no+'" aria-expanded="false" aria-controls="horse-detail-'+no+'"><strong>'+name+'</strong><span>'+value(h.get('age'))+' · '+value(facts.get('current_jockey',h.get('jockey')))+'</span><small>'+value(facts.get('jockey_change'))+' · 詳細を開く</small></button>',
               '<b class="metric-number">'+value(score)+'</b>'+('<small class="metric-rank">正式'+value(rank)+'位</small>' if score is not None and rank is not None else ''),
               index_html(metrics.get('ability')),index_html(metrics.get('distance')),index_html(metrics.get('course')),
               *(_run(runs.get(label,{})) for label in ('3走前','2走前','前走')),
               '<b class="metric-number">'+value(metrics.get('average'))+'</b>', '<b class="metric-number">'+value(metrics.get('maximum'))+'</b>',
               '<b>'+value(h.get('corner'))+'</b><small>'+value(h.get('style'))+'</small>',value(facts.get('rest_label'))]
        if jra:cells.append(value(facts.get('training')))
        cells += [value(facts.get('weight_label'))+'<small>'+value(facts.get('weight_delta_label'))+'</small>',_summary(facts),
                  '<b>'+value(h.get('odds'))+'</b><small>'+ (value(h.get('popularity'))+'人気' if number(h.get('popularity')) is not None else '人気 未取得')+'</small>']
        rows.append('<tr data-row="'+no+'" data-horse="'+no+'">'+''.join('<td class="col-'+cls+'" data-label="'+label+'">'+cell+'</td>' for (label,cls),cell in zip(columns,cells))+'</tr>')
    return ('<section class="lineup-workspace" id="lineup-workspace"><div class="explorer-section-heading"><div><span class="eyebrow">COMPARE ALL RUNNERS</span><h2>全頭予想・比較一覧</h2></div><span class="count">全'+str(len(view))+'頭</span></div>'
            '<p class="help">自分の✓は比較用です。何頭でも選べます。予測・保存データ・買い目には反映しません。馬名から詳細を開けます。</p>'
            '<div class="lineup-toolbar"><label>表示 <select id="lineup-filter"><option value="all">全頭表示</option><option value="selected">自分の✓だけ表示</option></select></label>'
            '<label>並び順 <select id="lineup-sort"><option value="no">馬番順</option><option value="score">A最終スコア順</option><option value="ability">純能力順位順</option><option value="distance">距離指数順</option><option value="course">コース指数順</option></select></label>'
            '<label>方向 <select id="lineup-direction"><option value="asc">昇順</option><option value="desc">降順</option></select></label>'
            '<button type="button" id="clear-user-selection">全選択解除</button><span id="selection-count" role="status" aria-live="polite">自分の✓ 0頭</span></div>'
            '<p id="lineup-empty" class="no-data" hidden>選択している馬はありません。全頭表示から比較する馬を選べます。</p>'
            '<div class="table-scroll explorer-table-scroll" tabindex="0" aria-label="全頭比較・横スクロール"><table class="explorer-table"><thead><tr>'+''.join('<th scope="col" class="col-'+cls+'">'+label+'</th>' for label,cls in columns)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
            '<p class="help">過去走は3走前 → 2走前 → 前走。★は保存された最高指数との一致です。長い判断材料は馬名から全文を確認できます。</p></section>')


def document(view,race_key='',paper_decision=None,portable=None):
    from .game_race_ui import ASSETS, comparison_data, comparison_html, nar_watch_html, paper_html, odds_status
    context=view[0].get('race_context',{}) if view else {}
    horses=[]
    for h in view:
        sort=dict(h.get('sort_values') or {})
        sort['score']=sort['final_score']=formal_score(h)
        horses.append(dict(no=h['no'],rank=number(h.get('rank')),sort=sort))
    payload=dict(experience='race-comparison',active_model='A',race_key=race_key,horses=horses,
                 names=[str(h['no'])+' '+str(h['name']) for h in view],cards=[detail_html(h) for h in view],
                 tabs=comparison_data(view,view[0].get('mode','jra') if view else 'jra',race_key,portable))
    data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+ (ASSETS/'race.css').read_text(encoding='utf-8')+'</style><body class="race-explorer"><main>'
            '<section id="race-pickup" class="race-pickup"><div class="explorer-section-heading"><div><span class="eyebrow">RACE PICKUP</span><h2>レースピックアップ</h2></div><span class="current-model">現行A</span></div>'
            '<p class="help">候補の状態と特徴を比較できます。購入する馬と券種はご自身で選べます。</p>'+pickup_html(view)+'</section>'
            +'<div class="overview-visuals">'+development_html(view,context)+ability_html(view)+'</div>'+odds_status(view)+lineup_html(view)
            +'<details class="detail-analysis" id="detail-analysis"><summary>詳細分析 <span>既存の12項目・研究指標</span></summary>'+comparison_html(view,view[0].get('mode','jra') if view else 'jra')+'</details>'
            +'<details class="advanced-research"><summary>買い目・保存済み研究情報</summary>'+nar_watch_html(view,portable)+paper_html(view,race_key,paper_decision)+'</details>'
            +'<section id="selected-section" hidden><div id="selected-card"></div></section><p id="selection-status" class="sr-only" role="status" aria-live="polite"></p>'
            +'<noscript>比較する馬の選択や詳細表示にはJavaScriptを有効にしてください。</noscript></main><script type="application/json" id="race-data">'+data+'</script><script>'+(ASSETS/'race.js').read_text(encoding='utf-8')+'</script></body></html>')
