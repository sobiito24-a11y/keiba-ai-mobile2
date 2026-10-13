"""Display-only lookup in the user's already uploaded newspaper files."""
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from .game_ui_frames import newspaper_frames


def uploaded_frames(state, race_id, names):
    if not race_id:
        return {}, []
    result, audit = {}, []
    for key in list(state):
        if not (str(key).startswith(('html_upload_', 'nar_json_upload_', 'game_frames_')) or key == 'dashboard_batch_uploads'):
            continue
        files = state[key]
        if not isinstance(files, (list, tuple)): files = [files]
        for item in files:
            if not hasattr(item, 'getvalue'): continue
            raw = item.getvalue()
            if len(raw) > 100_000_000: continue
            entries = []
            if str(getattr(item, 'name', '')).lower().endswith(('.html','.htm')):
                entries = [raw]
            elif str(getattr(item, 'name', '')).lower().endswith('.zip'):
                try:
                    with ZipFile(BytesIO(raw)) as z:
                        members = [x for x in z.infolist() if x.filename.lower().endswith(('.html','.htm')) and x.file_size <= 15_000_000]
                        if sum(x.file_size for x in members) > 100_000_000: continue
                        entries = [z.read(x) for x in members]
                except (BadZipFile, OSError, RuntimeError, NotImplementedError):
                    audit.append("ZIPから枠番を読み取れませんでした。新聞HTMLを直接指定できます。")
                    continue
            for html in entries:
                if str(race_id).encode('ascii') not in html: continue
                frames, messages = newspaper_frames(html, race_id, names)
                for no, frame in frames.items():
                    if no in result and result[no]['frame'] != frame['frame']:
                        audit.append(f'{no}番：複数新聞間で枠番が競合')
                        result[no] = dict(frame, frame=None)
                    elif no not in result: result[no] = frame
                audit.extend(messages)
    return {k:v for k,v in result.items() if v['frame'] is not None}, audit
