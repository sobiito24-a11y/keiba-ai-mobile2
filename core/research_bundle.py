"""Offline, bounded containers. Never changes original prediction bytes."""
import hashlib, io, json, os, re, sqlite3, stat, zipfile
from pathlib import Path, PurePosixPath
from .new_ai_research import VERSION, CONFIG, digest

MAX_ARCHIVE=200_000_000
MAX_TOTAL=256_000_000
MAX_JSON=8_000_000
MAX_FILES=512
FORMAT='keiba-research-bundle-v1'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def checked_zip(raw):
    if len(raw)>MAX_ARCHIVE:raise ValueError('ファイルサイズ上限200MBを超えています')
    try:z=zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:raise ValueError("ZIP形式が不正です") from exc
    items=z.infolist();names=[i.filename for i in items]
    if len(items)>MAX_FILES or len(names)!=len(set(names)) or sum(i.file_size for i in items)>MAX_TOTAL:
        z.close();raise ValueError('ZIPの件数・展開サイズ・重複名が不正です')
    for i in items:
        p=PurePosixPath(i.filename)
        if (p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or i.is_dir()
            or stat.S_ISLNK(i.external_attr>>16) or i.flag_bits&1 or i.file_size>MAX_ARCHIVE):
            z.close();raise ValueError('ZIP内に許可されないファイルがあります')
    return z

def event_bytes(raw):
    with checked_zip(raw) as z:
        if set(z.namelist())!={'manifest.json','snapshot.json'}:raise ValueError('未対応の.keiba構造です')
        if z.getinfo('manifest.json').file_size>MAX_JSON:raise ValueError('manifestが過大です')
        body=z.read('snapshot.json');manifest=json.loads(z.read('manifest.json'))
    if sha(body)!=manifest.get('snapshot_sha256'):raise ValueError('元.keibaのハッシュ不一致')
    event=json.loads(body)
    if event.get('schema_version')!=1 or not isinstance(event.get('races'),list):raise ValueError('未対応の予想スキーマです')
    ids=[r['race_id'] for r in event['races']]
    if len(ids)!=len(set(ids)):raise ValueError('重複レースIDです')
    return event

def validate_envelope(raw,source_hash,races):
    if len(raw)>MAX_JSON:raise ValueError('研究JSONが過大です')
    envelope=json.loads(raw);p=envelope['payload']
    if digest(p)!=envelope['payload_sha256']:raise ValueError('研究JSONハッシュ不一致')
    if p['keiba_sha256']!=source_hash:raise ValueError('元.keibaハッシュ不一致')
    if p['version']!=VERSION or p['config_sha256']!=digest(CONFIG) or digest(p['config'])!=digest(CONFIG):raise ValueError('未対応モデル版・係数設定です')
    race=races.get(p['race_id'])
    if race is None or p['authority']!=race['race_mode'].upper() or p['race_date']!=race['date']:raise ValueError('研究レースID・主催・日付不一致')
    expected={int(h['horse_no']):h['horse_name'] for h in race['horses']}
    allowed={'A','J_only','F1','F2','F3'} if p['authority']=='JRA' else {'A','NAR_Pure','NAR_P_J','NAR_P_F1','NAR_P_F2','NAR_P_F3'}
    if set(p['models'])!=allowed:raise ValueError('研究モデル構成が不正です')
    for model,data in p['models'].items():
        rows=data['rows'];found={int(h['no']):h['name'] for h in rows}
        if len(rows)!=len(found) or found!=expected:raise ValueError('研究結果の馬番・馬名不一致')
    return p

