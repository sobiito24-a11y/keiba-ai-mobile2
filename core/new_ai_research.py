"""Offline research only. No imports from production prediction/scoring code."""
from __future__ import annotations
import hashlib,json,math,sqlite3,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path

VERSION='formal_additive_actual_counts_v1'
CONFIG={'version':VERSION,'coefficient_source':'supplied analysis_f_models.py; exact counts version, not proxy',
        'historical_71_matched':False,'JRA':{'prior':.25,'prior_n':40,'scale':20,'corner':2},
        'NAR':{'prior':.25,'prior_n':40,'scale':20,'corner':2},'fit':False}
JST=timezone(timedelta(hours=9))

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def num(x):
    if isinstance(x,bool):return None
    try:
        v=float(x);return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None
def aware(x):
    try:
        d=datetime.fromisoformat(str(x));return d if d.utcoffset() is not None else None
    except ValueError:return None

def read_snapshot(path):
    raw=Path(path).read_bytes()
    with zipfile.ZipFile(__import__('io').BytesIO(raw)) as z:
        if set(z.namelist())!={'manifest.json','snapshot.json'}:raise ValueError('unsupported keiba members')
        body=z.read('snapshot.json');m=json.loads(z.read('manifest.json'))
    if hashlib.sha256(body).hexdigest()!=m['snapshot_sha256']:raise ValueError('snapshot hash mismatch')
    s=json.loads(body)
    if s.get('schema_version')!=1:raise ValueError('unsupported schema')
    return s,hashlib.sha256(raw).hexdigest()

def saved_horses(race):
    """Use saved formal values. Never recompute marks or formal candidate membership."""
    mode=race['race_mode'].upper();mobile=race.get('mobile_snapshot',{})
    form=(mobile.get('jra_formal_comparison_snapshot',{}).get('rows',[]) if mode=='JRA'
          else mobile.get('nar_top5_corner_order',{}).get('horses',[]))
    by={str(x.get('number',x.get('horse_no'))):x for x in form}
    evals={str(x.get('馬番')):x for x in race['prediction_result']['horse_evaluation']['records']}
    mobiles={str(x.get('horse_no')):x for x in mobile.get('horses',[])}
    rows=[]
    for h in race['horses']:
        no=str(h['horse_no']);f=by.get(no,{});e=evals.get(no,{});mh=mobiles.get(no,{})
        rows.append(dict(no=int(no),name=h['horse_name'],formal_rank=num(h.get('jra_top5_rank') if mode=='JRA' else f.get('nar_final_rank')),
            formal_score=num(h.get('jra_top5_score') if mode=='JRA' else f.get('nar_top5_order_score')),
            formal_mark=f.get('mark' if mode=='JRA' else 'nar_final_mark',''),
            ability=num(h.get('ability_value')),corner=num(e.get('netkeiba_corner4_rank')),
            reference={'ability_source':e.get('ability_core_source'),'weight':h.get('weight'),
              'training':h.get('training_short'),'indices':mh.get('indices',{}),'interval':h.get('interval')}))
    if len({h['no'] for h in rows})!=len(rows):raise ValueError('duplicate horse number')
    return rows

def statistics(path,race,horse_rows):
    out={};issues=[]
    if not path or not Path(path).is_file():return out,['研究統計DBがありません']
    by={h['no']:h for h in horse_rows};c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:
        records=c.execute('''SELECT l.*,s.authority,s.kind,s.captured_at,s.capture_timezone,s.period_start,s.period_end,t.payload FROM horse_links l JOIN sources s ON s.hash=l.source_hash JOIN statistics t ON t.cache_key=l.cache_key WHERE l.race_id=? AND s.status='imported' AND s.kind IN ('jockey','style')''',(race['race_id'],)).fetchall()
    finally:c.close()
    groups={}
    for r in records:
        h=by.get(r['horse_no']);p=json.loads(r['payload'])
        if not h or h['name']!=r['horse_name'] or r['authority']!=race['race_mode'].upper() or p['venue']!=race['venue'] or p['distance']!=int(race['distance']) or p['surface']!=race['surface']:
            issues.append('統計との馬・条件不一致');continue
        groups.setdefault((h['no'],r['kind']),[]).append((p,r))
    for key,items in groups.items():
        if len({canonical(p) for p,r in items})!=1:
            out[key]={'status':'conflicting_snapshots'};continue
        p=items[0][0];n=p.get('starts');top=p.get('top3')
        if not isinstance(n,int) or not isinstance(top,int) or n<0 or not 0<=top<=n:
            out[key]={'status':'invalid_denominator'};continue
        out[key]={'status':'observed' if n else 'no_sample','n':n,'top3':top,'entity':p['entity_label'],
           'period_raw':p.get('period_raw'),'statistic_type':'actual_course_counts',
           'evidence':[{'html_sha256':r['source_hash'],'captured_at':r['captured_at'],
             'period_start':r['period_start'],'period_end':r['period_end'],
             'as_of_status':p.get('as_of_status','unverified')} for p,r in items]}
    return out,issues

def correction(stat,cfg):
    if not stat or stat.get('status')!='observed':return None
    p=(stat['top3']+cfg['prior_n']*cfg['prior'])/(stat['n']+cfg['prior_n'])
    return cfg['scale']*(p-cfg['prior'])

