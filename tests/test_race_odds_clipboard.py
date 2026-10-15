import base64
from copy import deepcopy
import pytest
from core.race_odds_clipboard import decode_images
from core.race_odds_screenshot import review_issues
from tests.test_race_odds_screenshot import png,identity,rows


def test_clipboard_bytes_without_file_path():
    value={'images':[{'mime':'image/png','base64':base64.b64encode(png()).decode()}]}
    before=deepcopy(value)
    files=decode_images(value)
    assert files[0][1]==png() and value==before
    assert decode_images(None)==[] and decode_images({'images':[]})==[]


@pytest.mark.parametrize('value',[
    [],{}, {'images':None},{'images':[None]}, {'images':[{}]},
    {'images':[{'mime':'text/html','base64':'abcd'}]},
    {'images':[{'mime':'image/png','base64':'***'}]},
    {'images':[{'mime':'image/png','base64':base64.b64encode(b'bad image').decode()}]},
    {'images':[{}]*6},
])
def test_invalid_clipboard_rejected(value):
    with pytest.raises(ValueError):decode_images(value)


def test_suspect_but_valid_leading_digit_omission_is_flagged_not_corrected():
    row=rows()[0];row['単勝']='7.1'
    row['_ocr_cells']={'単勝':{'primary':'7.1','alternative':'57.1','disagreement':True}}
    before=deepcopy(row)
    assert any('単勝' in text for text in review_issues(row,identity()))
    assert row==before


def test_review_flags_name_mismatch_and_reverse_range():
    row=rows()[0];row.update(馬名='別馬',複勝下限='8.0',複勝上限='1.0')
    issues=review_issues(row,identity())
    assert any('不一致' in s for s in issues) and any('逆転' in s for s in issues)
