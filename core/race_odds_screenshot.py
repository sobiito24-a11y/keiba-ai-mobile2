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

FIELDS = ('馬番', '馬名', '単勝', '複勝下限', '複勝上限')


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
    if grid:
        return [{'grid_row': row} for row in grid], seconds
    with tempfile.TemporaryDirectory(prefix='keiba_ocr_') as directory:
        path = Path(directory) / 'input.png'
        image.save(path)
        completed = subprocess.run([binary, str(path), 'stdout', '-l', 'jpn+eng', '--psm', '6', '-c', 'tessedit_create_tsv=1'],
                                   capture_output=True, timeout=45)
        if completed.returncode: raise ValueError('画像認識に失敗しました。確認表で修正してください。')
    words = []
    for item in csv.DictReader(io.StringIO(completed.stdout.decode('utf-8', errors='replace')), delimiter='\t'):
        if item.get('level') != '5' or not item.get('text', '').strip(): continue
        words.append(dict(text=item['text'], x=int(item['left'])+int(item['width'])/2,
                          y=int(item['top'])+int(item['height'])/2, height=int(item['height']), confidence=float(item['conf'])))
    return words, round(time.monotonic()-started, 3)


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
        rows.append({'馬番':no,'馬名':name,'単勝':win,
                     '複勝下限':match[1] if match else '', '複勝上限':match[2] if match else '',
                     '読取注意':'原画像と全項目を確認' if min(w['confidence'] for w in line)>=80 else '低信頼の文字あり・要確認'})
    return rows, [] if rows else ['価格行を識別できませんでした。手入力で確認してください。']


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
            for row in parsed: row['_image_sha']=sha
            rows.extend(parsed);messages.extend(warnings)
        except (ValueError, subprocess.TimeoutExpired) as exc:
            messages.append(str(exc) if isinstance(exc,ValueError) else 'OCRが制限時間に達しました。確認表で修正してください。')
    # Exact overlap duplicates only; conflicting readings remain for correction.
    unique=[];seen=set()
    for row in rows:
        key=tuple(row[k] for k in FIELDS)
        if key not in seen: unique.append(row);seen.add(key)
    present={str(r['馬番']) for r in unique}
    for row in unique:
        issues=review_issues(row,identity)
        row['読取注意']=' / '.join(issues) if issues else '原画像と全項目を確認'
    for h in identity['horses']:
        if len(unique)<len(identity['horses']) and str(h['horse_no']) not in present:
            unique.append({'馬番':str(h['horse_no']), '馬名':'', '単勝':'', '複勝下限':'', '複勝上限':'', '読取注意':'未読取：馬名・数値を画像で確認'})
    return dict(rows=unique,sources=sources,messages=list(dict.fromkeys(messages)),seconds=elapsed,
                imported_at=datetime.now(odds.JST).isoformat(),version='screenshot_tesseract_grid_v3')


def review_issues(row,identity):
    """Review hints only; never change any OCR value to fit saved runners."""
    issues=[]
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


def confirmed_quote(rows, identity, draft_data, confirmed=False):
    if not confirmed: raise ValueError('画像と全項目を確認してから確定してください')
    expected={str(h['horse_no']):odds.norm(h['name']) for h in identity['horses']}
    names={};prices=[];missing=0
    for row in rows:
        no=normalize(row.get('馬番'));name=normalize(row.get('馬名'))
        if no not in expected or no in names or name != expected[no]:
            raise ValueError('全頭の馬番・馬名を照合してください。重複・別馬・未読取は確定できません。')
        names[no]=str(row['馬名'])
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
    q=odds.validate(dict(race_id=identity['race_id'],mode=identity['mode'],identities=names,prices=prices,
                        source='user_confirmed_screenshot',acquisition_method='manual_screenshot',
                        received_at=draft_data['imported_at'],observed_at=None,price_status='timestamp_unknown',
                        screenshot_audit=dict(version=draft_data['version'],images=draft_data['sources'],
                                              raw_rows=draft_data['rows'],confirmed_rows=rows,confirmation_at=datetime.now(odds.JST).isoformat()),
                        incomplete_horses=missing),identity)
    return q
