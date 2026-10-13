from core.game_ui_frames import newspaper_frames


def page(entries, rid="202608040511"):
    return f'<link rel="canonical" href="https://race.netkeiba.com/race/newspaper.html?race_id={rid}">' + entries


def horse(no, frame, name="テスト"):
    return f'<dl class="HorseList"><dt class="Waku{frame}">{frame}</dt><dt class="Waku_Horse">{no}</dt><dt class="HorseName Waku{frame}"><a>{name}</a></dt></dl>'


def test_explicit_frames_not_inferred_from_field_size():
    frames, audit = newspaper_frames(page(horse(16, 8)+horse(18, 8)), "202608040511", {16:"テスト",18:"テスト"})
    assert [v["frame"] for v in frames.values()] == [8,8]
    assert not audit


def test_race_and_name_must_match():
    assert not newspaper_frames(page(horse(1,1)),"202608040512",{1:"テスト"})[0]
    assert not newspaper_frames(page(horse(1,1)),"202608040511",{1:"別馬"})[0]


def test_missing_frame_not_inferred_from_horse_name_colour():
    markup=horse(1,1).replace('<dt class="Waku1">1</dt>','')
    assert not newspaper_frames(page(markup),"202608040511",{1:"テスト"})[0]


def test_conflicting_frame_and_duplicate_numbers_rejected():
    markup=horse(1,1).replace('<dt class="Waku1">1</dt>','<dt class="Waku1">2</dt>')
    assert not newspaper_frames(page(markup),"202608040511",{1:"テスト"})[0]
    assert not newspaper_frames(page(horse(1,1)+horse(1,2)),"202608040511",{1:"テスト"})[0]


def test_history_is_not_used_and_inputs_unchanged():
    names={1:"テスト"}
    html=page(horse(1,1))+'<table><tr><td class="Waku8">8</td></tr></table>'
    frames,_=newspaper_frames(html,"202608040511",names)
    assert frames["1"]["frame"] == 1
    assert names == {1:"テスト"}


def test_uploaded_zip_uses_html_race_id_not_filename():
    from io import BytesIO
    from zipfile import ZipFile
    from core.game_ui_uploads import uploaded_frames
    b=BytesIO()
    with ZipFile(b,'w') as z:z.writestr('競馬新聞.html',page(horse(1,1)))
    b.name='新聞.zip'
    frames,audit=uploaded_frames({'dashboard_batch_uploads':[b]},'202608040511',{1:'テスト'})
    assert frames['1']['frame']==1 and not audit


def test_bad_zip_does_not_break_prediction_display():
    from io import BytesIO
    from core.game_ui_uploads import uploaded_frames
    b=BytesIO(b'not a zip');b.name='broken.zip'
    frames,audit=uploaded_frames({'dashboard_batch_uploads':[b]},'202608040511',{1:'テスト'})
    assert frames=={} and audit
