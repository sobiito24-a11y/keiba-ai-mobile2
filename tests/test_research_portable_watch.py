import copy,json,hashlib
import pytest
from core.new_ai_research import VERSION,CONFIG,digest
from core.research_portable import validate
from core.nar_research_watch import select,html

def test_portable_hash_and_version():
 raw=b'original';p={'keiba_sha256':hashlib.sha256(raw).hexdigest(),'version':VERSION,'config':CONFIG,'config_sha256':digest(CONFIG)}
 pack=lambda:json.dumps({'payload':p,'payload_sha256':digest(p)})
 assert validate(pack(),raw)==p
 with pytest.raises(ValueError):validate(pack(),b'changed')
 p['version']='other'
 with pytest.raises(ValueError):validate(pack(),raw)

def test_no_ability_or_corner_ceiling_and_no_mutation():
 rows=[dict(no=1,formal_rank=9,ability_rank=9,corner=12,course_rank=1,distance_rank=2),dict(no=2,formal_rank=1,course_rank=1,distance_rank=1)]
 before=copy.deepcopy(rows)
 assert [r['no'] for r in select(rows)]==[1]
 assert rows==before
 assert select([dict(no=3,formal_rank=8)])==[]
 assert len(select([dict(no=i,formal_rank=9+i,course_rank=1,distance_rank=1) for i in range(5)]))==2

def test_rejected_hypothesis_not_adopted():
 assert '採用注目馬：0頭' in html([dict(no=1,name='A',rank=9,mode='nar',course={'rank':1},distance={'rank':2})])
 assert html([dict(mode='jra')])==''


def test_nar_hidden_outside_rank_is_not_a_mismatch():
 from core.new_ai_research_ui import formal_rank_matches
 h={'mode':'nar','rank':'—','formal_member':False}
 assert formal_rank_matches(h,{'formal_rank':8})
 assert not formal_rank_matches(h,{'formal_rank':2})
 assert not formal_rank_matches({**h,'formal_member':True},{'formal_rank':8})
 assert not formal_rank_matches({**h,'mode':'jra'},{'formal_rank':8})
