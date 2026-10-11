"""Presentation of existing material verdicts; no selection or new assessment."""
from copy import copy, deepcopy
from html import escape


def material_map(result):
    # Existing compatibility adapter may add version B to debug_info. Limit
    # that side effect to a temporary view, never the original saved result.
    from .material_reconsideration import saved_materials
    view = copy(result)
    view.debug_info = deepcopy(getattr(result, 'debug_info', None) or {})
    return saved_materials(view)


def material_cells(row, mode, evidence=None):
    from .material_reconsideration import display_material_cell
    plus = display_material_cell(evidence)
    caution = display_material_cell(evidence, False)
    # Preserve the exact existing detailed-table warning precedence.
    if mode == 'jra' and row.get('_display_jra_mark_reasons'):
        caution = ' / '.join(row['_display_jra_mark_reasons'])
    return {'今回プラス': plus, '今回注意': caution}


def material_html(row, mode, evidence=None):
    cells = material_cells(row, mode, evidence)
    parts = ['<div><b>'+escape(label)+'</b><br>'+escape(value)+'</div>'
             for label, value in cells.items() if value not in ('', '—', '未計算')]
    return ('<div class="horse-materials" style="font-size:12px;line-height:1.5;overflow-wrap:anywhere;margin:6px 0;">'
            + ''.join(parts) + '</div>') if parts else ''


def existing_development(row):
    # Same source order as the existing detailed-table development column.
    from .prediction_table_ui import pick, text
    return text(pick(row, 'v1_pace_eval', 'shadow_pace_eval', 'pace_mark_market')) or '—'


def material_sentence(cells):
    parts = []
    for label, value in cells.items():
        if value not in ('', '—', '未計算'):
            parts.append(label+'は'+value+'。')
    return ''.join(parts)


def explain_selected(insight, result, rows):
    """New prose only, after immutable candidate selection. No saved rewrites."""
    from .prediction_table_ui import horse_key
    from .race_insight_common import label
    materials = material_map(result)
    by = {horse_key(h): h for h in rows}
    facts = {h['no']: h for h in insight['horses']}
    chosen = list(dict.fromkeys(insight['centers']+insight['opponents']+insight['additional']))
    cells = {no: material_cells(by.get(no, {}), result.race_mode, materials.get(no)) for no in chosen}
    # Evidence stays inside the existing horse-facts container so the existing
    # snapshot input hash includes every material used in NEW explanations.
    for no in chosen:
        facts[no]['material_display'] = cells[no]
    for index, key in [(1, 'centers'), (2, 'opponents'), (3, 'additional')]:
        for i, no in enumerate(insight[key]):
            sentence = material_sentence(cells[no])
            if sentence:
                insight['sections'][index]['paragraphs'][i] += sentence
    if insight['sections'][2].get('groups'):
        paragraphs = dict(zip(insight['opponents'], insight['sections'][2]['paragraphs']))
        for group in insight['sections'][2]['groups']:
            group['paragraphs'] = [paragraphs[no] for no in group['horse_numbers']]
    # Emphasize strong existing materials only among already-selected horses.
    positives = [no for no in chosen if cells[no]['今回プラス'].startswith('◎')]
    cautions = [no for no in chosen if cells[no]['今回注意'].startswith('⚠')
                or by.get(no, {}).get('_display_jra_mark_reasons')]
    # Reserve space for both sides: warnings must not crowd out strong positives.
    important = list(dict.fromkeys(positives[:2] + cautions[:2]))
    additions = []
    for no in important:
        h = facts[no]
        intro = ('正式候補圏外の' if not h['member'] else '') + label(h) + 'について、'
        text = intro + material_sentence(cells[no])
        if cells[no]['今回注意'] != '—' and cells[no]['今回プラス'] != '—':
            text += '好材料と注意点を併せて確認したい。'
        additions.append(text)
    if additions:
        insight['sections'][4]['paragraphs'].append('材料面の比較では、'+''.join(additions))
    return insight
