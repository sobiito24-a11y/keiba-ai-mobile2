"""V3 research inputs: identity-checked, field-level historical evidence.

Only past-run blocks/header fields are accepted; current outcomes/odds are not
inputs. The v1 and class-split adapters intentionally remain frozen.
"""
import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone
from bs4 import BeautifulSoup
from .class_context import text, header_evidence, class_history
from .newspaper_v2_inputs import horse_no, recent_runs, number
from .newspaper_v2_class_inputs import classify_previous, comparison_blockers, finish_quality
from .newspaper_v2_class_revision import evaluate_class_revision, rank_payload

def conservative_class(evidence):
    ctx=classify_previous(evidence)
    raw=' '.join(str(evidence.get(k) or '') for k in ('race_name','race_data2','class_badge_raw'))
    if ctx['class_family']=='NAR':
        # C3/C4 and similar mixed classes are not a single comparable level.
        labels=set(re.findall(r'([ABC][1-9])', text(raw)))
        if len(labels)>1 or any(int(v[1:])>3 for v in labels):
            ctx['class_level_v2']=None
            ctx['class_confidence_v2']='mixed_or_unmapped'
        elif not labels and re.search(r'[ABC]',text(raw)):
            # A truncated newspaper name such as 3歳以上C is insufficient.
            ctx['class_level_v2']=None
            ctx['class_confidence_v2']='abbreviated_class_unresolved'
    return ctx


VERSION = 'newspaper_shadow_v3_input_enriched'
FIELDS = ('race_id','date','venue','race_number','horse_id','past_horse_no',
          'race_name','surface','distance','turn','finish','head_count','time_index',
          'class_badge_raw','race_data2','race_grade','data04_raw','data05_raw')


def json_value(value):
    """Keep structured audit serializable without rewriting source objects."""
    if isinstance(value,dict):return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_value(v) for v in value]
    if isinstance(value,date):return value.isoformat()
    if isinstance(value,float) and number(value) is None:return None
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def valid_id(value):
    return str(value) if re.fullmatch(r'20\d{10}',str(value or '')) else None


def full_date(value):
    try:
        return date.fromisoformat(str(value).split('T')[0]).isoformat()
    except ValueError:
        return None


def present(value):
    return value is not None and str(value).strip() not in ('','None','nan','—')


def saved_runs(row):
    raw=row.get('_past_runs') or row.get('past_runs') or []
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except ValueError:raw=[]
    raw=[r for r in raw if isinstance(r,dict)] if isinstance(raw,list) else []
    output=[]
    for normalized in recent_runs(row):
        label=normalized.get('label')
        candidates=[r for r in raw if r.get('label')==label or r.get('key')=={'前走':'race1','2走前':'race2','3走前':'race3'}.get(label)]
        r=candidates[0] if len(candidates)==1 else {}
        value={k:normalized.get(k) for k in FIELDS}
        aliases={'race_id':('race_id',),'date':('race_date','date'),'venue':('racecourse','venue'),
                 'race_number':('race_number',),'horse_id':('horse_id',),'past_horse_no':('horse_no',),
                 'race_name':('race_name',),'surface':('surface',),'distance':('distance',),
                 'turn':('direction','turn'),'time_index':('value','time_index'),
                 'race_data2':('race_data2','class_raw_text')}
        for key,keys in aliases.items():
            found=next((r[k] for k in keys if present(r.get(k))),None)
            if found is not None:value[key]=found
        value['race_id']=valid_id(value.get('race_id'))
        value['date']=full_date(value.get('date'))
        if value['race_id']:value['race_number']=int(value['race_id'][-2:])
        from .newspaper_v2_engine import run_number
        value['finish']=run_number(value.get('finish'))
        value['label']=label
        # Do not trust legacy inferred class_label/class_rank as explicit evidence.
        value['source']='snapshot_past_run'
        value['raw']=copy.deepcopy({k:r[k] for k in r if k in set(FIELDS)|{'race_date','racecourse','value','position','class_label','class_rank','url'}})
        output.append(json_value(value))
    return output


