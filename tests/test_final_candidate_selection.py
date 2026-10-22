from copy import deepcopy

import pytest

from core.final_candidate_selection import candidates, formal_score, select_indices


def view(mode='jra'):
    marks = ['◎', '○', '▲', '✔', '△', '✓', '✓', '✔', '—']
    return [dict(no=str(i), name=f'馬{i}', mode=mode, rank=str(i),
                 score=str(100-i), internal_score=100-i,
                 formal_member=i <= 5, mark=marks[i-1], ability_rank=str(i),
                 corner=i, sort_values={}, reference_score=dict(kind='official', value=100-i))
            for i in range(1, 10)]


@pytest.mark.parametrize('mode', ['jra', 'nar'])
def test_formal_five_plus_one_existing_reference_and_no_mutation(mode):
    horses = list(reversed(view(mode)))
    before = deepcopy(horses)
    indices = select_indices(horses)
    selected = [horses[i] for i in indices]
    assert [h['no'] for h in selected] == ['1', '2', '3', '4', '5', '6']
    assert sum(h['formal_member'] for h in selected) == 5
    assert sum(h['mark'] == '✓' for h in selected) == 1
    assert horses == before
    assert candidates(horses, '最終候補')['rows'] == indices


def test_no_reference_does_not_promote_other_marks_or_research_candidates():
    horses = view()
    for h in horses[5:]:
        h.update(mark='✔', additional_reference=True, focus_label='注目')
    assert [horses[i]['no'] for i in select_indices(horses)] == ['1', '2', '3', '4', '5']


def test_deduplication_favours_formal_entry_and_normalizes_horse_numbers():
    horses = view()
    horses.insert(0, dict(horses[0], no='1.0', formal_member=False, mark='✓'))
    horses.append(dict(horses[3]))
    indices = select_indices(horses)
    assert [horses[i]['no'] for i in indices] == ['1', '2', '3', '4', '5', '6']
    assert all(horses[i]['formal_member'] for i in indices[:5])


def test_display_sort_uses_exact_formal_scores_and_keeps_membership():
    horses = view()
    for h in horses:
        h['candidate_formal_score'] = float(h['no'])
    horses[0]['candidate_formal_score'] = 6.123456789
    horses[5]['candidate_formal_score'] = None
    horses[5]['score'] = 9999
    before = deepcopy(horses)
    by_no, by_score = select_indices(horses), select_indices(horses, 'score')
    assert [horses[i]['no'] for i in by_no] == ['1', '2', '3', '4', '5', '6']
    assert [horses[i]['no'] for i in by_score] == ['1', '5', '4', '3', '2', '6']
    assert set(by_no) == set(by_score)
    assert formal_score(horses[0]) == 6.123456789
    assert formal_score(horses[5]) is None
    assert horses == before


def test_nar_existing_priority_uses_pure_then_corner_then_jockey():
    horses = view('nar')
    horses[5].update(ability_rank='6', corner=5)
    horses[6].update(ability_rank='6', corner=3)
    assert select_indices(horses)[-1] == 6
    horses[5]['corner'] = 3
    horses[5]['reference_selection'] = dict(jockey_place_rate=40)
    horses[6]['reference_selection'] = dict(jockey_place_rate=45)
    assert select_indices(horses)[-1] == 6
    horses[5]['reference_selection']['jockey_place_rate'] = 50
    assert select_indices(horses)[-1] == 5
    # Frozen existing choices precede today's fallback, without rerunning select.
    horses[6]['reference_selection']['source'] = 'saved_nar_check_selected'
    assert select_indices(horses)[-1] == 6


@pytest.mark.parametrize('source6,source7', [
    ('saved_nar_check_selected', 'saved_nar_check_selected'),
    ('saved_overall_display_mark', 'saved_overall_display_mark'),
    ('saved_overall_display_mark', 'saved_nar_check_selected'),
])
def test_nar_frozen_checks_retain_resolve_saved_horse_number_tie_break(source6, source7):
    from core.nar_check_selection import resolve_saved
    horses = view('nar')
    # The higher horse number has better corner/jockey facts.  Saved decisions
    # intentionally use horse number after a tied pure rank, unlike new select.
    horses[5].update(ability_rank='6', corner=6)
    horses[6].update(ability_rank='6', corner=1)
    horses[5]['reference_selection'] = dict(source=source6, pure_rank=6,
                                          corner4_rank=6, jockey_place_rate=20)
    horses[6]['reference_selection'] = dict(source=source7, pure_rank=6,
                                          corner4_rank=1, jockey_place_rate=90)
    raw = [dict(number=int(h['no']), ability_rank=int(h['ability_rank']),
                pure_ability_top5_group=h['formal_member'],
                netkeiba_corner4_rank=h['corner'], current_jockey_place_rate=30)
           for h in horses]
    saved = deepcopy(raw)
    for row, source in zip(saved[5:7], (source6, source7)):
        if source == 'saved_nar_check_selected':
            row['nar_check_selected'] = True
        else:
            row['表示印'] = '✓'
    expected = [str(h['number']) for h in resolve_saved(raw, saved) if h['nar_check_selected']]
    assert expected == ['6']
    before = deepcopy(horses)
    for display in (horses, list(reversed(horses))):
        indices = select_indices(display)
        assert [display[i]['no'] for i in indices if not display[i]['formal_member']] == expected
    assert horses == before


