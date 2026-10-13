"""Provider stable ratings only. Never interpret comment prose or prediction marks."""
from copy import copy
from hashlib import sha256
import re
import unicodedata
from bs4 import BeautifulSoup

# Verified against netkeiba race_pc_new.css and icon_sprite_raceinfo.png:
# 01: -37px -159px (◎), 02: -38px -181px (○), 03: -37px -204px (△).
ICONS = {'Icon_Mark_01': '◎', 'Icon_Mark_02': '○', 'Icon_Mark_03': '△'}
SOURCE = 'netkeiba:Stable_Comment/Hyoka'
FIELDS = ('newspaper_stable_rating', 'newspaper_stable_rating_source',
          'newspaper_stable_rating_audit')


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')))


def parse(html):
    """Read only the explicitly labelled stable-comment evaluation table."""
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = {}
    digest = sha256((html or '').encode('utf-8')).hexdigest()
    for table in soup.select('table.Stable_Comment'):
        if '評価' not in [h.get_text(strip=True) for h in table.select('th')]:
            continue
        for tr in table.select('tr'):
            num, name = tr.select_one('td.Waku'), tr.select_one('td.Horse_Name')
            if num is None or name is None or not num.get_text(strip=True).isdigit():
                continue
            key = str(int(num.get_text(strip=True)))
            cell = tr.select_one('td.Hyoka')
            grades = set()
            if cell is not None:
                literal = cell.get_text(strip=True)
                if literal in ('◎', '○', '△'):
                    grades.add(literal)
                for icon in cell.select('.Icon_RaceInfo'):
                    grades.update(ICONS[c] for c in icon.get('class', []) if c in ICONS)
            grade = next(iter(grades)) if len(grades) == 1 else ''
            record = {'name': name.get_text(strip=True), FIELDS[0]: grade,
                      FIELDS[1]: SOURCE,
                      FIELDS[2]: {'reason': '新聞の明示評価' if grade else '評価アイコン未取得・未対応または競合',
                                  'html_sha256': digest}}
            if key in rows:
                record[FIELDS[0]] = ''
                record[FIELDS[2]]['reason'] = '同一馬番の厩舎欄が重複'
            rows[key] = record
    return rows


def assessment(row):
    grade = row.get(FIELDS[0])
    source = row.get(FIELDS[1])
    valid = isinstance(grade, str) and grade in ('◎', '○', '△') and source == SOURCE
    audit = row.get(FIELDS[2])
    reason = audit.get('reason') if isinstance(audit, dict) else None
    return {'grade': grade if valid else '', 'source': source if valid else '',
            'reason': reason or ('新聞の明示評価' if valid else 'Snapshotに新聞由来の厩舎評価が未保存'),
            'audit': audit if isinstance(audit, dict) else {}}


def attach(result, html_files):
    """After ALL predictions: add display metadata to a copied overall table.

    The old archive, horse evaluation, formal snapshots, AI and frozen prose
    are untouched. Existing dataframe serialization preserves these columns.
    """
    table = getattr(result, 'overall_table', None)
    if result.race_mode != 'jra' or table is None or table.empty:
        return result
    html = html_files.get('newspaper') or html_files.get('newspaper_context') or ''
    if not html:
        return result
    rows = parse(html)
    view = copy(result)
    view.overall_table = table.copy(deep=True)
    records = []
    for horse in table.to_dict('records'):
        try:
            key = str(int(horse.get('馬番')))
        except (ValueError, TypeError):
            key = ''
        record = rows.get(key)
        if record and normalized(record['name']) == normalized(horse.get('馬名')):
            records.append(record)
        else:
            records.append({FIELDS[0]: '', FIELDS[1]: '', FIELDS[2]: {
                'reason': '新聞馬名と保存馬名が不一致' if record else '新聞の厩舎評価欄未取得'}})
    for key in FIELDS:
        view.overall_table[key] = [r[key] for r in records]
    return view


def snapshot_metadata(result, payload):
    """Carry optional provider facts through the Mobile horse snapshot path."""
    from copy import deepcopy
    table = getattr(result, 'overall_table', None)
    if result.race_mode != 'jra' or table is None or table.empty or FIELDS[0] not in table:
        return
    by = {str(int(h['馬番'])): h for h in table.to_dict('records') if str(h.get('馬番', '')).replace('.0', '').isdigit()}
    for horse in payload.get('horses', []):
        source = by.get(str(horse.get('horse_no')), {})
        for field in FIELDS:
            if field in source: horse[field] = deepcopy(source[field])