def newspaper_runs(html):
    output={}
    for horse in BeautifulSoup(html or '', 'lxml').select('dl.HorseList'):
        node=horse.select_one('.Waku_Horse');no=horse_no({'horse_no':node.get_text(strip=True) if node else None})
        if not no or no in output:raise ValueError('enrichment: duplicate/missing horse number')
        output[no]=[]
        hl=horse.select_one('a[href*="/horse/"]')
        hm=re.search(r'/horse/(\d+)',hl.get('href','')) if hl else None
        for label,past in zip(('前走','2走前','3走前'),horse.select('.Past_Wrapper li.Past')[:3]):
            def t(selector):
                n=past.select_one(selector)
                return text(n.get_text(' ',strip=True)) if n else ''
            links=[a.get('href','') for a in past.select('a[href]')]
            ids=set(m[1] for link in links if (m:=re.search(r'(?:/race/|race_id=)(20\d{10})',link)))
            rid=next(iter(ids)) if len(ids)==1 else None
            day=re.search(r'(\d{1,2})/(\d{1,2})\s+([^\s\d]+)\s*(\d+)R',t('.Data01'))
            cond=re.search(r'(芝|ダ|障)\s*(\d{3,4})',t('.Data09'))
            count=re.fullmatch(r'(\d+)\s*頭',t('.Data05'))
            finish=re.fullmatch(r'(\d+)(?:着)?',t('.Data04 .Num'))
            first=past.select_one('.PastDataLine')
            badges=' / '.join(text(n.get_text(' ',strip=True)) for n in first.select('.Icon_GradeType')) if first else ''
            grade=None
            if first:
                for icon in first.select('.Icon_GradeType'):
                    match=re.search(r'(?:^| )Icon_GradeType([123])(?: |$)',' '.join(icon.get('class',[])))
                    if match:grade='G'+match[1];break
            raw={f'Data{x:02}':t(f'.Data{x:02}') for x in (1,3,4,5,6,9,10)}
            output[no].append(dict(label=label,race_id=rid,
                date=full_date(f'{rid[:4]}-{int(day[1]):02}-{int(day[2]):02}') if rid and day else None,
                venue=day[3] if day else None,race_number=int(day[4]) if day else None,
                horse_id=hm[1] if hm else None,past_horse_no=number(re.sub(r'番$','',t('.Data06'))),
                race_name=t('.RaceName'),surface=cond[1] if cond else None,distance=int(cond[2]) if cond else None,
                turn=t('.Data10'),finish=int(finish[1]) if finish else None,head_count=int(count[1]) if count else None,
                class_badge_raw=badges,race_grade=grade,race_data2=t('.Data03'),data04_raw=t('.Data04 .Num'),data05_raw=t('.Data05'),
                source='newspaper_past_block',raw=raw,identity_conflict=len(ids)>1))
    return output


def identity(a,b):
    """IDs take priority but contradictory explicit identity always blocks merge."""
    conflicts=[]
    for key in ('race_id','date','venue','race_number','surface','distance','horse_id','past_horse_no'):
        x,y=a.get(key),b.get(key)
        if key in ('distance','race_number','past_horse_no'):
            x=number(re.sub(r'm$','',str(x))) if present(x) else None
            y=number(re.sub(r'm$','',str(y))) if present(y) else None
        if present(x) and present(y) and str(x)!=str(y):conflicts.append(key)
    if a.get('identity_conflict') or b.get('identity_conflict'):conflicts.append('race_id_conflict')
    if conflicts:return 'conflict',conflicts
    if valid_id(a.get('race_id')) and a.get('race_id')==b.get('race_id'):return 'race_id',[]
    required=('date','venue','race_number','surface','distance')
    if all(present(a.get(k)) and present(b.get(k)) for k in required) and full_date(a['date']) and (present(a.get('horse_id')) and a.get('horse_id')==b.get('horse_id') or present(a.get('past_horse_no')) and a.get('past_horse_no')==b.get('past_horse_no')):
        return 'composite',[]
    return 'unmatched',[]


