"""Offline research only; no production predictor or UI imports this module."""
import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'market_rank_audit_v1_20261016'
FIELDS = ('horse_no', 'name', 'formal_rank', 'pure_rank', 'formal_mark', 'odds',
          'formal_rank_source', 'status', 'pure', 'formal_score', 'pace_bonus',
          'position_bonus', 'repro_bonus', 'training_bonus', 'state_bonus',
          'rest_days', 'training', 'corner4', 'distance_index', 'course_index',
          'recent3_mean', 'load_change', 'style', 'pace', 'jockey_place_rate')
META = ('date', 'venue', 'distance', 'discipline', 'prediction_version',
        'prediction_created_at', 'odds_observed_at', 'odds_source', 'post_time',
        'source_hash', 'result_seen', 'split')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def rank(value):
    n = number(value)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def build(race_id, mode, horses, metadata):
    """Allow-listed prediction facts only. Missing ranks are never replayed."""
    if mode not in ('jra', 'nar'):
        raise ValueError('invalid mode')
    rows = [{k: copy.deepcopy(h.get(k)) for k in FIELDS} for h in horses]
    for h in rows:
        for k in ('horse_no', 'formal_rank', 'pure_rank'):
            h[k] = rank(h[k])
        for k in ('odds', 'pure', 'formal_score', 'pace_bonus', 'position_bonus',
                  'repro_bonus', 'training_bonus', 'state_bonus'):
            h[k] = number(h[k])
    keys = [h['horse_no'] for h in rows]
    if not all(keys) or len(keys) != len(set(keys)):
        raise ValueError('invalid or duplicate horse numbers')
    rows.sort(key=lambda h: h['horse_no'])
    meta = {k: copy.deepcopy(metadata.get(k)) for k in META}
    inputs = dict(race_id=str(race_id), mode=mode, horses=rows, metadata=meta)
    result = dict(version=VERSION, research_only=True, inputs=inputs,
                  input_hash=digest(inputs), orders={}, unavailable={}, audit=[])
    active = [h for h in rows if h['status'] not in ('取消', '除外', 'scratched', 'excluded')]
    def order(label, values, reverse=False):
        if len(values) != len(active) or not active:
            result['unavailable'][label] = '全頭の保存値が揃っていません'
        else:
            result['orders'][label] = sorted(values, key=lambda no: ((-1 if reverse else 1)*values[no], no))
    order('formal', {h['horse_no']: h['formal_rank'] for h in active
                     if h['formal_rank'] and h['formal_rank_source'] not in (None, '', 'not_saved', 'reference_recalculation')})
    order('pure', {h['horse_no']: h['pure_rank'] for h in active if h['pure_rank']})
    order('market', {h['horse_no']: h['odds'] for h in active if h['odds'] is not None and h['odds'] >= 1.1})
    orders = result['orders']
    if 'pure' in orders and 'market' in orders:
        orders['pure3_market_fill'] = list(dict.fromkeys(orders['pure'][:3]+orders['market']))[:5]
    components = ('pace_bonus', 'position_bonus', 'repro_bonus', 'training_bonus', 'state_bonus')
    decomposable = mode == 'jra' and meta['discipline'] == 'flat' and active and all(
        h['pure'] is not None and h['formal_score'] is not None and
        all(h[k] is not None for k in components) and
        abs(h['pure']+sum(h[k] for k in components)-h['formal_score']) <= .0011 for h in active)
    if decomposable:
        for label, removed in (('position_removed', 1.), ('position_half', .5)):
            order(label, {h['horse_no']: h['formal_score']-removed*(h['pace_bonus']+h['position_bonus']) for h in active}, True)
    elif mode == 'jra':
        result['unavailable']['position_components'] = '保存内訳の合計一致または平地条件を確認できず、分解不可'
    market = {h['horse_no']: 1+sum(other['odds'] < h['odds'] for other in active)
              for h in active} if 'market' in orders else {}
    for h in active:
        flags = []
        if market.get(h['horse_no'], 999) <= 3 and (h['formal_rank'] or 999) >= 6:
            flags.append('市場上位・正式評価圏外')
        if h['pure_rank'] and h['pure_rank'] > 5:
            flags.append('保存純能力もTop5圏外（原因の断定ではありません）')
        for k in ('distance_index', 'course_index', 'recent3_mean'):
            if h[k] is None:
                flags.append(k+'未取得')
        if number(h['rest_days']) is not None and number(h['rest_days']) >= (180 if mode == 'jra' else 36):
            flags.append('休養注意・研究上の警告（除外条件ではありません）')
        result['audit'].append(dict(h, market_rank=market.get(h['horse_no']), flags=flags,
                                    causal_reason='不明：保存特徴量との関連のみ。因果は未検証'))
    result['odds_time_status'] = '観測時刻あり・鮮度は別途監査' if meta['odds_observed_at'] else '参考・時刻不明'
    return result


