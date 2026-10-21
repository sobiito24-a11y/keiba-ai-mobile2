"""Local OCR -> editable draft -> explicit confirmation. Never infer prices.

Tesseract TSV is interpreted using labelled column positions, never row order or
popularity. Unrecognised layouts remain an empty draft for manual transcription.
"""
from datetime import datetime
import csv
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from PIL import Image, ImageOps
from . import race_odds as odds

FIELDS = ('馬番', '馬名', '単勝', '人気', '複勝下限', '複勝上限')


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')))


def engine():
    binary = os.environ.get('TESSERACT_CMD') or shutil.which('tesseract')
    if not binary:
        candidate = Path('C:/Program Files/Tesseract-OCR/tesseract.exe')
        binary = str(candidate) if candidate.exists() else None
    if not binary: raise ValueError('ローカルOCR未設定：Tesseractと日本語モデルjpnが必要です。表への手入力は利用できます。')
    result = subprocess.run([binary, '--list-langs'], capture_output=True, timeout=10)
    langs = result.stdout.decode('utf-8', errors='replace').split()
    if result.returncode or not {'jpn', 'eng'}.issubset(langs):
        raise ValueError('OCRの日本語・英語モデル（jpn / eng）が未設定です。')
    return binary


def image_data(raw):
    if len(raw) > 15_000_000: raise ValueError('画像は1枚15MB以下にしてください')
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ('PNG', 'JPEG', 'WEBP'): raise ValueError('PNG・JPEG・WebPに対応しています')
        if image.width * image.height > 20_000_000: raise ValueError('画像の画素数が大きすぎます')
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.load()
        return image
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('画像を読み込めません') from exc


def recognize(raw):
    image = image_data(raw)
    binary = engine()
    started = time.monotonic()
    from .race_odds_screenshot_grid import read_grid
    grid, seconds = read_grid(image, binary)
    if grid and '_layout_words' in grid[0]:
        return grid[0]['_layout_words'], seconds
    if grid:
        return [{'grid_row': row} for row in grid], seconds
    words = read_text_table(image, binary)
    return words, round(time.monotonic()-started, 3)


