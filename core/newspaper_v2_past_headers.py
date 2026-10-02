"""Race-ID keyed explicit historical header cache for V3 research only."""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from .class_context import header_evidence, text
from .newspaper_v2_enrichment import valid_id, digest, full_date


def parse_header(html,race_id,*,source,acquired_at=None,known_info=None):
    """Never reads result table, odds/popularity or current horse outcome."""
    if not valid_id(race_id):return None
    soup=BeautifulSoup(html,'lxml')
    canonical=soup.select_one('link[rel="canonical"]')
    og=soup.select_one('meta[property="og:url"]')
    urls=[n.get('href') or n.get('content') or '' for n in (canonical,og) if n]
    ids={m[1] for url in urls if (m:=re.search(r'(?:race_id=|/race/)(20\d{10})',url))}
    if ids!={race_id}:return None
    info=known_info or {}
    nodes=[soup.select_one(s) for s in ('.RaceData01','.RaceData02','.data_intro .racedata','.data_intro .smalltxt')]
    raw=' / '.join(text(n.get_text(' ',strip=True)) for n in nodes if n)
    if not raw:return None
    name=soup.select_one('.RaceName,.data_intro h1')
    name=text(name.get_text(' ',strip=True)) if name else ''
    _,grade,_=header_evidence({},html)
    dt=re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日',raw)
    day=full_date(f'{dt[1]}-{int(dt[2]):02}-{int(dt[3]):02}') if dt else full_date(info.get('race_date'))
    venue=info.get('racecourse')
    if not venue:
        from .newspaper_v2_class_inputs import JRA_VENUES,NAR_VENUES
        venues=[v for v in JRA_VENUES|NAR_VENUES if v in raw]
        venue=venues[0] if len(venues)==1 else None
    surface=re.search(r'障|芝|ダート|ダ',raw)
    return dict(race_id=race_id,date=day,venue=venue,race_name=name,race_data2=raw,
                race_grade=grade,surface=surface[0].replace('ダート','ダ') if surface else None,
                source=source,acquired_at=acquired_at,input_hash=digest(html),status='explicit_header')


class PastHeaderCache:
    """Local first, optional public HTTP; one attempt per ID per instance.

    A failed response is recorded, never interpreted as an empty/normal class.
    The caller opts in to HTTP. Snapshot restore never creates this collector.
    """
    def __init__(self,directory,allow_http=False):
        self.directory=Path(directory);self.allow_http=allow_http;self.memory={};self.audit=[]

    def get(self,race_id):
        if not valid_id(race_id):return None
        if race_id in self.memory:return self.memory[race_id]
        path=self.directory/(race_id+'.json')
        if path.is_file():
            value=json.loads(path.read_text(encoding='utf-8-sig'))
            if value.get('race_id')==race_id:
                self.memory[race_id]=value;return value
        self.memory[race_id]=None
        if not self.allow_http:return None
        import requests
        url=f'https://db.netkeiba.com/race/{race_id}/'
        now=datetime.now(timezone.utc).isoformat()
        entry={'race_id':race_id,'url':url,'acquired_at':now}
        try:
            response=requests.get(url,timeout=15)
            entry['http_status']=response.status_code
            if response.status_code==200:
                response.encoding=response.apparent_encoding
                value=parse_header(response.text,race_id,source=url,acquired_at=now)
                if value:
                    self.directory.mkdir(parents=True,exist_ok=True)
                    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
                    self.memory[race_id]=value
            entry['status']='explicit_header' if self.memory[race_id] else 'header_unavailable'
        except requests.RequestException as exc:entry['status']=type(exc).__name__
        self.audit.append(entry)
        return self.memory[race_id]

NAR_ID_VENUES = {'30':'門別','31':'盛岡','35':'盛岡','36':'水沢','42':'浦和','43':'船橋','44':'大井','45':'川崎','46':'金沢','47':'笠松','48':'名古屋','50':'園田','51':'姫路','54':'高知','55':'佐賀'}