def merge_run(saved, newspaper, header=None, acquired_at=None):
    status,conflicts=identity(saved,newspaper) if saved else ('html_only',[])
    # Independent HTML evidence can stand on its own; unmatched saved evidence is
    # retained in the audit, never attached to a different run.
    sources=[newspaper] if newspaper else [saved]
    if status in ('race_id','composite'):sources=[saved,newspaper]
    values={};provenance={};field_conflicts=[]
    for source in sources:
        for key in FIELDS:
            value=source.get(key)
            if not present(value):continue
            previous=values.get(key)
            if present(previous) and previous!=value:
                # Expanded snapshot name can supply explicit age, provided class
                # agrees with the independently scoped newspaper badge.
                if key in ('race_name','race_data2'):
                    continue
                if key not in ('turn','data04_raw','data05_raw','finish'):field_conflicts.append(key)
            values[key]=value
            provenance[key]={'raw':value,'normalized':value,'source':source.get('source'),
                             'status':'observed','acquired_at':source.get('acquired_at',acquired_at),'confidence':'explicit_saved_evidence','input_hash':digest(source)}
    header_conflicts=[]
    if header and header.get('race_id')==values.get('race_id'):
        for key in ('date','venue','surface'):
            if present(header.get(key)) and present(values.get(key)) and header[key]!=values[key]:header_conflicts.append('header_'+key)
    if header and header.get('race_id')==values.get('race_id') and not header_conflicts:
        for key in ('race_name','race_data2','race_grade','surface','venue','date'):
            if present(header.get(key)):
                values[key]=header[key];provenance[key]={'raw':header[key],'normalized':header[key],
                    'source':header.get('source'),'status':'header_observed','acquired_at':header.get('acquired_at'),
                    'input_hash':header.get('input_hash'),'confidence':'explicit_header'}
    values['surface']=values.get('surface') or newspaper.get('surface')
    ctx=conservative_class(values)
    htmlctx=conservative_class(newspaper)
    if ctx.get('class_level_v2') is not None and htmlctx.get('class_level_v2') is not None and ctx['class_level_v2']!=htmlctx['class_level_v2']:
        field_conflicts.append('class_level')
    audit={'status':status,'identity_conflicts':conflicts,'field_conflicts':sorted(set(field_conflicts+header_conflicts)),
           'saved':saved,'newspaper':newspaper,'header':header,'fields':provenance}
    return {'values':values,'class_context':ctx,'audit':audit,'input_hash':digest(audit)}


def enriched_runs(row, newspaper, headers=None, target_date=None, acquired_at=None):
    saved=saved_runs(row);out=[]
    for run in newspaper or saved:
        candidates=[s for s in saved if identity(s,run)[0] in ('race_id','composite')]
        fallback=next((s for s in saved if s.get('label')==run.get('label')),None)
        match=candidates[0] if len(candidates)==1 else {} if len(candidates)>1 else fallback
        merged=merge_run(match or {},run,(headers or {}).get(run.get('race_id')),acquired_at)
        dt=full_date(merged['values'].get('date'));target=full_date(target_date)
        merged['audit']['temporal_status']='prior_race' if dt and target and dt<target else 'not_prior' if dt and target else 'unverified'
        if len(candidates)>1:
            merged['audit']['identity_conflicts'].append('multiple_saved_matches')
            merged['audit']['ambiguous_saved_candidates']=copy.deepcopy(candidates)
        merged['input_hash']=digest(merged['audit'])
        out.append(merged)
    return out[:3]


