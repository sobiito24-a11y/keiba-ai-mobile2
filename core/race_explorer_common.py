"""Small, escaped presentation primitives shared by the race comparison UI."""
from html import escape
from collections.abc import Mapping
import re

from .prediction_table_ui import number, fmt


def plain(value):
    return escape('' if value is None else str(value))


def value(item, missing='未取得'):
    if item is None or str(item).strip().casefold() in ('', '—', '―', '－', '-', 'nan', 'none', '<na>', 'inf', '+inf', '-inf', 'infinity', '+infinity', '-infinity'):
        return plain(missing)
    n=number(item)
    return plain(fmt(n) if n is not None else item)


def number_badge(horse):
    from .game_race_ui import FRAME_COLORS
    frame=number(horse.get('frame'))
    frame=int(frame) if frame is not None and frame.is_integer() and frame in FRAME_COLORS else None
    colors=FRAME_COLORS.get(frame)
    style=(' style="--frame-bg:'+colors[0]+';--frame-ink:'+colors[1]+'"') if colors else ''
    label=(str(frame)+'枠 · ' if frame else '枠番未取得 · ')+'馬番 '+str(horse.get('no','未取得'))
    return '<span class="number-badge'+(' number-unknown' if frame is None else '')+'"'+style+' aria-label="'+plain(label)+'" title="'+plain(label)+'">'+value(horse.get('no'),'―')+'</span>'


def index_html(cell):
    cell=cell if isinstance(cell,Mapping) else {}
    n=number(cell.get('value')); rank=number(cell.get('rank'))
    return '<b class="metric-number">'+value(n)+'</b>'+('<small class="metric-rank">'+value(rank)+'位</small>' if n is not None and rank is not None and rank>0 and rank.is_integer() else '')


def material_text(item):
    """Remove old judgement glyphs in summaries, never the stored wording."""
    return re.sub(r'[◎○▲✔✓△][\ufe0e\ufe0f]?\s*','',str(item or '')).strip()
