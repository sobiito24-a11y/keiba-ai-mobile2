"""Resolve display/save marks from the same frozen formal ranks and decisions."""
from .nar_top5_order import horse_no

VERSION = 'resolved_marks_v1_20261021'


def resolve(result):
    if result.race_mode == 'jra':
        from .jra_rank_display import official_jra_result_rows
        from .jra_display_mark import jra_display_mark_from_row
        rows = official_jra_result_rows(result, result.horse_evaluation.to_dict('records'))
        originals = {horse_no(r): r for r in result.overall_table.to_dict('records')}
        def mark(r):
            if r.get('_display_jra_top5_rank') is not None:
                return jra_display_mark_from_row(r)
            old = originals.get(horse_no(r), {})
            return next((str(old[k]) for k in ('表示印','ai_current_mark','mark') if old.get(k)), '')
        return {horse_no(r): dict(mark=mark(r),
                source='saved_formal_rank', reasons=r.get('_display_jra_mark_reasons', []),
                group=r.get('_display_jra_candidate_group'), version=VERSION) for r in rows}
    from .nar_top5_order import result_rows, overlay_saved, comparison_fields
    from .nar_display_mark import display_mark
    rows = result_rows(result)
    source = overlay_saved(result, rows)
    rows = comparison_fields([dict(r) for r in source], source)
    return {horse_no(r): dict(mark=display_mark(r), version=VERSION,
            source='saved_formal_rank' if r.get('pure_ability_top5_group') else r.get('nar_check_source'),
            group='正式Top5' if r.get('pure_ability_top5_group') else '参考✓' if display_mark(r) else '無印',
            reasons=[]) for r in rows}


def reconcile_snapshot(snapshot, result):
    """Update only newly serialized copies, never existing files or source tables."""
    resolved = resolve(result)
    for h in snapshot.get('horses', []):
        item = resolved.get(str(h.get('horse_no')))
        if item:
            h['mark'] = item['mark']
            h['resolved_mark'] = item
    for h in snapshot.get('mobile_snapshot', {}).get('horses', []):
        item = resolved.get(str(h.get('horse_no')))
        if item:
            h.setdefault('prediction', {})['mark'] = item['mark']
            h['resolved_mark'] = item
    for table in ('overall_table', 'horse_evaluation'):
        block = snapshot.get('prediction_result', {}).get(table) or {}
        for h in block.get('records', []):
            item = resolved.get(horse_no(h))
            if item:
                h.setdefault('source_display_mark', h.get('表示印'))
                h['resolved_mark'] = item
                h['表示印'] = item['mark']
        if block:
            for field in ('resolved_mark', 'source_display_mark', '表示印'):
                if field not in block.get('columns', []):
                    block.setdefault('columns', []).append(field)
    return snapshot