def evaluate_enriched(rows,info,mode,*,html='',base_v1=None,base_split=None,headers=None,acquired_at=None,race_identifier='',evaluated_at=None):
    split=base_split or evaluate_class_revision(rows,info,mode,html=html,base_v1=base_v1,race_identifier=race_identifier)
    out=copy.deepcopy(split);p=mode+'_v2_';by={horse_no(r):r for r in rows};news=newspaper_runs(html)
    out['model_version']=mode+'_'+VERSION
    out['parent_model_version']=split['model_version']
    out['evaluated_at']=evaluated_at or datetime.now(timezone.utc).isoformat()
    out['parent_evaluated_at']=split.get('evaluated_at')
    out['usage']='input_enrichment_reference_recalculation_not_formal'
    for h in out['horses']:
        runs=enriched_runs(by[h['horse_no']],news.get(h['horse_no'],[]),headers,info.get('race_date'),acquired_at)
        h['structured_recent_runs']=runs
        previous=runs[0] if runs else None
        ev=previous['values'] if previous else {}
        ctx=previous['class_context'] if previous else classify_previous({})
        current_ev={'race_name':h['class_context'].get('class_raw_v2'),'venue':info.get('racecourse'),'surface':info.get('surface'),'race_grade':h['class_context'].get('class_grade_raw_v2')}
        current_header=(headers or {}).get(race_identifier or out.get('race_id'))
        if current_header and current_header.get('date')==full_date(info.get('race_date')) and current_header.get('venue')==info.get('racecourse'):
            current_ev={**current_ev,**{k:current_header[k] for k in ('race_name','race_data2','surface','venue','race_grade') if present(current_header.get(k))}}
        current=conservative_class(current_ev)
        h['enriched_current_class']=current
        h['enriched_current_evidence']={'values':current_ev,'header':copy.deepcopy(current_header),'input_hash':digest(current_ev)}
        flags=comparison_blockers(current,ctx)
        if previous:
            audit=previous['audit']
            if audit['identity_conflicts'] or audit['field_conflicts']:flags.append('input_conflict')
            if audit['temporal_status']!='prior_race':flags.append('past_date_not_verified')
        else:flags.append('previous_run_missing')
        a,af=finish_quality(ev)
        if previous and previous['audit']['temporal_status']=='not_prior':
            a=None;af.append('not_a_prior_race')
        b=None if flags else max(-1.,min(1.,(ctx['class_level_v2']-current['class_level_v2'])/(1 if mode=='jra' else 3)))
        olda=h[p+'finish_quality_score'];oldb=h[p+'class_change_score']
        for purpose,w in out['coefficients'].items():
            k=p+purpose+'_candidate_score'
            if h[k] is not None:h[k]+=((a or 0)-(olda or 0))*w['finish_quality']+((b or 0)-(oldb or 0))*w['class_change']
        h[p+'finish_quality_score']=a;h[p+'class_change_score']=b
        h['input_enrichment']={'previous_class':ctx,'finish_flags':af,'transition_flags':flags,'old_a':olda,'old_b':oldb,'a':a,'b':b}
        history=[]
        for r in runs:
            context=copy.deepcopy(r['class_context'])
            if r['audit']['temporal_status']!='prior_race' or r['audit']['identity_conflicts'] or r['audit']['field_conflicts']:
                context['comparable_class_group_v2']=''
            history.append({'class':context,'finish':number(r['values'].get('finish'))})
        # Never promote an older run into the previous-run slot when the actual
        # previous run is unverified.
        h['enriched_class_history']=class_history(current,history)
        missing=[s for s in h[p+'missing_reasons'] if not s.startswith(('着順の質:','クラス変化:'))]
        missing += ['着順の質: '+s for s in af]+['クラス変化: '+s for s in flags]
        h[p+'missing_reasons']=missing
        if h[p+'data_quality']!='insufficient':h[p+'data_quality']='partial' if missing else 'complete'
        for kind in ('positive','negative'):
            h[p+kind+'_reasons']=[s for s in h[p+kind+'_reasons'] if not s.startswith(('前走着順の質','比較可能な前走→今回クラス差'))]
        for name,value in [('前走着順の質',a),('比較可能な前走→今回クラス差',b)]:
            if value:h[p+('positive' if value>0 else 'negative')+'_reasons'].append(f'{name} {value:+.2f}')
    out['structured_inputs_hash']=digest([{'past':h['structured_recent_runs'],'current':h['enriched_current_evidence']} for h in out['horses']])
    return rank_payload(out)


def replay_enriched_inputs(payload):
    """Explicit research audit replay, never called by Snapshot restoration.

    Re-evaluate A/B from frozen structured inputs; the remaining components
    are intentionally the parent's frozen component values, not live code.
    """
    if payload.get('model_version') != payload.get('race_mode','')+'_'+VERSION:
        raise ValueError('Not an input-enriched V3 payload')
    out=copy.deepcopy(payload);mode=out['race_mode'];p=mode+'_v2_'
    for h in out['horses']:
        runs=h.get('structured_recent_runs',[]);previous=runs[0] if runs else None
        current=h['enriched_current_class']
        ev=previous['values'] if previous else {}
        context=conservative_class(ev)
        flags=comparison_blockers(current,context)
        if previous:
            audit=previous['audit']
            if audit['identity_conflicts'] or audit['field_conflicts']:flags.append('input_conflict')
            if audit['temporal_status']!='prior_race':flags.append('past_date_not_verified')
        else:flags.append('previous_run_missing')
        a,af=finish_quality(ev)
        if previous and previous['audit']['temporal_status']=='not_prior':a=None
        b=None if flags else max(-1.,min(1.,(context['class_level_v2']-current['class_level_v2'])/(1 if mode=='jra' else 3)))
        for purpose,w in out['coefficients'].items():
            key=p+purpose+'_candidate_score'
            if h[key] is not None:h[key]+=((a or 0)-(h[p+'finish_quality_score'] or 0))*w['finish_quality']+((b or 0)-(h[p+'class_change_score'] or 0))*w['class_change']
        h[p+'finish_quality_score']=a;h[p+'class_change_score']=b
    return rank_payload(out)
