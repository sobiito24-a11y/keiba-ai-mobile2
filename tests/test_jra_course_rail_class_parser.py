"""A/B track-rail lettering must never masquerade as JRA class A級/B級."""
import pytest
from bs4 import BeautifulSoup

from core.jra_notebook_logic import race_class_info_from_soup


def _html(condition: str, rail: str = "A", title: str = "特別競走", grade: str = ""):
    return BeautifulSoup(
        f'<div class="RaceName">{title}<span class="{grade}"></span></div>'
        f'<div class="RaceData01">14:00発走 / 芝1800m 右 {rail}</div>'
        f'<div class="RaceData02">{condition}</div>',
        "html.parser",
    )


@pytest.mark.parametrize("condition,rail,expected", [
    ("サラ系3歳以上 1勝クラス [指定] 定量", "A", (30, "1勝")),
    ("サラ系3歳以上 1勝クラス", "B", (30, "1勝")),
    ("サラ系3歳以上 2勝クラス", "B", (40, "2勝")),
    ("サラ系3歳以上 3勝クラス", "B", (50, "3勝")),
    ("サラ系3歳以上 オープン", "A", (60, "OP")),
    ("サラ系2歳 未勝利", "B", (20, "未勝利")),
])
def test_explicit_jra_class_overrides_turf_course_lane(condition, rail, expected):
    assert race_class_info_from_soup(_html(condition, rail)) == expected


def test_named_graded_race_grade_icon_overrides_generic_open():
    soup = _html("サラ系2歳 オープン", "B", "デイリー杯2歳S", "Icon_GradeType2")
    assert race_class_info_from_soup(soup) == (80, "G2")


def test_rail_without_class_does_not_become_local_a_or_b():
    for lane in ("A", "B", "C"):
        soup = _html("サラ系3歳以上 [指定] 定量", lane)
        assert race_class_info_from_soup(soup) == (None, "")


def test_explicit_nar_a_class_still_supported():
    soup = _html("サラ系一般 A級", "")
    assert race_class_info_from_soup(soup) == (64, "A級")


def test_db_netkeiba_smalltxt_class_outweighs_racedata_course_rail():
    soup = BeautifulSoup(
        '<div class="data_intro">'
        '<h1>春風特別</h1>'
        '<div class="racedata">芝1400m B</div>'
        '<p class="smalltxt">3歳以上 2勝クラス</p>'
        '</div>', "html.parser",
    )
    assert race_class_info_from_soup(soup) == (40, "2勝")
