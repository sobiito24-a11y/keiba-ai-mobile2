"""Independent, evidence-led research only. Never returns formal prediction fields.

The 54-race ZIP is exploratory, not validation of these fixed hypotheses.
No fitted outcome coefficients, odds, missing-count features or calibrated probability.
Unknown components stay None; their uncertainty is carried into selection.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math

KEY = 'jra_practical_reevaluation_shadow'
VERSION = 'jra_practical_evidence_shadow_v1'
# Fixed BEFORE replay. Score intervals stop missing evidence deciding membership.
BOUNDS = {'position': 2.0, 'condition': 1.0, 'training': .75}
SETTINGS = {'slow_front': 2.0, 'slow_back': -1.0, 'fast_middle': 1.5,
            'normal_middle': .5, 'condition_top3': .25,
            'training': {'A': .75, 'B': .25, 'C': 0., 'D': -.5},
            'swap_min_positive_domains': 2,
            'swap_requires_strict_interval_dominance': True}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def evaluate_practical_shadow(inputs, *, evaluated_at=None):
    """Pure evaluation of a whitelisted, time-audited input contract.

    Ability is the only numeric anchor. Official score/rank/position bonus are
    comparison metadata: they NEVER enter this score (no position double count).
    Missing components produce an interval, not a mean/zero-filled point rank.
    """
    inputs = deepcopy(inputs)
    rows = inputs['horses']
    keys = [str(h['horse_no']) for h in rows]
    if not all(k.isdigit() and int(k) > 0 for k in keys) or len(set(keys)) != len(keys):
        raise ValueError('馬番欠損・重複')
    status = ('excluded_jump' if inputs.get('is_jump') else
              'time_unverified' if inputs.get('time_status') != 'pre_race' else 'research_only')
    pace = inputs.get('pace')
    corner_values = [number(h.get('corner4_rank')) for h in rows]
    known_positions = sum(v is not None for v in corner_values)
    front = sum(v is not None and v <= 4 for v in corner_values)
    assessed = []
    for raw in rows:
        h = deepcopy(raw)
        positive, negative, context, missing = [], [], [], []
        domains = set()
        def good(domain, text):
            domains.add(domain); positive.append(text)
        pure = number(h.get('pure_score'))
        corner = number(h.get('corner4_rank'))
        grade = h.get('training_grade')
        parts = {'position': None, 'condition': None, 'training': None}
        if pure is None:
            missing.append('純能力未取得：順位・5頭案を確定しない')
        if corner is not None and pace in ('S', 'M', 'H'):
            parts['position'] = 0.
            if pace == 'S' and corner <= 4:
                parts['position'] = SETTINGS['slow_front']
                good('position', f'スロー想定×4角{corner:g}番手（前方構成{front}/{known_positions}頭）')
            elif pace == 'S' and corner >= 9:
                parts['position'] = SETTINGS['slow_back']
                negative.append(f'スロー想定×4角{corner:g}番手：前が残る場合は慎重')
            elif pace in ('M', 'H') and 5 <= corner <= 8:
                parts['position'] = SETTINGS['fast_middle' if pace == 'H' else 'normal_middle']
                good('position', f'{pace}ペース想定×4角{corner:g}番手')
            else:
                context.append(f'{pace}ペース想定×4角{corner:g}番手：固定補正なし')
        else:
            missing.append('予測ペース／4角想定の不足・競合')
        known, hits = 0, []
        for k, label in [('distance', '距離'), ('course', 'コース'), ('star', '★'), ('away', '☆')]:
            value, rank = number(h.get(k + '_index')), number(h.get(k + '_rank'))
            if value is None or rank is None:
                missing.append(label + '指数未取得')
            else:
                known += 1
                if rank <= 3:
                    hits.append(f'{label}{rank:g}位（{value:g}）')
        # Related condition indicators form ONE domain, not four independent votes.
        if known == 4:
            parts['condition'] = len(hits) * SETTINGS['condition_top3']
        if hits:
            good('condition', '条件上位：' + ' / '.join(hits))
        if grade in SETTINGS['training']:
            parts['training'] = SETTINGS['training'][grade]
            if grade in ('A', 'B'):
                good('training', '今回調教' + grade)
            elif grade == 'D':
                negative.append('今回調教D：仕上がりを確認')
        else:
            missing.append('今回調教評価未取得')
        rest = number(h.get('rest_days'))
        return_form = h.get('layoff_returns') or []
        if rest is None:
            missing.append('休養日数未取得')
        elif rest >= 90:
            context.append(f'休養{rest:g}日：一律減点なし')
            successful = [r for r in return_form if number(r.get('finish')) is not None and 1 <= r['finish'] <= 3]
            if successful:
                good('return', f'過去休み明け3着内{len(successful)}例（条件差は過去走欄）')
            elif not return_form:
                missing.append('過去の休み明け実績は確認不能')
            if grade in ('C', 'D') and not successful:
                negative.append(f'長期休養×調教{grade}：復帰根拠を確認（消し判定ではない）')
            elif grade in ('A', 'B'):
                context.append('休養の不安に対し調教A/Bが対抗材料')
        change = number(h.get('load_change'))
        if change is None:
            missing.append('斤量前走比未取得')
        else:
            context.append(f'斤量前走比{change:+g}kg：単独加減点なし')
            if change >= 2:
                negative.append('斤量+2kg以上：年齢・距離・展開と合わせ確認')
        for field, label in [('age', '年齢'), ('load_weight', '今回斤量'), ('class_change', '前走からのクラス変動'), ('body_weight', '当日馬体重')]:
            if h.get(field) is None:
                missing.append(label + '未取得／比較根拠なし')
            else:
                context.append(f'{label}：{h[field]}（単独加減点なし）')
        for meet in h.get('head_to_head', []):
            context.append(f"過去対戦 {meet['race_id']}：自身{meet['own_finish']:g}着／{meet['opponent_no']}番{meet['opponent_finish']:g}着。今回との条件差：{meet['condition_difference']}。単独減点なし")
        if not h.get('head_to_head'):
            missing.append('近3走の照合可能な直接対戦なし（未対戦とは断定しない）')
        if not h.get('recent_runs'):
            missing.append('有効な発走前過去走なし')
        else:
            runs = h['recent_runs']
            for r in runs:
                context.append(f"過去走 {r.get('date')} {r.get('venue')} {r.get('surface')}{r.get('distance')}：{r.get('finish', '—')}着／指数{r.get('value', '—')}（純能力と重複加点しない）")
            indexes = [number(r.get('value')) for r in runs]
            if len(indexes) >= 2 and all(v is not None for v in indexes):
                trend = indexes[0] - sum(indexes[1:]) / len(indexes[1:])
                context.append(f'前走指数－それ以前の取得指数平均 {trend:+.1f}：条件差も確認')
        if h.get('class_change') == '降級':
            good('class', '前走から今回の明示クラス比較で降級（過去上位経験とは別）')
        # An observed subtotal is audit-only; interval width explicitly represents
        # unknown evidence. No rank uses missing=0 or learned missingness.
        subtotal = pure + sum(v for v in parts.values() if v is not None) if pure is not None else None
        uncertainty = sum(BOUNDS[k] for k, v in parts.items() if v is None)
        low = subtotal - uncertainty if subtotal is not None else None
        high = subtotal + uncertainty if subtotal is not None else None
        h.update(components=parts, observed_subtotal=subtotal, score_interval=[low, high],
                 positive_reasons=positive, negative_reasons=negative,
                 decisive_conditions=context, missing_reasons=missing,
                 positive_domains=sorted(domains), classification='優先度維持・材料不足')
        assessed.append(h)
    # Partial ordering: rank range, not an invented total rank for unknown scores.
    for h in assessed:
        lo, hi = h['score_interval']
        h['shadow_rank_range'] = ([1 + sum(o['score_interval'][0] is not None and o['score_interval'][0] > hi for o in assessed),
                                   len(rows) - sum(o['score_interval'][1] is not None and o['score_interval'][1] < lo for o in assessed)]
                                  if lo is not None else None)
    by_no = {str(h['horse_no']): h for h in assessed}
    formal = sorted([h for h in assessed if number(h.get('formal_rank')) is not None and 1 <= h['formal_rank'] <= 5], key=lambda h: (h['formal_rank'], int(h['horse_no'])))
    a = [str(h['horse_no']) for h in formal]
    valid_a = len(a) == 5 and sorted(h['formal_rank'] for h in formal) == [1, 2, 3, 4, 5]
    # Free choice uses the SAME observed domains for every runner. A domain
    # missing for one horse is excluded from the numeric comparison for ALL;
    # it remains in each horse's evidence/interval. Missingness earns no bonus,
    # zero imputation or pessimistic ranking penalty.
    common = [k for k in BOUNDS if assessed and all(h['components'][k] is not None for h in assessed)]
    for h in assessed:
        pure = number(h.get('pure_score'))
        h['comparison_score'] = pure + sum(h['components'][k] for k in common) if pure is not None else None
    eligible = sorted([h for h in assessed if h['comparison_score'] is not None], key=lambda h: (-h['comparison_score'], int(h['horse_no'])))
    for rank, h in enumerate(eligible, 1):
        h['comparison_rank'] = rank
    b = [str(h['horse_no']) for h in eligible[:5]] if len(eligible) == len(rows) and len(rows) >= 5 and status == 'research_only' else []
    c = list(a) if valid_a else []
    swap = None
    if b and valid_a:
        for no in b:
            incoming = by_no[no]
            if no in a or len(incoming['positive_domains']) < SETTINGS['swap_min_positive_domains']:
                continue
            for old in reversed(a):
                outgoing = by_no[old]
                if not outgoing['negative_reasons'] or outgoing['score_interval'][1] is None:
                    continue
                if incoming['score_interval'][0] <= outgoing['score_interval'][1]:
                    continue
                c[c.index(old)] = no
                swap = {'added': no, 'removed': old,
                        'reasons': incoming['positive_reasons'] + outgoing['negative_reasons'],
                        'rule': '複数領域の好材料＋除外側の懸念＋不確実性区間の厳密優越。最大1頭。'}
                break
            if swap:
                break
    for h in assessed:
        no = str(h['horse_no'])
        if status != 'research_only' or h['observed_subtotal'] is None:
            continue
        if no in c and no not in a:
            h['classification'] = '評価上昇'
        elif no in a and h['negative_reasons']:
            h['classification'] = '正式上位だが慎重'
        elif no in a:
            h['classification'] = '評価維持'
        elif no in b or len(h['positive_domains']) >= 2 and h['negative_reasons']:
            h['classification'] = '消す前に再確認'
    return {'model_version': VERSION, 'status': status, 'race_id': inputs.get('race_id'),
            'evaluated_at': evaluated_at or datetime.now(timezone.utc).isoformat(),
            'prediction_created_at': inputs.get('prediction_created_at'),
            'evaluation_context': inputs.get('evaluation_context', 'fresh_pre_race'),
            'input_hash': digest(inputs), 'inputs': inputs, 'settings': deepcopy(SETTINGS),
            'uncertainty_bounds': dict(BOUNDS), 'common_comparison_domains': common, 'horses': assessed,
            'race_assessment': [f'予測ペース：{pace or "未取得"}／4角想定取得{known_positions}/{len(rows)}頭、前方4番手以内{front}頭',
                                '純能力を基礎に全頭を独立比較。正式スコア・既存位置bonusは加算しない。',
                                '自由5頭は全頭で取得済みの同じ評価軸だけを数値比較。欠損軸は全頭一律で比較から外し、個別根拠には残す。',
                                '全頭で比較できる材料：純能力 / ' + (' / '.join({'position': '4角想定とペース', 'condition': '距離・コース・★・☆', 'training': '調教'}[k] for k in common) or '追加材料なし'),
                                '保護案は欠損を含む評価区間でも優越する場合のみ。購入推奨ではない。'],
            'A': a, 'B': b, 'C': c, 'swap': swap,
            'selection_status': 'ok' if valid_a and b else '正式Top5または評価材料不足・5頭案未確定',
            'comparison': {label: {'added': [n for n in nums if n not in a], 'removed': [n for n in a if n not in nums]}
                           for label, nums in [('B', b), ('C', c)] if nums},
            'protection_reason': swap['rule'] if swap else '根拠の組合せ／不確実性を越える優越が足りないため交換0頭'}


def attach_practical_shadow(result):
    """Called only after fresh formal generation; loaded predictions never replay."""
    if result.race_mode != 'jra' or getattr(result, '_jra_snapshot_restored', False) or KEY in (result.debug_info or {}):
        return result
    from .jra_practical_inputs import practical_inputs
    try:
        payload = evaluate_practical_shadow(practical_inputs(result))
    except (ValueError, TypeError, KeyError) as exc:
        payload = {'model_version': VERSION, 'status': 'input_error', 'reason': str(exc), 'horses': []}
    result.debug_info = {**(result.debug_info or {}), KEY: payload}
    return result


def practical_snapshot(result):
    saved = (result.debug_info or {}).get(KEY)
    return {KEY: deepcopy(saved)} if result.race_mode == 'jra' and isinstance(saved, dict) else {}
