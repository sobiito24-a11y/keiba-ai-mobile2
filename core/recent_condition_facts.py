"""Dated, display-only last-three-start condition evidence. No score adjustment."""
import re
from html import escape
from .condition_fit import _current_condition, _venue_key, _turn_key, _distance_int

VERSION = 'recent_condition_facts_v1'
LABELS = {'venue': '同会場', 'turn': '同回り', 'venue_distance': '同会場・同距離'}
STATES = {'placed': '好走歴あり', 'started': '出走経験あり・好走歴なし',
          'absent': '過去3走に該当出走なし', 'missing': '過去走データ不足'}


def surface(value):
    value = str(value or '').strip()
    return '芝' if value == '芝' else 'ダ' if value in ('ダ', 'ダート') else None


def evaluate(row, info, runs):
    current = _current_condition(row, info)
    current['venue'] = _venue_key(current['venue'])
    current['surface'] = surface(current['surface'])
    current['turn'] = current['turn'] if current['turn'] in ('右', '左', '直') else None
    result = {'version': VERSION, 'current': current, 'window': '開催日前の保存過去3走',
              'capture_status': '取得時点の証明は別途必要', 'conditions': {}}
    for key in LABELS:
        required = ('surface', 'turn') if key == 'turn' else ('surface', 'venue', 'distance') if key == 'venue_distance' else ('surface', 'venue')
        matches, unknown = [], 0
        for run in runs:
            facts = dict(venue=_venue_key(run.get('venue')), surface=surface(run.get('surface')),
                         turn=_turn_key(run.get('turn')), distance=_distance_int(run.get('distance')))
            if facts['turn'] not in ('右', '左', '直'):
                facts['turn'] = None
            finish = re.fullmatch(r'(\d+)(?:着)?', str(run.get('finish', '')))
            if not all(current.get(k) and facts.get(k) for k in required):
                unknown += 1
                continue
            if all(current[k] == facts[k] for k in required):
                matches.append(dict(run, placed=bool(finish and 1 <= int(finish[1]) <= 3)))
                if not finish:
                    unknown += 1
        placed = [r for r in matches if r['placed']]
        complete = len(runs) == 3 and unknown == 0 and all(current.get(k) for k in required)
        state = 'placed' if placed else 'missing' if not complete else 'started' if matches else 'absent'
        result['conditions'][key] = dict(state=state, complete=complete, matches=matches,
                                         starts=len(matches), top3=len(placed), unknown=unknown)
    return result


def html(data):
    e = lambda x: escape(str(x or '未取得'))
    body = '<section class="recent-conditions"><h4>近走条件実績（加点・降格なし）</h4>'
    for key, item in data['conditions'].items():
        body += '<p><b>'+LABELS[key]+'</b>：'+STATES[item['state']]+'</p>'
        for run in item['matches']:
            body += '<small>'+e(run['label'])+' '+e(run['date'])+' '+e(run['venue'])+' '+e(run['surface'])+e(run['distance'])+' '+e(str(run['finish']).removesuffix('着'))+'着</small><br>'
    return body+'<p class="help">近3走に該当なしは全キャリアの未経験・不適性を意味しません。</p></section>'


def materials(data):
    # Prefer the most specific positive evidence instead of repeating one start.
    for key in ('venue_distance', 'venue', 'turn'):
        item = data['conditions'][key]
        wins = [r for r in item['matches'] if r['placed']]
        if wins:
            return ['近走'+LABELS[key]+'好走（'+'・'.join(r['label']+str(r['finish']).removesuffix('着')+'着' for r in wins)+'）']
    return []