def calculate(race,keiba_hash,stats_path,scheduled_at=None):
    mode=race['race_mode'].upper();cfg=CONFIG[mode];horses=saved_horses(race)
    stats,issues=statistics(stats_path,race,horses);models={};n=len(horses)
    names=['A','J_only','F1','F2','F3'] if mode=='JRA' else ['A','NAR_Pure','NAR_P_J','NAR_P_F1','NAR_P_F2','NAR_P_F3']
    for model in names:
        rows=[]
        for h in horses:
            row={**h,'model':model,'contributions':{},'evidence':{},'missing':[],'research_rank':None}
            base=h['formal_score'] if mode=='JRA' else h['ability'];score=base
            if model=='A':score=h['formal_score']
            wants_j=model not in ('A','NAR_Pure');wants_s=model in ('F1','F2','F3','NAR_P_F1','NAR_P_F2','NAR_P_F3')
            for kind,needed in [('jockey',wants_j),('style',wants_s)]:
                if not needed:continue
                st=stats.get((h['no'],kind),{'status':'not_acquired'});delta=correction(st,cfg)
                row['evidence'][kind]=st;row['contributions'][kind]=delta
                if delta is None:row['missing'].append(kind+':'+st['status'])
                elif score is not None:score+=delta
            if model.endswith(('F2','F3')):
                rank=h['corner'];valid=rank is not None and 1<=rank<=n
                group=None;delta=None
                if valid:
                    u=(rank-.5)/n;group='先団' if u<1/3 else '中団' if u<2/3 else '後方'
                    delta=({'先団':cfg['corner'],'中団':0,'後方':-cfg['corner']}[group] if model.endswith('F2') else cfg['corner']*(1-2*(rank-1)/(n-1)) if n>1 else 0)
                row['corner_group']=group;row['contributions']['corner']=delta
                if delta is None:row['missing'].append('corner:unavailable')
                elif score is not None:score+=delta
            if model!='A' and base is None:row['missing'].append('base_score:unavailable')
            row['score']=score if not row['missing'] else None
            rows.append(row)
        complete=all(r['formal_rank'] is not None for r in rows) if model=='A' else all(r['score'] is not None for r in rows)
        if complete:
            ordered=sorted(rows,key=lambda r:(r['formal_rank'] if model=='A' else -r['score'],r['formal_rank'] or float('inf'),r['no']))
            for i,r in enumerate(ordered,1):r['research_rank']=r['formal_rank'] if model=='A' else i
        for r in rows:
            r['rank_change']=r['formal_rank']-r['research_rank'] if r['formal_rank'] is not None and r['research_rank'] is not None else None
            r['new_top5']=r['research_rank'] is not None and r['research_rank']<=5 and r['formal_rank'] is not None and r['formal_rank']>5
        models[model]={'complete':complete,'rows':rows}
    info=race.get('mobile_snapshot',{}).get('race_info',{})
    schedule=scheduled_at
    if schedule is None:
        t=info.get('post_time')
        if t and __import__('re').fullmatch(r'\d{1,2}:\d{2}',str(t)):schedule=race['date']+'T'+str(t).zfill(5)+':00+09:00'
    if schedule is not None and aware(schedule) is None:raise ValueError('scheduled_at needs timezone offset')
    if schedule and aware(schedule).astimezone(JST).date().isoformat()!=race['date']:raise ValueError('schedule date does not match race')
    return {'authority':mode,'race_id':race['race_id'],'race_date':race['date'],'scheduled_at':schedule,
      'schedule_source':'explicit_or_saved_post_time','keiba_sha256':keiba_hash,'version':VERSION,
      'definition':'saved_formal_real_additive' if mode=='JRA' else 'pure_ability_reference_NOT_formal_score_additive',
      'config':CONFIG,'config_sha256':digest(CONFIG),'models':models,'issues':issues,
      'time_status':'探索用・発走前時点未確認','historical_71_status':'固定係数一致・71R代理脚質とは別版'}

def freeze(report,path,now=None):
    """Append-only, deterministic input identity; no overwrite on repeated execution."""
    now=now or datetime.now(JST)
    if now.utcoffset() is None:raise ValueError('aware saved time required')
    identity=digest(report);payload={**report,'input_sha256':identity,'saved_at':now.astimezone(JST).isoformat()}
    # Conservative eligibility gate: all data evidence must be explicitly time verified.
    start=aware(report['scheduled_at']);ev=[e for m in report['models'].values() for r in m['rows'] for st in r['evidence'].values() for e in st.get('evidence',[])]
    verified=bool(ev) and all(e.get('as_of_status')=='verified' and aware(e.get('captured_at')) and aware(e.get('period_end')) and aware(e['captured_at'])<=now and aware(e['period_end'])<=now for e in ev)
    payload['eligible_pre_race']=bool(start and now<start and verified and all(m['complete'] for m in report['models'].values()))
    payload['time_status']='発走前固定・時点検証済み' if payload['eligible_pre_race'] else '探索用・発走前時点未確認'
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path)
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS new_ai_frozen(input_hash TEXT PRIMARY KEY,race_id TEXT,saved_at TEXT,payload TEXT,payload_hash TEXT);
        CREATE TRIGGER IF NOT EXISTS new_ai_no_update BEFORE UPDATE ON new_ai_frozen BEGIN SELECT RAISE(ABORT,'immutable research prediction'); END;
        CREATE TRIGGER IF NOT EXISTS new_ai_no_delete BEFORE DELETE ON new_ai_frozen BEGIN SELECT RAISE(ABORT,'immutable research prediction'); END;''')
        with c:c.execute('INSERT OR IGNORE INTO new_ai_frozen VALUES (?,?,?,?,?)',(identity,report['race_id'],payload['saved_at'],canonical(payload),digest(payload)))
        raw,h=c.execute('SELECT payload,payload_hash FROM new_ai_frozen WHERE input_hash=?',(identity,)).fetchone()
        frozen=json.loads(raw)
        if digest(frozen)!=h:raise ValueError('frozen payload integrity mismatch')
        return frozen
    finally:c.close()
