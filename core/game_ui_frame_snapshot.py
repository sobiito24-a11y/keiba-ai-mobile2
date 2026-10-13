"""Optional frame fact in the existing extensible horse metadata mapping."""
def copy_frame_metadata(result,payload):
    from .game_race_ui import frame_number
    from .prediction_table_ui import horse_key
    table=getattr(result,'overall_table',None)
    if table is None:return
    by={horse_key(h):frame_number(h) for h in table.to_dict('records')}
    for h in payload.get('horses',[]):
        value=by.get(str(h.get('horse_no')))
        if value is not None:h['frame_number']=value
