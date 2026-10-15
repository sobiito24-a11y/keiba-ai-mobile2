from copy import deepcopy
import io
import pytest
from PIL import Image
from core import race_odds_screenshot as s
from core import race_odds as o


def identity():
    return dict(race_id='202608040511',mode='jra',horses=[dict(horse_no=i,name=f'テスト馬{i}') for i in range(1,19)])


def rows():
    return [{'馬番':str(i),'馬名':f'テスト馬{i}','単勝':str(i+1.1),'複勝下限':'1.2','複勝上限':'2.4'} for i in range(1,19)]


def audit():
    return dict(imported_at='2026-10-15T10:00:00+09:00',version='test',sources=[{'sha256':'test'}],rows=rows())


def test_confirm_full_batch_and_no_mutation_or_clock_guessing():
    data=rows();before=deepcopy(data)
    q=s.confirmed_quote(data,identity(),audit(),True)
    assert data==before and q['horse_count']==18 and len(q['prices'])==36
    assert q['observed_at'] is None and q['acquisition_method']=='manual_screenshot'
    assert all(p['kind'] in ('win','place') for p in q['prices'])
    assert len(o.merge([q],[q],identity()))==1


@pytest.mark.parametrize('change',[
    lambda r:r.pop(), lambda r:r.append(r[0]),lambda r:r[0].update(馬名='別の馬'),
    lambda r:r[0].update(馬番='2'),lambda r:r[0].update(単勝='O.5'),
    lambda r:r[0].update(単勝='nan'),lambda r:r[0].update(複勝下限='9.9'),
    lambda r:r[0].update(複勝上限=''),lambda r:r[0].update(馬名='')])
def test_unverified_identity_or_invalid_prices_rejected(change):
    r=rows();change(r)
    with pytest.raises(ValueError):s.confirmed_quote(r,identity(),audit(),True)


def test_confirmation_required_and_partial_prices_remain_missing():
    with pytest.raises(ValueError):s.confirmed_quote(rows(),identity(),audit())
    r=rows();r[0].update(単勝='',複勝下限='',複勝上限='')
    q=s.confirmed_quote(r,identity(),audit(),True)
    assert q['horse_count']==17 and q['incomplete_horses']==1
    assert not any(1 in p['horses'] for p in q['prices'])


def word(text,x,y):return dict(text=text,x=x,y=y,height=18,confidence=95)


def test_popularity_is_never_horse_number_and_unknown_headers_rejected():
    words=[word(t,x,10) for t,x in [('人気',10),('馬番',60),('馬名',180),('単勝',320),('複勝',410)]]
    words += [word(t,x,50) for t,x in [('1',10),('8',60),('テスト馬8',180),('8.8',320),('2.0-3.0',410)]]
    result,messages=s.parse_words(words)
    assert result[0]['馬番']=='8' and result[0]['単勝']=='8.8'
    assert result[0]['複勝下限']=='2.0' and result[0]['複勝上限']=='3.0'
    assert s.parse_words([w for w in words if w['text']!='馬番'])[0]==[]


def png():
    b=io.BytesIO();Image.new('RGB',(50,50),'white').save(b,format='PNG');return b.getvalue()


def test_missing_engine_has_editable_blanks_never_invented_names(monkeypatch):
    def unavailable(_):raise ValueError('OCR unavailable')
    monkeypatch.setattr(s,'recognize',unavailable)
    d=s.draft([('a.png',png())],identity())
    assert len(d['rows'])==18 and all(r['馬名']==r['単勝']=='' for r in d['rows'])
    assert d['messages']==['OCR unavailable']


def test_multiple_images_conflicts_preserved_exact_overlap_deduplicated(monkeypatch):
    monkeypatch.setattr(s,'recognize',lambda _: ([],0.1))
    monkeypatch.setattr(s,'parse_words',lambda _:([dict(rows()[0],読取注意='確認')],[]))
    d=s.draft([('a.png',png()),('again.png',png())],identity())
    assert len(d['sources'])==1 and len(d['rows'])==18
    assert d['rows'][0]['馬名']=='テスト馬1'