def test_nar_display_reference_equation_is_not_a_formal_score():
    horse = view('nar')[5]
    horse.update(reference_score=dict(kind='reference', value=88.8),
                 internal_score=88.8, score='88.8')
    assert formal_score(horse) is None
    horse['reference_score'] = dict(kind='official', value=0)
    assert formal_score(horse) == 0


def test_active_model_b_formal_membership_and_scores_take_priority():
    horses = view('nar')
    for i, h in enumerate(horses):
        h.update(active_model='B', model_a=dict(rank=h['rank'], mark=h['mark']),
                 candidate_formal_score=999,
                 model_b=dict(score=-i), rank=str(9-i), formal_member=i >= 4)
        if h['formal_member']:
            h['mark'] = '△'
    before = deepcopy(horses)
    indices = select_indices(horses, 'score')
    assert [horses[i]['no'] for i in indices] == ['5', '6', '7', '8', '9']
    assert all(formal_score(horses[i]) == -i for i in indices)
    assert horses == before


def test_model_b_keeps_only_existing_a_reference_outside_b_top5():
    horses = view()
    horses[5].update(active_model='B', model_b=dict(score=12),
                     model_a=dict(mark='✓'), rank='7')
    horses[6].update(mark='—', additional_reference=True)
    assert len(select_indices(horses)) == 6
    assert formal_score(horses[5]) == 12


def test_nar_b_projection_keeps_a_check_priority_and_b_formal_top5():
    from core.model_b_ui import project
    horses = view('nar')
    horses[5]['reference_selection'] = dict(source='saved_nar_check_selected', pure_rank=6,
                                          corner4_rank=4, jockey_place_rate=30)
    horses[6]['reference_selection'] = dict(source='saved_nar_check_selected', pure_rank=7,
                                          corner4_rank=2, jockey_place_rate=50)
    ranks = [1, 2, 3, 8, 9, 7, 6, 4, 5]
    report = dict(status='ready', model_version='saved_b', horses=[
        dict(no=h['no'], rank=rank, score=100-rank,
             mark={1:'◎', 2:'○', 3:'▲', 4:'✔', 5:'△'}.get(rank, ''))
        for h, rank in zip(horses, ranks)])
    before, frozen = deepcopy(horses), deepcopy(report)
    shown = project(horses, report)
    projected = deepcopy(shown)
    indices = select_indices(shown)
    assert [shown[i]['no'] for i in indices] == ['1', '2', '3', '6', '8', '9']
    assert {shown[i]['no'] for i in indices if shown[i]['formal_member']} == {'1', '2', '3', '8', '9'}
    assert [shown[i]['no'] for i in indices if not shown[i]['formal_member']] == ['6']
    assert formal_score(shown[5]) == 93
    assert horses == before and report == frozen and shown == projected


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), True, '未取得'])
def test_missing_scores_never_become_zero(value):
    assert formal_score(dict(mode='jra', candidate_formal_score=value, score=123)) is None


def test_zero_and_negative_scores_are_real_scores():
    horses = view()
    for h in horses:
        h['candidate_formal_score'] = -float(h['no'])
    horses[1]['candidate_formal_score'] = 0
    assert select_indices(horses, 'score')[0] == 1


def test_odds_results_and_materials_do_not_select_or_rerank_candidates():
    horses = view('nar')
    before = select_indices(horses)
    for h in horses:
        h.update(odds=1.1, popularity=1, finish=1, training='D', rest='180日',
                 plus='調教A', caution='休養', additional_reference=True)
    assert select_indices(horses) == before


def test_invalid_order_is_not_silently_treated_as_a_ranking():
    with pytest.raises(ValueError):
        select_indices(view(), 'mark')