NAR_BABA = {'門別':36,'水沢':11,'盛岡':10,'浦和':18,'船橋':19,'大井':20,'川崎':21,'金沢':22,'笠松':23,'名古屋':24,'園田':27,'姫路':28,'高知':31,'佐賀':32,'帯広':3}


def parse_nar_official_header(html,run,*,source,acquired_at=None):
    """Select race header ONLY, validate date/venue/R; never result rows."""
    rid=valid_id(run.get('race_id'));day=full_date(run.get('date'));venue=run.get('venue')
    if not rid or not day or venue not in NAR_BABA:return None
    if rid[:4]+rid[6:10]!=day.replace('-','') or NAR_ID_VENUES.get(rid[4:6])!=venue:return None
    soup=BeautifulSoup(html,'lxml')
    compact=lambda v:re.sub(r'\s+','',text(v))
    y,m,d=map(int,day.split('-'));no=int(rid[-2:])
    heading=next((h for h in soup.select('h4') if f'{y}年{m}月{d}日' in compact(h.get_text()) and venue in compact(h.get_text()) and f'第{no}競走' in compact(h.get_text())),None)
    title=soup.select_one('section.raceTitle')
    if heading is None or title is None:return None
    name=title.select_one('h3');data=title.select_one('.dataArea li')
    if name is None or data is None:return None
    raw=text(data.get_text(' ',strip=True))
    condition=raw.split('天候:')[0].split('天候：')[0]
    # Age/eligibility is explicit after the breed label. Weather/going/results
    # and the prize-money row are deliberately not stored as features.
    eligibility=re.search(r'サラブレッド系\s*(.*?)\s*(?:\*|電話投票|$)',raw)
    raw_class=eligibility[1].strip() if eligibility else ''
    surface=re.search(r'ダート|芝|障',condition)
    distance=re.search(r'(\d{3,4})m',condition)
    if run.get('distance') and distance and float(run['distance'])!=int(distance[1]):return None
    return {'race_id':rid,'date':day,'venue':venue,'race_number':no,
            'race_name':text(name.get_text(' ',strip=True)),'race_data2':raw_class,
            'surface':surface[0].replace('ダート','ダ') if surface else None,
            'source':source,'acquired_at':acquired_at,'input_hash':digest(html),
            'status':'explicit_official_header','raw_header':text(heading.get_text())+' / '+text(name.get_text())+' / '+condition+' / '+raw_class}


def collect_nar_header(cache,run,local_html=None):
    rid=valid_id(run.get('race_id'))
    if not rid:return None
    path=cache.directory/(rid+'.official.json')
    if path.is_file():
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved.get('race_id')==rid and saved.get('date')==run.get('date') and saved.get('venue')==run.get('venue'):return saved
    if rid in cache.memory:return cache.memory[rid]
    venue=run.get('venue');day=full_date(run.get('date'))
    if venue not in NAR_BABA or not day:return None
    url=f'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_babaCode={NAR_BABA[venue]}&k_raceDate={day.replace("-","%2F")}&k_raceNo={int(rid[-2:])}'
    entry={'race_id':rid,'url':url,'acquired_at':None,'source':'local' if local_html else 'HTTP'}
    value=None
    try:
        if local_html:
            html=Path(local_html).read_text(encoding='utf-8');source=str(local_html)
        elif cache.allow_http:
            import requests,time
            response=requests.get(url,timeout=15);entry['http_status']=response.status_code
            entry['acquired_at']=datetime.now(timezone.utc).isoformat()
            response.raise_for_status();response.encoding='utf-8';html=response.text;source=url
            cache.directory.mkdir(parents=True,exist_ok=True)
            (cache.directory/(rid+'.official.html')).write_text(html,encoding='utf-8')
            time.sleep(.15)
        else:return None
        value=parse_nar_official_header(html,run,source=source,acquired_at=entry['acquired_at'])
        entry['status']='explicit_header' if value else 'identity_or_header_unverified'
        if value:
            cache.directory.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as exc:
        entry['status']=type(exc).__name__;entry['error']=str(exc)
    cache.memory[rid]=value;cache.audit.append(entry)
    return value
