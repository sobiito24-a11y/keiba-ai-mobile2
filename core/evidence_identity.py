"""Semantic display identities, independent of prediction calculations."""
import re
import unicodedata


def material_items(values):
    items = {}
    for value in values:
        for raw in str(value or '').split(' / '):
            if raw.strip() in ('', '—', '-', '未取得'):
                continue
            if raw.strip() == '正式順位に基づく本印':
                continue  # Classification reason, not a performance warning.
            normalized = unicodedata.normalize('NFKC', raw).replace('−', '-')
            weight = re.search(r'斤量(?:前走比)?\s*([+-]\d+(?:\.\d+)?)\s*kg', normalized)
            key = 'load_weight_change' if weight else normalized.strip()
            label = raw.strip()
            if weight:
                delta = float(weight[1])
                label = f'斤量{delta:+g}kg｜注意・単独では消し材料にしない' if delta > 0 else f'斤量{delta:+g}kg'
            items.setdefault(key, dict(key=key, text=label, sources=[]))['sources'].append(raw)
    return list(items.values())


def text(values):
    return ' / '.join(item['text'] for item in material_items(values))
