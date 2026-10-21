"""Attach independently frozen B to a copy; preserve every existing A field."""
from copy import deepcopy
from hashlib import sha256
import io,json,zipfile
from .independent_ai_odds_io import read_archive,restore_race
from .model_b import KEY,freeze,digest,resolve

def add_to_copy(raw):
    manifest,event=read_archive(raw)
    before=deepcopy(event);source_hash=sha256(raw).hexdigest();audit=[]
    for race in event['races']:
        result=restore_race(race)
        if KEY in race:
            report=resolve(result)
            if report.get('status')=='unavailable':raise ValueError(report.get('fallback_reason','保存B照合失敗'))
            action='preserved'
        else:
            report=freeze(result)
            report['source_keiba_sha256']=source_hash
            report.pop('prediction_sha256',None)
            report['prediction_sha256']=digest(report)
            race[KEY]=report;action='attached_retrospective'
        audit.append(dict(race_id=race['race_id'],action=action,status=report['status'],horses=len(report.get('horses',[])),reason=report.get('fallback_reason','')))
    # A, odds, metadata and existing B remain byte-value identical in the JSON tree.
    stripped=deepcopy(event)
    for race,old in zip(stripped['races'],before['races']):
        if KEY not in old:race.pop(KEY,None)
    if stripped!=before:raise ValueError('既存予想への変更を検知しました')
    body=json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    manifest['snapshot_sha256']=sha256(body).hexdigest()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        z.writestr('snapshot.json',body)
    return out.getvalue(),audit