def test_invalid_image_rejected():
    with pytest.raises(ValueError):s.image_data(b'not an image')


def test_grid_readings_preserve_errors_for_manual_review():
    parsed,_=s.parse_words([{'grid_row':{'馬番':'','馬名':'読取名','単勝':'7.1','複勝':'38.2-4.2'}}])
    assert parsed[0]['馬番']=='' and parsed[0]['単勝']=='7.1'
    assert parsed[0]['複勝下限']=='38.2' and parsed[0]['複勝上限']=='4.2'
    with pytest.raises(ValueError): s.confirmed_quote(parsed,identity(),audit(),True)


def test_ruled_table_stops_before_next_section(monkeypatch):
    from PIL import ImageDraw
    from core.race_odds_screenshot_grid import read_grid
    from types import SimpleNamespace
    image=Image.new('RGB',(400,600),'white'); draw=ImageDraw.Draw(image)
    for y in (10,60,90,120,220,250):draw.line((0,y,399,y),fill=(200,200,200),width=2)
    for x in (0,60,220,300,399):draw.line((x,10,x,250),fill=(200,200,200),width=2)
    readings=iter(['馬番','馬名','単勝','複勝']+[v for v in ['9','馬A','3.9','1.5-1.8','1','馬B','6.1','2.2-2.9'] for _ in range(2)])
    monkeypatch.setattr('core.race_odds_screenshot_grid.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=next(readings).encode()))
    rows,_=read_grid(image,'test')
    assert len(rows)==2 and rows[0]['馬番']=='9' and rows[1]['馬番']=='1'


def test_pair_history_is_retained_when_screenshot_added():
    q=s.confirmed_quote(rows(),identity(),audit(),True)
    pair=deepcopy(q);pair['prices']=[dict(kind='wide',horses=[1,2],low=3.,high=4.)]
    original=deepcopy(pair);history=o.merge([pair],[q],identity())
    assert pair==original and history[0]['prices'][0]['kind']=='wide' and len(history)==2


def test_review_ui_requires_confirmation_then_commits_once(monkeypatch):
    from streamlit.testing.v1 import AppTest
    source='''
import streamlit as st
from unittest.mock import patch
from core.race_odds_screenshot_ui import render
from core import race_odds as o
from tests.test_race_odds_screenshot import identity, audit, png
class Upload:
 name='test.png'
 def getvalue(self):return png()
import hashlib
sig=o.digest([('test.png',hashlib.sha256(png()).hexdigest())])
st.session_state.setdefault('test_ocr_'+sig,dict(audit(),messages=[],seconds=0.1))
state=st.session_state.setdefault('prices',dict(saved=[],history=[]))
with patch('streamlit.file_uploader',return_value=[Upload()]):
 render(identity(),state,'test')
'''
    at=AppTest.from_string(source).run(timeout=30)
    assert not at.exception
    apply=next(b for b in at.button if b.label=='全頭一括反映')
    assert apply.disabled and not at.session_state['prices']['history']
    at.checkbox[0].check().run()
    next(b for b in at.button if b.label=='全頭一括反映').click().run()
    assert not at.exception and len(at.session_state['prices']['history'])==1
    assert at.session_state['prices']['history'][0]['horse_count']==18
    next(b for b in at.button if b.label=='全頭一括反映').click().run()
    assert len(at.session_state['prices']['history'])==1
    # Editing a row invalidates earlier confirmation; invalid identity cannot
    # be committed even after a new confirmation.
    at.text_input[1].set_value('別馬')
    next(b for b in at.button if b.label=='この行の修正を保存').click().run()
    assert next(b for b in at.button if b.label=='全頭一括反映').disabled
    at.checkbox[0].check().run()
    next(b for b in at.button if b.label=='全頭一括反映').click().run()
    assert at.error and len(at.session_state['prices']['history'])==1