def load(raw):
    """Return immutable original bytes, parsed event and per-race research."""
    try:
        with checked_zip(raw) as z:
            if set(z.namelist())=={'manifest.json','snapshot.json'}:
                return raw,event_bytes(raw),{}
            if 'bundle.json' not in z.namelist() or z.getinfo('bundle.json').file_size>MAX_JSON:raise ValueError('研究ZIPのmanifestがありません')
            m=json.loads(z.read('bundle.json'))
            if m.get('format')!=FORMAT:raise ValueError('未対応の研究ZIPです')
            entries=m['files']
            if not isinstance(entries,dict) or set(z.namelist())!={'bundle.json',*entries}:raise ValueError('ZIPファイル一覧不一致')
            if 'prediction.keiba' not in entries:raise ValueError('元.keibaがありません')
            for name in entries:
                if name!='prediction.keiba' and not re.fullmatch(r'research/[0-9]{12}\.json',name):raise ValueError('研究ZIPに不要なファイルがあります')
                if name!='prediction.keiba' and z.getinfo(name).file_size>MAX_JSON:raise ValueError('研究JSONが過大です')
            original=z.read('prediction.keiba')
            if sha(original)!=entries['prediction.keiba']:raise ValueError('元.keibaハッシュ不一致')
            event=event_bytes(original);races={r['race_id']:r for r in event['races']};reports={}
            for name in entries:
                if name=='prediction.keiba':continue
                body=z.read(name)
                if sha(body)!=entries[name]:raise ValueError('研究JSONの原本ハッシュ不一致')
                p=validate_envelope(body,sha(original),races)
                if name!=f"research/{p['race_id']}.json":raise ValueError('研究JSON名とレースID不一致')
                reports[p['race_id']]=p
            return original,event,reports
    except (zipfile.BadZipFile,KeyError,TypeError,UnicodeError,json.JSONDecodeError,RuntimeError,OverflowError,AttributeError,IndexError,RecursionError) as exc:
        raise ValueError('予想ファイル／研究ZIPが不正です: '+str(exc)) from exc

def build(original,reports):
    event=event_bytes(original);races={r['race_id']:r for r in event['races']}
    files={'prediction.keiba':original}
    for p in reports:
        name=f"research/{p['race_id']}.json"
        if name in files:raise ValueError('研究レース重複')
        body=json.dumps({'payload':p,'payload_sha256':digest(p)},ensure_ascii=False,sort_keys=True).encode()
        validate_envelope(body,sha(original),races);files[name]=body
    manifest={'format':FORMAT,'files':{k:sha(v) for k,v in files.items()}}
    files['bundle.json']=json.dumps(manifest,sort_keys=True).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,body in sorted(files.items()):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(entry,body)
    result=stream.getvalue();load(result);return result

def local_reports(original,event,db=None,json_dir=None):
    """Exact source hash only. Unknown, corrupt or other-version records are skipped."""
    base=Path(__file__).resolve().parents[1]/'research'
    db=Path(db or os.environ.get('KEIBA_RESEARCH_PREDICTIONS',base/'predictions.sqlite'))
    json_dir=Path(json_dir or os.environ.get('KEIBA_RESEARCH_JSON_DIR',base/'portable'))
    races={r['race_id']:r for r in event['races']};found={};issues=[];h=sha(original)
    def accept(body):
        try:
            p=validate_envelope(body,h,races)
            old=found.get(p['race_id'])
            if old is None or (p.get('saved_at',''),p.get('input_sha256',''))>(old.get('saved_at',''),old.get('input_sha256','')):found[p['race_id']]=p
        except (ValueError,KeyError,TypeError,AttributeError,RecursionError):pass
    if db.is_file():
        try:
            with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as c:
                for rid in races:
                    for body,hashvalue in c.execute('SELECT payload,payload_hash FROM new_ai_frozen WHERE race_id=? ORDER BY saved_at DESC LIMIT 128',(rid,)):
                        if len(body)>MAX_JSON:continue
                        try:accept(json.dumps({'payload':json.loads(body),'payload_sha256':hashvalue}))
                        except ValueError:continue
        except sqlite3.Error:issues.append('研究SQLiteを読み取れません')
    if json_dir.is_dir():
        for rid in races:
            for i,path in enumerate(json_dir.glob(rid+'_*.json')):
                if i>=128:break
                if path.stat().st_size<=MAX_JSON:
                    try:accept(path.read_bytes())
                    except OSError:issues.append('研究JSONを読み取れません')
    return found,issues

def attach_upload(raw,state,allow_local=True):
    signature=sha(raw)
    cached=state.get('research_loaded')
    if cached and cached['upload_sha256']==signature:return cached['original'],cached['event']
    # A rejected replacement must never reuse the preceding race's research.
    state.pop('research_loaded',None)
    original,event,reports=load(raw);issues=[]
    if allow_local:
        try:
            local,issues=local_reports(original,event)
            reports={**local,**reports}
        except (OSError,sqlite3.Error) as exc:
            issues.append('ローカル研究データを読み取れません：'+str(exc))
    state['research_loaded']={'upload_sha256':signature,'original':original,'event':event,'reports':reports,'issues':issues}
    return original,event