def read_text_table(image, binary, psm=6):
    # Upscale small tables for OCR only; never alter the uploaded source.
    if image.width < 1400:
        factor=min(3, max(1, 1400 // image.width))
        image=image.resize((image.width*factor,image.height*factor))
    with tempfile.TemporaryDirectory(prefix='keiba_ocr_') as directory:
        path = Path(directory) / 'input.png'
        image.save(path)
        completed = subprocess.run([binary, str(path), 'stdout', '-l', 'jpn+eng', '--psm', str(psm), '-c', 'tessedit_create_tsv=1'],
                                   capture_output=True, timeout=45)
        if completed.returncode: raise ValueError('画像認識に失敗しました。確認表で修正してください。')
    words = []
    for item in csv.DictReader(io.StringIO(completed.stdout.decode('utf-8', errors='replace')), delimiter='\t'):
        if item.get('level') != '5' or not item.get('text', '').strip(): continue
        words.append(dict(text=item['text'], x=int(item['left'])+int(item['width'])/2,
                          y=int(item['top'])+int(item['height'])/2, height=int(item['height']), confidence=float(item['conf'])))
    return words



def parse_words(words):
    """Require explicit horse-number/name/win/place headers. No guessed columns."""
    if words and 'grid_row' in words[0]:
        rows=[]
        for item in words:
            row=item['grid_row']
            match=re.fullmatch(r'(\d+(?:\.\d+)?)[〜～~\-–](\d+(?:\.\d+)?)',row['複勝'])
            rows.append({'馬番':row['馬番'],'馬名':row['馬名'],'単勝':row['単勝'],
                         '複勝下限':match[1] if match else '', '複勝上限':match[2] if match else '',
                         '読取注意':'原画像と全項目を確認' if match else '複勝読取不明：原画像で修正',
                         '_crop':row.get('_box'), '_ocr_cells':row.get('_cells',{})})
        return rows, []
    labels = {'馬番':'number', '馬名':'name', '単勝':'win', '複勝':'place', '人気':'popularity', '枠':'frame'}
    headers = {}
    for w in words:
        label = labels.get(normalize(w['text']))
        if label and label not in headers: headers[label] = w
    if not {'number','name','win','place'}.issubset(headers):
        return [], ['馬番・馬名・単勝・複勝の列見出しを確認できません。人気順から馬番を補完しません。']
    header_y = headers['name']['y']
    if any(abs(headers[k]['y']-header_y) > 35 for k in ('number','win','place')):
        return [], ['列見出しの対応が不明です。画像と確認表を照合してください。']
    ordered = sorted(headers, key=lambda k:headers[k]['x'])
    bounds = [(headers[a]['x']+headers[b]['x'])/2 for a,b in zip(ordered,ordered[1:])]
    lines=[]
    for w in sorted(words, key=lambda w:(w['y'],w['x'])):
        if w['y'] <= header_y+max(8,w['height']/2): continue
        line = next((r for r in lines if abs(r[0]['y']-w['y']) < max(7,min(r[0]['height'],w['height'])*0.65)),None)
        if line is None: lines.append([w])
        else: line.append(w)
    rows=[]
    for line in lines:
        cells={k:[] for k in ordered}
        for w in sorted(line,key=lambda w:w['x']):
            index=sum(w['x']>b for b in bounds);cells[ordered[index]].append(w)
        value=lambda k:normalize(''.join(w['text'] for w in cells[k]))
        no,name=value('number'),value('name')
        if not no.isdigit() or not name: continue
        win=value('win');place=value('place')
        match=re.fullmatch(r'(\d+(?:\.\d+)?)[〜～~\-–](\d+(?:\.\d+)?)',place)
        rows.append({'馬番':no,'馬名':name,'単勝':win,'人気':value('popularity') if 'popularity' in cells else '',
                     '複勝下限':match[1] if match else '', '複勝上限':match[2] if match else '',
                     '読取注意':'原画像と全項目を確認' if min(w['confidence'] for w in line)>=80 else '低信頼の文字あり・要確認'})
    return rows, [] if rows else ['価格行を識別できませんでした。手入力で確認してください。']


def parse_runner_layout(words, identity):
    """Fallback draft only: exact OCR names plus one consistent number column.

    Never substitute saved names/numbers into OCR. Ambiguous columns (including
    popularity order equal to horse order) are rejected, not guessed.
    """
    expected={normalize(h['name']):str(h['horse_no']) for h in identity['horses']}
    lines=[]
    for w in sorted(words,key=lambda w:(w.get('y',0),w.get('x',0))):
        if 'text' not in w or not normalize(w['text']): continue
        line=next((r for r in lines if abs(r[0]['y']-w['y'])<max(5,min(r[0]['height'],w['height'])*.6)),None)
        if line is None: lines.append([w])
        else: line.append(w)
    anchors=[]
    for line in lines:
        line=sorted(line,key=lambda w:w['x'])
        matches=[]
        for start in range(len(line)):
            for end in range(start+1,min(len(line),start+12)+1):
                name=normalize(''.join(w['text'] for w in line[start:end]))
                if name in expected: matches.append((start,end,name))
        if len(matches)!=1: continue
        start,end,name=matches[0]
        numbers=[w for w in line[:start] if normalize(w['text'])==expected[name]]
        anchors.append((line,start,end,name,numbers))
    anchors=[a for a in anchors if a[4]]
    if len(anchors)<2: return [],['列の再解析：照合できる馬名が不足しています。確認表で手入力してください。']
    # Column must agree for every identified runner, with at least two distinct
    # numbers. One matching popularity cell is never sufficient evidence.
    candidates=[]
    for w in anchors[0][4]:
        x=w['x']
        if all(sum(abs(n['x']-x)<=12 for n in a[4])==1 for a in anchors): candidates.append(x)
    if len(candidates)!=1 or len({a[3] for a in anchors})!=len(anchors):
        return [],['馬番列と人気列を一意に区別できません。画像を確認して手入力してください。']
    x=candidates[0];rows=[]
    # With cell geometry, use the verified name/number columns for unreadable
    # names too. Retain their actual OCR text for correction, never saved names.
    if words and all(w.get('ruled_cell') for w in words):
        name_x={a[0][a[1]]['x'] for a in anchors}
        if len(name_x)==1:
            name_x=next(iter(name_x)); all_anchors=[]
            for line in lines:
                line=sorted(line,key=lambda w:w['x'])
                ns=[w for w in line if abs(w['x']-x)<=12 and normalize(w['text']).isdigit()]
                positions=[j for j,w in enumerate(line) if w['x']==name_x]
                if len(ns)==1 and len(positions)==1:
                    j=positions[0]
                    all_anchors.append((line,j,j+1,normalize(line[j]['text']),ns))
            anchors=all_anchors
    for line,start,end,name,numbers in anchors:
        no=next(normalize(n['text']) for n in numbers if abs(n['x']-x)<=12)
        # Only accept an explicit decimal + explicit range, without extra
        # trailing values. Unknown price layouts remain blank for manual review.
        tail=' '.join(normalize(w['text']) for w in line[end:])
        match=re.fullmatch(r'(\d+\.\d)\s+(\d+\.\d)\s*[〜～~\-–]\s*(\d+\.\d)',tail)
        rows.append({'馬番':no,'馬名':name,'単勝':match[1] if match else '',
                     '複勝下限':match[2] if match else '', '複勝上限':match[3] if match else '',
                     '_layout_review':True,'読取注意':'列見出し不足：列位置・馬番・全価格を確認'})
    return rows,['列見出し不足のため保存出走馬と列位置で再解析しました。下書きです。全頭・全価格を画像と照合してください。']


def draft(files, identity):
    if not 1 <= len(files) <= 5: raise ValueError('画像は1〜5枚で指定してください')
    rows=[];messages=[];sources=[];elapsed=0
    for name,raw in files:
        image_data(raw)  # Reject corrupt/oversized images even if OCR is absent.
        sha=hashlib.sha256(raw).hexdigest()
        if sha in [s['sha256'] for s in sources]: continue
        sources.append(dict(name=name,sha256=sha))
        try:
            words,seconds=recognize(raw);parsed,warnings=parse_words(words);elapsed+=seconds
            if not parsed:
                parsed,retry_messages=parse_runner_layout(words,identity)
                warnings.extend(retry_messages)
                if not parsed:
                    retry_start=time.monotonic()
                    retry_words=read_text_table(image_data(raw),engine(),psm=11)
                    parsed,retry_messages=parse_words(retry_words)
                    if not parsed:
                        parsed,retry_messages=parse_runner_layout(retry_words,identity)
                    elapsed+=time.monotonic()-retry_start
                    warnings.extend(retry_messages)

            for row in parsed: row['_image_sha']=sha
            rows.extend(parsed);messages.extend(warnings)
        except (ValueError, subprocess.TimeoutExpired) as exc:
            messages.append(str(exc) if isinstance(exc,ValueError) else 'OCRが制限時間に達しました。確認表で修正してください。')
    # Exact overlap duplicates only; conflicting readings remain for correction.
    unique=[];seen=set()
    for row in rows:
        key=tuple(row.get(k,'') for k in FIELDS)
        if key not in seen: unique.append(row);seen.add(key)
    present={str(r['馬番']) for r in unique}
    for row in unique:
        issues=review_issues(row,identity)
        row['読取注意']=' / '.join(issues) if issues else '原画像と全項目を確認'
    for h in identity['horses']:
        if len(unique)<len(identity['horses']) and str(h['horse_no']) not in present:
            unique.append({'馬番':str(h['horse_no']), '馬名':'', '単勝':'', '複勝下限':'', '複勝上限':'', '読取注意':'未読取：馬名・数値を画像で確認'})
    return dict(identity_binding=identity_binding(identity),race_id=str(identity['race_id']),rows=unique,sources=sources,messages=list(dict.fromkeys(messages)),seconds=elapsed,
                imported_at=datetime.now(odds.JST).isoformat(),version='screenshot_tesseract_grid_v4')


def review_issues(row,identity):
    """Review hints only; never change any OCR value to fit saved runners."""
    issues=[]
    if row.get('_layout_review'): issues.append('列見出し不足：列位置・馬番・全価格を確認')
    expected={str(h['horse_no']):normalize(h['name']) for h in identity['horses']}
    if expected.get(normalize(row.get('馬番'))) != normalize(row.get('馬名')):
        issues.append('馬番・馬名不一致（自動補完なし）')
    for label,cell in row.get('_ocr_cells',{}).items():
        if cell.get('disagreement'):
            issues.append(label+'の再読取が不一致・桁欠落等を確認')
    for label in ('単勝','複勝下限','複勝上限'):
        value=normalize(row.get(label))
        if not re.fullmatch(r'\d+\.\d',value) or float(value)<1:
            issues.append(label+'の形式・欠損を確認')
    try:
        if float(row.get('複勝下限',''))>float(row.get('複勝上限','')):
            issues.append('複勝上下限が逆転')
    except (ValueError,TypeError): pass
    return issues


def identity_binding(identity):
    return odds.digest(dict(race_id=str(identity['race_id']),mode=identity['mode'],
        horses=sorted((str(h['horse_no']),normalize(h['name'])) for h in identity['horses'])))


def saved_name_candidate(row, identity, draft_data):
    # Race association is the selected saved race, not an inferred image ID.
    if draft_data.get('identity_binding')!=identity_binding(identity): return None
    no=normalize(row.get('馬番'))
    matches=[h for h in identity['horses'] if str(h['horse_no'])==no]
    if len(matches)!=1 or normalize(row.get('馬名'))==normalize(matches[0]['name']): return None
    return str(matches[0]['name'])


def adopt_saved_name(row, identity, draft_data, confirmed=False):
    candidate=saved_name_candidate(row,identity,draft_data)
    if not confirmed or candidate is None:
        raise ValueError('対象レース・馬番・元画像・価格を確認してから正式馬名を採用してください')
    changed=dict(row);changed['馬名']=candidate
    changed['読取注意']='正式馬名を確認して採用済み・全頭数値の確認が必要'
    event=dict(race_id=str(identity['race_id']),horse_no=normalize(row.get('馬番')),
               original_name=str(row.get('馬名','')),adopted_name=candidate,
               confirmed_at=datetime.now(odds.JST).isoformat())
    return changed,event


def confirmed_quote(rows, identity, draft_data, confirmed=False):
    if draft_data.get('identity_binding') and draft_data['identity_binding']!=identity_binding(identity):
        raise ValueError('読取時と対象レースが異なります。対象レースで再読取してください')
    if not confirmed: raise ValueError('画像と全項目を確認してから確定してください')
    expected={str(h['horse_no']):odds.norm(h['name']) for h in identity['horses']}
    names={};prices=[];popularity={};missing=0
    for row in rows:
        no=normalize(row.get('馬番'));name=normalize(row.get('馬名'))
        if no not in expected or no in names or name != expected[no]:
            raise ValueError('全頭の馬番・馬名を照合してください。重複・別馬・未読取は確定できません。')
        names[no]=str(row['馬名'])
        pop=normalize(row.get('人気')).removesuffix('人気')
        if pop not in ('','—','-'):
            if not pop.isdigit() or not 1<=int(pop)<=len(expected):raise ValueError('人気順位を確認してください')
            popularity[no]=int(pop)
        values=[]
        for key in ('単勝','複勝下限','複勝上限'):
            text=normalize(row.get(key))
            if text in ('','—','---.-'):values.append(None);continue
            if not re.fullmatch(r'\d+(?:\.\d+)?',text) or float(text)<1:
                raise ValueError(f'{no}番 {key}の数値を確認してください')
            values.append(float(text))
        win,lo,hi=values
        if (lo is None)!=(hi is None) or (lo is not None and lo>hi):
            raise ValueError(f'{no}番の複勝上下限を確認してください')
        if win is not None: prices.append(dict(kind='win',horses=[int(no)],low=win,high=win))
        if lo is not None: prices.append(dict(kind='place',horses=[int(no)],low=lo,high=hi))
        if any(v is None for v in values): missing+=1
    if set(names)!=set(expected): raise ValueError('レース名の有無にかかわらず、全出走馬の照合が必要です')
    if not prices: raise ValueError('有効な単勝・複勝価格がありません')
    q=odds.validate(dict(race_id=identity['race_id'],mode=identity['mode'],identities=names,prices=prices,popularity=popularity,
                        source='user_confirmed_screenshot',acquisition_method='manual_screenshot',
                        received_at=draft_data['imported_at'],observed_at=None,price_status='timestamp_unknown',
                        screenshot_audit=dict(version=draft_data['version'],images=draft_data['sources'],
                                              raw_rows=draft_data['rows'],confirmed_rows=rows,
                                              name_adoptions=draft_data.get('name_adoptions',[]),confirmation_at=datetime.now(odds.JST).isoformat()),
                        incomplete_horses=missing),identity)
    return q
