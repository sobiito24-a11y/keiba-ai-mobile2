"""Read-only prices for the official UI. No scoring or purchase decisions.

Archive additions live beside prediction_result, never inside it. One observation
is a batch: missing tickets are not filled from an older batch.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import re

from .independent_ai_html_odds import norm, parse as parse_html
from .independent_ai_odds import timestamp

KEY = 'race_odds_v1'
JST = timezone(timedelta(hours=9))
KINDS = ('win', 'place', 'quinella', 'wide')
LABELS = dict(win='単勝', place='複勝', quinella='馬連', wide='ワイド')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def identity_from_result(result):
    from .newspaper_v2_inputs import result_rows, race_id, horse_no, pick
    horses = []
    for row in result_rows(result):
        name = pick(row, '馬名', 'horse_name', 'name')
        if not name:
            raise ValueError('馬名が未取得のためオッズを照合できません')
        horses.append(dict(horse_no=int(horse_no(row)), name=str(name)))
    rid = race_id(result)
    if not re.fullmatch(r'\d{12}', rid) or not horses:
        raise ValueError('レースID・出走馬が未取得です')
    return dict(race_id=rid, mode=result.race_mode, horses=horses)


def validate(raw, identity):
    q = deepcopy(raw)
    if not isinstance(q, dict) or q.get('race_id') != identity['race_id'] or q.get('mode') != identity['mode']:
        raise ValueError('レースID・JRA/NARが一致しません')
    expected = {str(h['horse_no']): norm(h['name']) for h in identity['horses']}
    names = q.get('identities', {})
    if not isinstance(names, dict) or any(k not in expected or norm(v) != expected[k] for k, v in names.items()):
        raise ValueError('馬番・馬名が保存予想と一致しません')
    if not isinstance(q.get('prices', []), list):
        raise ValueError('価格一覧の形式が不正です')
    seen = {}
    for p in q.get('prices', []):
        if not isinstance(p, dict):
            raise ValueError('価格行が不正です')
        kind, ns = p.get('kind'), p.get('horses')
        if kind not in KINDS or not isinstance(ns, list) or any(type(n) is not int or str(n) not in names for n in ns):
            raise ValueError('券種・馬番・馬名照合情報が不正です')
        if len(ns) != (2 if kind in ('wide', 'quinella') else 1) or len(set(ns)) != len(ns):
            raise ValueError('組み合わせ馬番が不正です')
        lo, hi = p.get('low'), p.get('high')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (lo, hi)) or not 1 <= lo <= hi:
            raise ValueError('有効なオッズ上下限がありません')
        if kind in ('win', 'quinella') and lo != hi:
            raise ValueError('単勝・馬連には単一オッズが必要です')
        key = (kind, tuple(sorted(ns)))
        if key in seen and seen[key] != (lo, hi):
            raise ValueError('同じ券種・組み合わせに競合価格があります')
        seen[key] = (lo, hi)
    popularity = q.get('popularity', {})
    if not isinstance(popularity,dict) or any(str(k) not in names or type(v) is not int or not 1<=v<=len(expected) for k,v in popularity.items()):
        raise ValueError('人気順位・馬番が不正です')
    q['popularity']={str(k):v for k,v in popularity.items()}
    withdrawn = q.get('withdrawn', [])
    if not isinstance(withdrawn, list) or any(type(n) is not int or str(n) not in names for n in withdrawn):
        raise ValueError('取消・除外馬を照合できません')
    for field in ('received_at', 'observed_at'):
        if q.get(field) is not None and timestamp(q[field]) is None:
            raise ValueError('日時にはタイムゾーンが必要です')
    if not isinstance(q.get('source'), str) or not q['source'].strip():
        raise ValueError('情報源がありません')
    q['prices'] = [dict(kind=k, horses=list(ns), low=lo, high=hi)
                   for (k, ns), (lo, hi) in sorted(seen.items()) if not set(ns).intersection(withdrawn)]
    q['withdrawn'] = sorted(set(withdrawn))
    active = len(expected) - len(q['withdrawn'])
    q['coverage'] = {k: dict(count=sum(p['kind'] == k for p in q['prices']),
                            expected=active * (active-1)//2 if k in ('wide', 'quinella') else active) for k in KINDS}
    q['horse_count'] = len({n for p in q['prices'] if p['kind'] in ('win', 'place') for n in p['horses']})
    q['expected_horses'] = active
    q['collection_status'] = ('unavailable' if not q['prices'] else 'complete'
                              if all(v['count'] == v['expected'] for v in q['coverage'].values()) else 'partial')
    # Transport time is deliberately excluded: reimporting never refreshes prices.
    q['observation_id'] = digest({k: q.get(k) for k in ('race_id', 'mode', 'source', 'observed_at',
                                    'price_status', 'identities', 'withdrawn', 'prices', 'popularity')})
    q['schema_version'] = 1
    return q


def import_files(files, identity, now=None):
    """Validate the ENTIRE operation before the caller commits any observation."""
    now = now or datetime.now(JST)
    out = []
    for filename, raw in files:
        if len(raw) > 12_000_000:
            raise ValueError('オッズ入力は12MB以下にしてください')
        if filename.lower().endswith(('.html', '.htm')):
            html_raw = raw
            if not re.search(br'charset\s*=', raw[:10000], re.I):
                try:
                    raw.decode('utf-8-sig')
                    html_raw = b'<meta charset="utf-8">' + raw
                except UnicodeDecodeError:
                    pass
            q = parse_html(html_raw, identity, now=now)
            q['html_sha256'] = hashlib.sha256(raw).hexdigest()
            # Only explicit named pair exports are supported, not guessed DOM ids.
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_raw, 'html.parser')
            for node in soup(['script', 'style']): node.decompose()
            visible = soup.get_text(' ', strip=True)
            q['availability'] = ('not_on_sale' if re.search(r'発売開始前|まだ発売されて|発売前です', visible)
                                 else 'closed' if re.search(r'発売は終了|発売終了しました', visible) else 'unknown')
            for table in soup.select('table'):
                rows = table.find_all('tr')
                heads = [norm(c.get_text()) for c in rows[0].find_all(['th', 'td'], recursive=False)] if rows else []
                if not all(k in heads for k in ('馬番1', '馬名1', '馬番2', '馬名2', '馬連')):
                    continue
                for tr in rows[1:]:
                    cells = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'], recursive=False)]
                    if len(cells) != len(heads): continue
                    row = dict(zip(heads, cells))
                    if not all(norm(row[k]).isdigit() for k in ('馬番1', '馬番2')): continue
                    ns = [int(norm(row[k])) for k in ('馬番1', '馬番2')]
                    for n, key in zip(ns, ('馬名1', '馬名2')):
                        if str(n) in q['identities'] and norm(q['identities'][str(n)]) != norm(row[key]):
                            raise ValueError('馬連の馬名が一致しません')
                        q['identities'][str(n)] = row[key]
                    value = norm(row['馬連']).removesuffix('倍')
                    if re.fullmatch(r'\d+(?:\.\d+)?', value):
                        q['prices'].append(dict(kind='quinella', horses=ns, low=float(value), high=float(value)))
            quotes = [q]
        else:
            payload = json.loads(raw.decode('utf-8-sig'))
            quotes = payload.get('odds_history', [payload]) if isinstance(payload, dict) else payload
            if not isinstance(quotes, list): raise ValueError('オッズJSONの形式が不正です')
        for raw_q in quotes:
            q = deepcopy(raw_q)
            q['imported_at'] = now.isoformat()
            q.setdefault('acquisition_method', 'manual_html' if filename.lower().endswith(('.html', '.htm')) else 'manual_json')
            q.setdefault('received_at', now.isoformat())
            q.setdefault('input_sha256', hashlib.sha256(raw).hexdigest())
            out.append(validate(q, identity))
    return out


def merge(history, incoming, identity):
    out, seen = [], set()
    for raw in [*history, *incoming]:
        q = validate(raw, identity)
        if q['observation_id'] not in seen:
            out.append(q)
            seen.add(q['observation_id'])
    return out


def baseline(result):
    """Legacy values are saved prices with unknown observation time, never live."""
    from .newspaper_v2_inputs import result_rows, horse_no, pick, number
    ident = identity_from_result(result)
    prices = []
    for row in result_rows(result):
        value = number(pick(row, 'odds_at_prediction', 'actual_odds', '単勝オッズ', 'オッズ', '単勝'))
        if value is not None and value >= 1:
            prices.append(dict(kind='win', horses=[int(horse_no(row))], low=value, high=value))
    return validate(dict(race_id=ident['race_id'], mode=ident['mode'],
                         identities={str(h['horse_no']): h['name'] for h in ident['horses']},
                         prices=prices, source='saved_prediction', received_at=None, observed_at=None,
                         price_status='saved_time_unknown'), ident)


def state_for(result):
    state = getattr(result, '_race_odds', None)
    if isinstance(state, dict): return deepcopy(state)
    try:
        saved = [baseline(result)]
    except (ValueError, TypeError, KeyError):
        saved = []
    return dict(schema_version=1, saved=saved, history=[])


def restore(result, race):
    """Runtime-only attachment; excluded from PredictionResult serialization."""
    if KEY in race:
        try:
            value = race[KEY]
            if not value.get('saved') and not value.get('history'):
                result._race_odds = dict(schema_version=1, saved=[], history=[])
            else:
                ident = identity_from_result(result)
                result._race_odds = dict(schema_version=1, saved=merge([], value.get('saved', []), ident),
                                        history=merge([], value.get('history', []), ident))
        except (ValueError, TypeError, KeyError, AttributeError):
            result._race_odds_error = '保存オッズの照合に失敗しました。予想は維持し、価格を表示しません。'
            result._race_odds = dict(schema_version=1, saved=[], history=[])
    return result


def start_from_result(result):
    """Use explicit saved race date/time only, never the current date."""
    info = result.race_info or {}
    for key in ('start_at', 'start_datetime'):
        if timestamp(info.get(key)): return info[key]
    date = str(info.get('race_date') or info.get('date') or '')
    time_text = str(info.get('start_time') or info.get('race_data') or '')
    day = re.fullmatch(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})', date)
    clock = re.search(r'(\d{1,2}):(\d{2})(?:発走|$)', time_text)
    if day and clock:
        try:
            return datetime(*map(int, day.groups()), *map(int, clock.groups()), tzinfo=JST).isoformat()
        except ValueError:
            pass
    return None


def with_state(event, identity, state):
    out = deepcopy(event)
    races = [r for r in out['races'] if str(r.get('race_id')) == identity['race_id']]
    if len(races) != 1: raise ValueError('コピー内の対象レースを一意に確認できません')
    race = races[0]
    from .independent_ai_odds_io import restore_race
    actual = identity_from_result(restore_race(race))
    if actual != identity: raise ValueError('コピー元の出走馬が一致しません')
    saved = race.get(KEY, {}).get('saved')
    if saved is not None and saved != state.get('saved'):
        raise ValueError('保存時オッズは変更できません')
    race[KEY] = dict(schema_version=1, saved=merge([], state.get('saved', []), actual),
                     history=merge(race.get(KEY, {}).get('history', []), state.get('history', []), actual))
    return out


def export_copy(raw, identity, state):
    import io, zipfile
    from .independent_ai_odds_io import read_archive
    manifest, event = read_archive(raw)
    event = with_state(event, identity, state)
    body = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    manifest['snapshot_sha256'] = hashlib.sha256(body).hexdigest()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('snapshot.json', body)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
    return out.getvalue()


def freshness(q, start_at=None, now=None, max_age_seconds=300):
    now = now or datetime.now(JST)
    start, observed, received = timestamp(start_at), timestamp(q.get('observed_at')), timestamp(q.get('received_at'))
    if q.get('availability') == 'not_on_sale': return '発売前・購入可能価格ではありません'
    if q.get('availability') == 'closed': return '発売終了・履歴参考価格'
    if q.get('price_status') in ('predicted_odds', 'final', 'post_race'):
        return '参考価格（予想オッズまたは終了後）'
    if start and (now >= start or (observed and observed >= start) or (received and received >= start)):
        return '発走後・履歴参考価格'
    if not q.get('prices'): return '有効な価格未取得'
    if not start: return '発走日時未確認・購入可能価格と未確認'
    if not observed: return '提供元更新時刻不明・鮮度未確認'
    if observed > now or (received and observed > received): return '提供元時刻が未来・確認が必要'
    if (now-observed).total_seconds() > max_age_seconds: return '古い観測・現在価格ではありません'
    return '発走前の観測価格（変動します）'


def format_time(value):
    t = timestamp(value)
    return t.astimezone(JST).strftime('%Y/%m/%d %H:%M:%S JST') if t else '時刻不明'


def received_label(q):
    if q.get('acquisition_method') == 'manual_screenshot': return '画像取込日時（価格更新時刻ではありません）'
    return 'HTML取込日時' if q.get('acquisition_method') == 'manual_html' else '取得・受信記録日時'


def price_text(p):
    return (f"{p['low']:.1f}" if p['low'] == p['high'] else f"{p['low']:.1f}〜{p['high']:.1f}") if p else '—'


def overlay(view, quote, label):
    """Price-only copy: no fallback to older horse prices in a partial batch."""
    out = deepcopy(view)
    prices = {(p['kind'], tuple(p['horses'])): p for p in (quote or {}).get('prices', [])}
    for h in out:
        ns = (int(h['no']),)
        h['odds'] = price_text(prices.get(('win', ns)))
        h['place_odds'] = price_text(prices.get(('place', ns)))
        h['popularity'] = (quote or {}).get('popularity',{}).get(str(ns[0]))
        h['odds_source'] = (quote or {}).get('source','未取込')
        h['odds_received_at'] = format_time((quote or {}).get('received_at'))
        h['odds_label'] = label
        h['odds_time'] = format_time((quote or {}).get('observed_at'))
        if ns[0] in (quote or {}).get('withdrawn', []):
            h['odds'] = h['place_odds'] = '取消・除外'
            h['popularity'] = None
        h.setdefault('sort_values',{}).update(odds=prices.get(('win',ns),{}).get('low') if ns[0] not in (quote or {}).get('withdrawn',[]) else None,popularity=h['popularity'])
    return out
