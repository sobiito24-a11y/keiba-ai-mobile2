"""Read explicit current-entry frame numbers without changing predictions."""
import re
import unicodedata
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup


def normalize_name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def newspaper_frames(html, expected_race_id, expected_horses):
    """Return verified display metadata and audit messages; no guessed frames.

    expected_horses maps horse numbers to names from the current prediction.
    Only the current entry list is read, never historical race tables.
    """
    soup = BeautifulSoup(html, "html.parser")
    ids = set()
    for tag in soup.select('link[rel="canonical"], meta[property="og:url"]'):
        url = urlparse(tag.get("href") or tag.get("content") or "")
        if url.hostname in {"race.netkeiba.com", "nar.netkeiba.com"}:
            ids.update(parse_qs(url.query).get("race_id", []))
    if ids != {str(expected_race_id)}:
        return {}, ["新聞のレースIDが未取得、競合、または対象レースと不一致"]
    expected = {str(k): normalize_name(v) for k, v in expected_horses.items()}
    result, audit, seen = {}, [], set()
    for entry in soup.select("dl.HorseList"):
        number = entry.select_one("dt.Waku_Horse")
        name = entry.select_one("dt.HorseName a")
        if number is None or name is None:
            audit.append("出馬表の馬番または馬名が未取得")
            continue
        no = normalize_name(number.get_text())
        if not re.fullmatch(r"[1-9]\d*", no):
            audit.append("出馬表の馬番が不正")
            continue
        if no in seen:
            result.pop(no, None)
            audit.append(f"{no}番：出馬表内で馬番重複")
            continue
        seen.add(no)
        horse_name = name.get_text(strip=True)
        if no not in expected or normalize_name(horse_name) != expected[no]:
            audit.append(f"{no}番：予想と馬名または馬番が不一致")
            continue
        frames = set()
        invalid = False
        for cell in entry.find_all("dt", recursive=False):
            classes = cell.get("class", [])
            # HorseName repeats the frame colour class but is not a frame cell.
            if "HorseName" in classes or "Waku_Horse" in classes:
                continue
            for css in classes:
                match = re.fullmatch(r"Waku([1-8])", css)
                if match:
                    frame = int(match[1])
                    if normalize_name(cell.get_text()) != str(frame):
                        invalid = True
                    frames.add(frame)
        if invalid or len(frames) != 1:
            audit.append(f"{no}番：明示枠番が未取得または競合")
            continue
        result[no] = {"frame": frames.pop(), "name": horse_name,
                      "race_id": str(expected_race_id), "source": "newspaper_html"}
    return result, audit


def attach_saved_frames(result, html_files):
    """Attach newspaper facts only AFTER every prediction engine has finished.

    Existing dataframe serialization carries this optional factual column. No
    scores, marks, candidate fields or existing frame values are overwritten.
    """
    from copy import copy
    from .prediction_table_ui import horse_key, pick
    from .newspaper_v2_inputs import race_id
    html=html_files.get('newspaper') or html_files.get('newspaper_context')
    table=getattr(result,'overall_table',None)
    if not html or table is None or table.empty:return result
    rows=table.to_dict('records')
    names={horse_key(h):pick(h,'馬名','name') for h in rows}
    frames,audit=newspaper_frames(html,race_id(result),names)
    if audit:
        import logging
        logging.getLogger(__name__).info('Frame metadata audit for %s: %s', race_id(result), '; '.join(audit))
    if not frames:return result
    view=copy(result);view.overall_table=table.copy(deep=True)
    from .game_race_ui import frame_number
    view.overall_table['frame_number']=[frame_number(h) or frames.get(horse_key(h),{}).get('frame') for h in rows]
    return view
