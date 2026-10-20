"""Offline audit of the six supplied course-statistics HTMLs. No network."""
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup

KINDS = {('courseanalysis','0'):'frame',('courseanalysis','1'):'style',
         ('courseanalysis','2'):'jockey',('courseanalysis','3'):'trainer',
         ('coursedata','1'):'sire',('coursedata','4'):'damsire'}
HEADERS=['馬番','印','項目','1着','2着','3着','4着以下','出走回数','勝率','連対率','複勝率','単勝回収率','複勝回収率','馬名']

def parse(path):
    raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    try: decoded=raw.decode('utf-8-sig')
    except UnicodeDecodeError: decoded=raw
    soup=BeautifulSoup(decoded,'html.parser')
    meta=soup.select_one('meta[property="og:url"]')
    if not meta: raise ValueError('source_url_missing')
    url=meta.get('content',''); query=parse_qs(urlparse(url).query)
    kind=KINDS.get((query.get('mode',[''])[0],query.get('cid',[''])[0]))
    if kind is None: raise ValueError('unsupported_kind')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    course=re.search(r'(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉|門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀|帯広)(芝|ダート|ダ|障害|障)(\d+)m',title)
    if not course: raise ValueError('course_not_confirmed')
    host=urlparse(url).hostname
    if host not in ('race.netkeiba.com','nar.netkeiba.com'): raise ValueError('authority_unknown')
    table=soup.select_one('table#table_sort_back')
    if not table: raise ValueError('result_table_missing')
    trs=table.select('tr')
    headers=[re.sub(r'\s','',th.get_text()) for th in trs[0].find_all('th')]
    if headers!=HEADERS: raise ValueError('table_schema_changed')
    period=re.search(r'集計期間[：:]\s*([^\s]+)',soup.get_text(' ',strip=True))
    common=dict(source_path=str(path),source_url=url,source_sha256=digest,
                captured_at=None,parsed_at=datetime.now(timezone.utc).isoformat(),
                period_raw=period[1] if period else None,period_start=None,period_end=None,
                as_of_status='unverified',predictive_validation_eligible=False,
                authority='NAR' if host=='nar.netkeiba.com' else 'JRA',venue=course[1],surface='ダ' if course[2]=='ダート' else course[2],distance=int(course[3]),
                going=None,turn=None,class_filter=None,kind=kind)
    stats={}; links=[]; errors=[]
    for tr in trs[1:]:
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=14: raise ValueError('row_schema_changed')
        vals=[c.get_text(' ',strip=True) for c in cells]
        counts=[int(v.replace(',','')) for v in vals[3:8]]
        wins,second,third,other,starts=counts
        if sum(counts[:4])!=starts: raise ValueError('denominator_mismatch')
        shown=[float(v.rstrip('%')) for v in vals[8:13]]
        calculated=[100*n/starts if starts else None for n in (wins,wins+second,wins+second+third)]
        for label,actual,display in zip(('win','quinella','top3'),calculated,shown[:3]):
            if actual is not None and abs(actual-display)>=1.000001:
                errors.append(dict(horse_no=vals[0],field=label,display=display,recalculated=actual))
        key=vals[2]
        sid=hashlib.sha256((digest+'|'+kind+'|'+key).encode()).hexdigest()
        row={**common,'stat_id':sid,'entity_label':key,'entity_id':None,
             'wins':wins,'second':second,'third':third,'other':other,'starts':starts,
             'top3':wins+second+third,'win_pct_display':shown[0],
             'quinella_pct_display':shown[1],'place_pct_display':shown[2],
             'win_return_pct_display':shown[3],'place_return_pct_display':shown[4],
             'win_pct_recalculated':calculated[0],'top3_pct_recalculated':calculated[2],
             'sample_status':'observed' if starts else 'no_sample'}
        if key in stats and stats[key]!=row: raise ValueError('duplicate_stat_conflict')
        stats[key]=row
        a=cells[13].select_one('a[href*="/horse/"]')
        match=re.search(r'/horse/(\d+)',a.get('href','')) if a else None
        links.append(dict(stat_id=sid,kind=kind,race_id=query.get('race_id',[''])[0],
                          horse_no=int(vals[0]),horse_name=vals[13],horse_id=match[1] if match else None))
    return list(stats.values()),links,errors
