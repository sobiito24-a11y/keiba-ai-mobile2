"""Read-only audit CLI. No app integration; outputs must be a new directory."""
import argparse
import csv
import html
import itertools
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.market_rank_audit import build, digest, metrics, seal, settlement


def csvout(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def run(args):
    out = Path(args.output); out.mkdir(parents=True, exist_ok=False)
    archive = Path(args.archive)
    with zipfile.ZipFile(archive) as z:
        metadata = json.loads(z.read('metadata.json'))
        outcomes = json.loads(z.read('outcomes.json'))
        packets = {r['race_id']: r for r in json.loads(z.read('packets.json'))}
    raw_hashes = {}; snapshots = {}; conflicts = []
    # Only explicitly requested files; no heuristic choice between different versions.
    for name in args.snapshot:
        p = Path(name); raw = p.read_bytes(); raw_hashes[str(p)] = __import__('hashlib').sha256(raw).hexdigest()
        with zipfile.ZipFile(p) as z:
            races = json.loads(z.read('snapshot.json'))['races']
        for r in races:
            rid = str(r['race_id'])
            saved_path = metadata.get(rid, {}).get('path')
            if not saved_path or Path(saved_path.replace('\\\\', '/')).resolve() != p.resolve():
                continue
            if rid in snapshots and digest(snapshots[rid]) != digest(r):
                conflicts.append(rid)
            else:
                snapshots[rid] = r
    if conflicts:
        raise ValueError('conflicting source snapshots: '+','.join(sorted(set(conflicts))))
    reports = []; details = []; audits = []; bets = []; candidate_rows = []; exclusions = []
    for rid, outcome in outcomes.items():
        if rid not in snapshots or rid not in metadata:
            exclusions.append(dict(race_id=rid, reason='source_snapshot_or_metadata_missing')); continue
        r = snapshots[rid]; m = metadata[rid]
        hs = r['horses']; nos = {int(h['horse_no']) for h in hs}
        finishes = outcome.get('finishes', {})
        if not outcome.get('confirmed') or any(finishes.get(str(n)) is None for n in nos):
            exclusions.append(dict(race_id=rid, reason='incomplete_confirmed_finishes')); continue
        features = {int(h['horse_no']): h for h in packets.get(rid, {}).get('horses', [])}
        saved_formal = r.get('prediction_result', {}).get('debug_info', {}).get('jra_formal_comparison_snapshot', {})
        parts = {int(h.get('number',h.get('horse_no',0))): h for h in saved_formal.get('rows', [])}
        rows = []
        for h in hs:
            no = int(h['horse_no']); saved = m['horses'].get(str(no), {})
            x = dict(features.get(no, {}), horse_no=no, name=h.get('horse_name', h.get('name')),
                     formal_rank=saved.get('formal_rank'), pure_rank=saved.get('pure_rank'),
                     formal_mark=saved.get('formal_mark'), formal_rank_source=saved.get('formal_rank_source'),
                     odds=str(h.get('odds_at_prediction', '')).replace('倍','').strip(), style=saved.get('style'), pace=saved.get('pace'))
            # Never import reference-replayed components or use mismatched saved rank versions.
            p = parts.get(no, {})
            if p.get('jra_top5_rank') == saved.get('formal_rank'):
                x['formal_score'] = p.get('jra_top5_score')
                x['pure'] = p.get('jra_pure_ability_score')
                for key in ('formal_score', 'pace_bonus', 'position_bonus', 'repro_bonus', 'training_bonus', 'state_bonus'):
                    if key != 'formal_score':
                        x[key] = p.get('jra_'+key)
            rows.append(x)
        meta = dict(date=r['date'], venue=r['venue'], distance=m.get('distance'), discipline='jump' if m.get('surface') == '障' else 'flat',
                    prediction_version=m.get('version'), prediction_created_at=m.get('created_at'),
                    odds_observed_at=None, odds_source='saved_odds_at_prediction', post_time=m.get('post_time'),
                    source_hash=digest(r), result_seen=True, split='historical_exploration')
        report = build(rid, r['race_mode'], rows, meta)
        orders = report['orders']
        if not all(k in orders for k in ('formal', 'pure', 'market')) or len(nos) < 5:
            exclusions.append(dict(race_id=rid, reason=json.dumps(report['unavailable'], ensure_ascii=False))); continue
        # Preserve historical rank<=5 membership and reject ambiguous Top5 boundaries.
        if any(sum(1 for h in rows if h.get(k) is not None and h[k] <= 5) != 5 for k in ('formal_rank', 'pure_rank')):
            exclusions.append(dict(race_id=rid, reason='non_five_saved_top5_boundary')); continue
        reports.append(report)
        base = dict(race_id=rid, date=r['date'], mode=r['race_mode'], venue=r['venue'], distance=m.get('distance'), field_size=len(nos))
        winners = {int(n) for n, f in finishes.items() if f == 1}
        top3 = {int(n) for n, f in finishes.items() if f is not None and f <= 3}
        for label, order in orders.items():
            picks = set(order[:5])
            details.append(dict(base, method=label, picks='-'.join(map(str, order[:5])), winner_caught=int(bool(picks&winners)),
                                top3_count=len(picks&top3), first_win=int(order[0] in winners), first_top3=int(order[0] in top3)))
        by = {h['horse_no']: h for h in report['inputs']['horses']}
        market = {n: 1+sum(by[k]['odds']<by[n]['odds'] for k in nos) for n in nos}
        strong = [n for n in orders['formal'] if by[n]['formal_rank'] <= (1 if r['race_mode']=='jra' else 2)
                  and by[n]['pure_rank'] <= (1 if r['race_mode']=='jra' else 2)][:2]
        value = sorted([n for n in nos if 2 <= by[n]['formal_rank'] <= 5 and by[n]['pure_rank'] <= 4
                        and 8 <= by[n]['odds'] <= 35 and market[n] >= 4],
                       key=lambda n: (-(market[n]-by[n]['pure_rank']), by[n]['formal_rank'], n))[:2]
        candidate_rows.append(dict(base, strong=strong, value=value, overlap=len(set(strong)&set(value)),
                                   both_present=bool(strong and value), neither=not(strong or value),
                                   strong_top3=len(set(strong)&top3), value_top3=len(set(value)&top3),
                                   strong_count=len(strong), value_count=len(value)))
        for h in report['audit']:
            if (h['market_rank'] <= 3 and h['formal_rank'] >= 6) or (h['horse_no'] in winners and h['market_rank'] <= 5 and h['formal_rank'] > 5):
                audits.append(dict(base, **h, finish=finishes[str(h['horse_no'])],
                                   market_only_winner=h['horse_no'] in winners and h['market_rank']<=5 and h['formal_rank']>5))
        policies = {label: order for label, order in orders.items()}
        # Predeclared comparators, no optimization by the outcome.
        pairs = {'strong_value': [(a,b) for a in strong for b in value if a!=b]}
        for partner in ('formal', 'pure', 'market'):
            pairs[partner+'_value'] = [(orders[partner][0], b) for b in value if orders[partner][0]!=b]
        for label, order in policies.items():
            pairs[label+'_top5_pairs'] = list(itertools.combinations(order[:5], 2))
        outcome = dict(outcome, place_places=3 if len(nos)>=8 else 2 if len(nos)>=5 else None)
        for label, order in policies.items():
            for limit in (1, 2, 5):
                for no in order[:limit]:
                    for kind in ('win','place'):
                        s = settlement(kind, [no], outcome)
                        bets.append(dict(base, policy=label, limit=str(limit), kind=kind, horses=str(no), cost=100, **s))
        for label, ps in pairs.items():
            # Undirected tickets deduped; exacta retains ordered anchor -> value.
            for kind in ('wide','quinella','exacta'):
                sequence = list(dict.fromkeys(tuple(p) if kind=='exacta' else tuple(sorted(p)) for p in ps))
                for limit in ('1','2','all'):
                    for pair in sequence if limit=='all' else sequence[:int(limit)]:
                        s = settlement(kind, pair, outcome)
                        bets.append(dict(base, policy=label, limit=limit, kind=kind, horses='-'.join(map(str,pair)), cost=100, **s))
    totals = Counter(r['inputs']['mode'] for r in reports)
    summary = []
    for mode in totals:
        for method in sorted({d['method'] for d in details if d['mode']==mode}):
            ds=[d for d in details if d['mode']==mode and d['method']==method]
            summary.append(dict(mode=mode, method=method, races=len(ds), winner_caught=sum(d['winner_caught'] for d in ds),
                                top3_two=sum(d['top3_count']>=2 for d in ds),top3_all=sum(d['top3_count']==3 for d in ds),
                                top3_horses=sum(d['top3_count'] for d in ds),first_win=sum(d['first_win'] for d in ds),first_top3=sum(d['first_top3'] for d in ds)))
    groups=defaultdict(list)
    for b in bets:
        for split, val in (('all','all'),('date',b['date']),('venue',b['venue'])):
            groups[(b['mode'],b['policy'],b['limit'],b['kind'],split,val)].append(b)
    stats=[]
    for (mode,policy,limit,kind,split,val), bs in groups.items():
        pool=[r for r in reports if r['inputs']['mode']==mode and (split=='all' or r['inputs']['metadata'][split]==val)]
        method=policy.removesuffix('_top5_pairs')
        eligible=[r for r in pool if not method.startswith('position_') or method in r['orders']]
        stats.append(dict(mode=mode,policy=policy,limit=limit,kind=kind,split=split,split_value=val,
                          unavailable_races=len(pool)-len(eligible),**metrics(bs,len(eligible))))
    strata=[]
    for column in ('date','venue','distance','field_size'):
        buckets=defaultdict(list)
        for d in details:buckets[(d['mode'],d['method'],d[column])].append(d)
        for (mode,method,value),ds in buckets.items():
            strata.append(dict(mode=mode,method=method,stratum=column,value=value,races=len(ds),
                               winners=sum(d['winner_caught'] for d in ds),top3_two=sum(d['top3_count']>=2 for d in ds),
                               top3_all=sum(d['top3_count']==3 for d in ds)))
    csvout(out/'strata.csv',strata)
    for name, data in [('comparison',summary),('races',details),('horse_audit',audits),('candidates',candidate_rows),
                       ('tickets',bets),('returns',stats),('exclusions',exclusions)]:
        csvout(out/(name+'.csv'),data)
    (out/'research_predictions.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    # Reference CSV comparison is an independent aggregate check, not raw provenance proof.
    reference=[]
    if args.reference:
        with Path(args.reference).open(encoding='utf-8-sig') as f:
            for rr in csv.DictReader(f):
                rid=rr['race_id']; actual=next((r for r in reports if r['inputs']['race_id']==rid),None)
                reference.append(dict(race_id=rid, available=actual is not None,
                                      matches=actual is not None and all('-'.join(map(str,actual['orders'][k][:5]))==rr[k+'_top5'] for k in ('formal','pure','market'))))
        csvout(out/'reference_check.csv',reference)
    manifest=dict(version='market_rank_audit_v1_20261016',counts=dict(totals),reference_matched=sum(r['matches'] for r in reference),
                  reference_total=len(reference),input_hashes=raw_hashes,archive_hash=__import__('hashlib').sha256(archive.read_bytes()).hexdigest(),
                  historical_only=True,unseen_races=0,odds_time_unknown=True)
    for p,h in raw_hashes.items():
        assert __import__('hashlib').sha256(Path(p).read_bytes()).hexdigest()==h
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    body='<meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>body{background:#101c30;color:#fff;font:16px sans-serif;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{padding:10px;border:1px solid #567}</style><h1>順位・市場比較（研究専用）</h1><p>全件過去探索。保存オッズの観測時刻不明。正式予想は変更していません。</p>'
    for s in summary:
        body+='<p>'+html.escape(str(s))+'</p>'
    for a in audits:
        body+='<details><summary>'+html.escape(str(a['race_id'])+' '+str(a['horse_no'])+' '+str(a['name']))+'</summary><pre>'+html.escape(json.dumps(a,ensure_ascii=False,indent=2))+'</pre></details>'
    (out/'audit.html').write_text(body,encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True);p.add_argument('--snapshot',action='append',required=True)
    p.add_argument('--reference');p.add_argument('--output',required=True)
    run(p.parse_args())