def seal(report, fixed_at=None):
    record = copy.deepcopy(report)
    record['fixed_at'] = fixed_at or datetime.now(timezone.utc).isoformat()
    record['prospective_eligible'] = False
    # A local hash/time does not prove pre-start existence or absence of result exposure.
    record['validation_status'] = 'independent_external_timestamp_and_unseen_registry_required'
    record['record_hash'] = digest(record)
    return record


def verify(record):
    return record.get('record_hash') == digest({k: v for k, v in record.items() if k != 'record_hash'})


def save_once(record, directory):
    if not verify(record):
        raise ValueError('hash mismatch')
    rid = record['inputs']['race_id']
    if not rid.isdigit():
        raise ValueError('invalid race id')
    path = Path(directory) / (record['inputs']['mode']+'_'+rid+'.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2, allow_nan=False)
    return path


def settlement(kind, horses, outcome):
    """Official complete payout maps only. Ordered exacta is never sorted."""
    ns = list(horses)
    if kind not in ('win', 'place', 'wide', 'quinella', 'exacta'):
        raise ValueError('unsupported kind')
    if len(ns) != (1 if kind in ('win', 'place') else 2) or len(set(ns)) != len(ns):
        raise ValueError('invalid ticket')
    if not outcome.get('confirmed'):
        return dict(status='unknown', payout=None)
    refund = outcome.get('refunds', {}).get(kind, [])
    key = '-'.join(map(str, ns if kind == 'exacta' else sorted(ns)))
    if key in refund:
        return dict(status='refund', payout=100)
    if outcome.get('special_settlement'):
        return dict(status='unknown', payout=None)
    payouts = outcome.get('payouts', {}).get(kind)
    finishes = outcome.get('finishes', {})
    if not payouts or any(rank(finishes.get(str(n))) is None for n in ns):
        return dict(status='unknown', payout=None)
    # Missing payouts on a winning ticket indicate an incomplete map, not a loss.
    fs = [rank(finishes[str(n)]) for n in ns]
    place_count = outcome.get('place_places')
    if kind == 'place' and place_count is None:
        return dict(status='unknown', payout=None)
    wins = {'win': fs == [1], 'place': len(fs) == 1 and fs[0] <= (place_count or 0),
            'wide': len(fs) == 2 and max(fs) <= 3,
            'quinella': sorted(fs) == [1, 2], 'exacta': fs == [1, 2]}
    if key in payouts:
        value = number(payouts[key])
        return dict(status='hit', payout=value) if value is not None and value > 0 else dict(status='unknown', payout=None)
    if wins[kind] or outcome.get('dead_heat'):
        return dict(status='unknown', payout=None)
    return dict(status='miss', payout=0)


def metrics(tickets, total_races):
    """Unknown payouts excluded, never converted to zero. Two outlier conventions."""
    known = [t for t in tickets if number(t.get('payout')) is not None]
    stake = sum(t.get('cost', 100) for t in known)
    returned = sum(t['payout'] for t in known)
    result = dict(tickets=len(tickets), settled=len(known), unknown=len(tickets)-len(known),
                  races=len({t['race_id'] for t in tickets}), cost=stake, payout=returned,
                  profit=returned-stake, roi=100*returned/stake if stake else None,
                  hits=sum(t.get('status') == 'hit' for t in known),
                  skip_rate=1-len({t['race_id'] for t in tickets})/total_races if total_races else None)
    top = sorted(known, key=lambda t: (-t['payout'], str(t['race_id']), str(t.get('horses', ''))))
    for n in (1, 2):
        removed = top[:n]; ret = returned-sum(t['payout'] for t in removed)
        cost = stake-sum(t.get('cost', 100) for t in removed)
        result[f'roi_without_{n}_fixed_stake'] = 100*ret/stake if stake else None
        result[f'roi_without_{n}_removed_purchase'] = 100*ret/cost if cost else None
    return result


def evaluate_frozen(record, race_id, outcome):
    """Return a separate result document; never update the fixed prediction."""
    if not verify(record) or str(race_id) != record['inputs']['race_id']:
        raise ValueError('hash or race id mismatch')
    finishes = outcome.get('finishes', {})
    rows = []
    for method, order in record['orders'].items():
        complete = outcome.get('confirmed') and all(rank(finishes.get(str(n))) for n in order)
        rows.append(dict(method=method,
                         winner_caught=any(finishes.get(str(n)) == 1 for n in order[:5]) if complete else None,
                         top3_caught=sum(finishes.get(str(n), 999) <= 3 for n in order[:5]) if complete else None))
    return dict(record_hash=record['record_hash'], race_id=str(race_id),
                result_hash=digest(outcome), comparisons=rows)
