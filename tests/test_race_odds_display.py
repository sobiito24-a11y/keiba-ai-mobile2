import json
from copy import deepcopy
import pytest
from core import race_odds as o
from tests.test_race_odds import identity,quote

def test_reimport_popularity_partial_no_old_values():
 q=quote(n=3);q['popularity']={'1':2,'2':1};v=o.validate(q,identity(n=3))
 rows=[dict(no=str(i),score='80',rank=str(i),mark='◎',sort_values={}) for i in range(1,4)]
 before=deepcopy(rows);out=o.overlay(rows,v,'取込')
 assert rows==before and out[0]['popularity']==2 and out[2]['popularity'] is None
 q['prices']=[dict(kind='win',horses=[2],low=8.6,high=8.6)];q['popularity']={'2':3}
 new=o.validate(q,identity(n=3));out2=o.overlay(out,new,'再取込')
 assert out2[0]['odds']=='—' and out2[0]['popularity'] is None
 assert out2[1]['odds']=='8.6' and out2[1]['sort_values']['popularity']==3
 assert all(h['score']=='80' and h['mark']=='◎' for h in out2)
 assert new['observation_id']!=v['observation_id']

@pytest.mark.parametrize('p',[{'4':1},{'1':0},{'1':1.5},{'1':True}])
def test_invalid_popularity_rejected(p):
 q=quote(n=3);q['popularity']=p
 with pytest.raises(ValueError):o.validate(q,identity(n=3))

def test_explicit_html_popularity_only():
 html='''<link rel="canonical" href="https://race.netkeiba.com/odds/index.html?race_id=202608040511"><table><tr><th>馬番</th><th>馬名</th><th>単勝</th><th>人気</th></tr><tr><td>2</td><td>馬2</td><td>8.6</td><td>3</td></tr><tr><td>1</td><td>馬1</td><td>2.1</td><td>—</td></tr></table>'''
 q=o.import_files([('odds.html',html.encode())],identity(n=3))[0]
 assert q['popularity']=={'2':3}
 out=o.overlay([dict(no='1'),dict(no='2')],q,'HTML')
 assert out[0]['popularity'] is None and out[1]['popularity']==3


def test_screenshot_explicit_popularity_preserved():
 from core import race_odds_screenshot as s
 from tests.test_race_odds_screenshot import identity as sid,rows as srows
 r=srows();r[0]['人気']='2'
 draft=dict(imported_at='2026-10-18T14:35:00+09:00',version='fixture',sources=[],rows=r)
 q=s.confirmed_quote(r,sid(),draft,confirmed=True)
 assert q['popularity']=={str(r[0]['馬番']):2}
