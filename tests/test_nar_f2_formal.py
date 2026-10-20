import copy
from types import SimpleNamespace
from core import nar_f2_formal as f
from core.nar_top5_order import annotate, FIELDS
from core.nar_check_selection import select
from core.nar_display_mark import formal_mark


def fixture():
    rows=[dict(馬番=i,馬名=str(i),market_ability_score=20-i,ver3_ability_core=20-i,
        market_ability_rank=i,netkeiba_corner4_rank=i) for i in range(1,8)]
    old=annotate(rows)
    legacy=dict(model_version='legacy',horses=[dict(horse_no=str(x['馬番']),pure_ability_rank=x['market_ability_rank'],**{k:x.get(k) for k in FIELDS}) for x in old],pure_ability_top5_group=['1','2','3','4','5'])
    stats={(str(i),kind):dict(starts=100,top3=100 if i==6 else 0) for i in range(1,8) for kind in ['jockey','style']}
    return rows,legacy,stats


def test_outside_pure_top5_promoted_and_no_mutation():
    rows,old,stats=fixture();before=copy.deepcopy((rows,old,stats))
    out=f.evaluate(rows,old,stats)
    assert (rows,old,stats)==before
    six=next(h for h in out['horses'] if h['horse_no']=='6')
    assert six['nar_final_rank']==1 and six['nar_final_mark']=='◎'
    assert not six['nar_original_pure_top5_group'] and six['nar_formal_top5_member']
    assert out['legacy_comparison']==old
    assert [formal_mark(h) for h in sorted(out['horses'],key=lambda x:x['nar_final_rank'])][:5]==['◎','○','▲','✔︎','△']
    merged=[dict(row,**h) for row,h in zip(rows,out['horses'])]
    assert not any(h['nar_check_selected'] and h['pure_ability_top5_group'] for h in select(merged))


def test_missing_falls_back_and_records_reason():
    rows,old,stats=fixture();del stats[('1','style')]
    out=f.evaluate(rows,old,stats)
    assert not out['f2_audit']['complete'] and 'style:unavailable' in out['f2_audit']['fallback_reasons']
    assert [h['nar_final_rank'] for h in out['horses']]==[h['nar_final_rank'] for h in old['horses']]


def test_missing_legacy_input_undetermined():
    rows,old,stats=fixture();rows[0]['market_ability_score']=None
    out=f.evaluate(rows,old,stats)
    assert out['horses'][0]['nar_final_rank'] is None
    assert out['horses'][0]['nar_final_mark']==''


def test_jra_no_op_and_rollback(monkeypatch):
    result=SimpleNamespace(race_mode='jra')
    assert f.attach_new(result,{}) is result
    rows,old,stats=fixture();monkeypatch.setattr(f,'POLICY','legacy')
    out=f.evaluate(rows,old,stats)
    assert out['model_version']=='legacy'
    assert out['f2_audit']['complete']
    assert out['f2_audit']['fallback_reasons']==['policy_legacy']


def test_score_matches_reference_addition_order():
    rows,old,stats=fixture()
    out=f.evaluate(rows,old,stats)
    for h in out['f2_audit']['horses']:
        expected=h['ability']
        for kind in ('jockey','style','corner'):
            expected+=h['contributions'][kind]
        assert h['score']==expected
