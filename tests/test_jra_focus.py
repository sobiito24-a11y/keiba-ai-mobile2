import copy
from core.jra_focus import annotate, partition, evidence_groups
from core.game_race_ui import candidate_badge

def test_focus_retains_original_predictions_and_caps():
    rows=[dict(no=str(n),mode='jra',rank=str(n),mark='✔',score=100-n,formal_member=n<=5) for n in range(4,12)]
    original=copy.deepcopy(rows);annotate(rows)
    assert [h['no'] for h in rows if h.get('focus_label')=='注目']==['6','7']
    assert all(all(h[k]==v for k,v in old.items()) for h,old in zip(rows,original))
    main,other=partition(rows,list(range(len(rows))))
    assert len(main)+len(other)==len(rows)
    assert '注目' in candidate_badge(rows[2]) and '最終印' in candidate_badge(rows[0])

def test_no_fill_and_nar_unchanged():
    rows=[dict(no='1',mode='jra',rank='9',mark='✔'),dict(no='2',mode='nar',rank='6',mark='✓')]
    nar=rows[1].copy();annotate(rows)
    assert rows[0]['focus_label']=='参考' and rows[1]==nar

def test_correlated_evidence_not_double_counted():
    assert evidence_groups(dict(candidate_evidence=dict(audit=dict(ability={},course={},distance={}))))==['能力・適性']

def test_missing_rank_and_green_not_focus():
    rows=[dict(no='1',mode='jra',rank='—',mark='✔'),dict(no='2',mode='jra',rank='6',mark='✓')]
    annotate(rows)
    assert all(h['focus_label']=='参考' for h in rows)
    assert 'green-reference' in candidate_badge(rows[1])
