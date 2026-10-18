import unittest
from copy import deepcopy
from core.jra_corner4_shadow import select

class Corner4ShadowTest(unittest.TestCase):
    def _view(self):
        return [dict(no=str(i), name=f"馬{i}",mode="jra", mark="◎" if i == 1 else "✓",
                     ability_rank=str(i), rank=str(i), corner=i)
                for i in range(1,9)]

    def test_straightforward(self):
        view=self._view()
        before=deepcopy(view)
        result=select(view,"202610180101")
        self.assertEqual(result["status"],"ready")
        self.assertEqual([h["no"] for h in result["baseline"]],[1,2,3])
        self.assertEqual([h["no"] for h in result["shadow"]],[1,2,3])
        self.assertEqual(view,before)
        self.assertEqual(result["input_sha256"],select(view,"202610180101")["input_sha256"])

    def test_front_filter_and_fallback(self):
        view=self._view()
        for h in view:
            h["corner"]={1:7,2:5,3:1,4:2,5:4,6:3,7:8,8:6}[int(h["no"])]
        result=select(view,"202610180102")
        self.assertEqual([h["no"] for h in result["shadow"]],[3,4,5])
        view[4]["corner"]=7
        result=select(view,"202610180102")
        self.assertEqual([h["no"] for h in result["shadow"]],[3,4,1])
        self.assertIn("補充",result["shadow"][-1]["selection_reason"])

    def test_missing_corner_no_false_position(self):
        view=self._view();view[0]["corner"]=None
        self.assertEqual(select(view,"x")["status"],"unavailable")

    def test_nar_unaffected(self):
        view=self._view();view[0]["mode"]="nar"
        self.assertEqual(select(view,"x")["status"],"unavailable")

    def test_missing_ability_and_duplicate_numbers(self):
        view=self._view();view[0]['ability_rank']=None
        self.assertEqual(select(view,'x')['status'],'unavailable')
        view=self._view();view[1]['no']=view[0]['no']
        self.assertEqual(select(view,'x')['status'],'unavailable')

    def test_frozen_record_is_separate_and_odds_not_inferred(self):
        from core.jra_corner4_shadow import freeze
        import hashlib,json
        view=self._view();before=deepcopy(view)
        record=freeze(view,'202608040711','2026-10-18T00:00:00+00:00')
        self.assertEqual(view,before)
        self.assertIsNone(record['odds_observations'][0]['displayed_odds'])
        check=deepcopy(record);sha=check.pop('record_sha256')
        self.assertEqual(sha,hashlib.sha256(json.dumps(check,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        view[0]['corner']=12
        self.assertEqual(record['frozen_input']['input'][0]['corner4_rank'],1)
        self.assertFalse(record['pre_start_verified'])

    def test_ties_mark_priority_and_results_ignored(self):
        view=self._view()
        for h in view:h['ability_rank']=1
        view[0]['mark']='✔︎';view[1]['mark']='✓'
        self.assertEqual(select(view,'x')['baseline'][0]['no'],1)
        prior=select(view,'x')
        view[0].update(actual_corner4_rank=18,finish=1,odds=99)
        self.assertEqual(select(view,'x'),prior)

    def test_unmarked_not_eligible(self):
        view=self._view();view[0]["mark"]="—"
        self.assertNotIn(1,[h["no"] for h in select(view,"x")["shadow"]])

class HistoricalGoldenReproduction(unittest.TestCase):
    def test_jra_90_races_match_saved_policy(self):
        import json
        from pathlib import Path
        fixture = Path(__file__).parent / 'fixtures' / 'jra_corner4_90r_golden.json'
        cases = json.loads(fixture.read_text(encoding='utf-8'))
        self.assertEqual(len(cases), 90)
        for case in cases:
            with self.subTest(race=case['race_id']):
                report = select(case['horses'],case['race_id'])
                self.assertEqual(report['status'],'ready')
                self.assertEqual([h['no'] for h in report['shadow']], case['expected'])


if __name__ == "__main__":
    unittest.main()
