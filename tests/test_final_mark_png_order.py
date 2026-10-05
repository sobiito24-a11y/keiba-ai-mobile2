import copy
import pandas as pd
import pytest
from core.models import PredictionResult


@pytest.mark.parametrize("ranks", [False, True])
def test_nar_png_keeps_web_order_and_marks(ranks):
    import app
    from render.mobile_png import _prediction_detail_records
    rows = [dict(number=n, name=f"horse{n}", ability_rank=i if ranks else None,
                 ver3_ability_core=60-i) for i,n in enumerate([3,5,7,4,6,8,1,2],1)]
    result = PredictionResult(race_mode="nar", race_info={},
                              horse_evaluation=pd.DataFrame(rows), overall_table=pd.DataFrame(rows))
    before=copy.deepcopy(result)
    assert app.prediction_detail_records(result) == _prediction_detail_records(result)
    pd.testing.assert_frame_equal(result.horse_evaluation,before.horse_evaluation)
    pd.testing.assert_frame_equal(result.overall_table,before.overall_table)
