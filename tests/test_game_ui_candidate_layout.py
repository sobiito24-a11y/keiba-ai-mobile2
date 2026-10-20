from copy import deepcopy
from bs4 import BeautifulSoup
from core.game_race_ui import candidate_html
from core.game_ui_candidate_evidence import candidates

def test_accessible_single_row_per_candidate_and_no_mutation():
 view=[dict(no=str(i),name='保存馬'+str(i),frame=3,mark='✔︎',rank=str(i),score='80.2',ability_rank='3') for i in range(1,14)]
 before=deepcopy(view);doc=BeautifulSoup(candidate_html(view,candidates(view,'')),'html.parser')
 assert len(doc.select('[data-accordion]'))==13
 assert len(doc.select('.candidate-panel[hidden]'))==13
 for b in doc.select('[data-accordion]'):
  assert b['aria-expanded']=='false' and doc.find(id=b['aria-controls'])
  assert '80.2' in b.text and '純能力3位' in b.text
 assert view==before

def test_missing_values_and_escaping():
 view=[dict(no='1',name='<script>馬</script>',frame=None,mark='✓',rank='—',score='—',ability_rank='—')]
 doc=BeautifulSoup(candidate_html(view,candidates(view,'')),'html.parser')
 assert not doc.select('script') and doc.select_one('.frame.missing')
 assert '—' in doc.select_one('.candidate-score').text
