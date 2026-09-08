import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.netkeiba_html_collector import extract_nar_race_list_venue_urls
from tools.netkeiba_html_collector import collect_race_targets_from_list_urls
from tools.netkeiba_html_collector import extract_race_targets_from_links
from tools.netkeiba_html_collector import format_race_target_for_log
from tools.netkeiba_html_collector import get_race_link_items
from tools.netkeiba_html_collector import is_login_like
from tools.netkeiba_html_collector import list_urls_from_dates
from tools.netkeiba_html_collector import main as collector_main
from tools.netkeiba_html_collector import NO_RACES_EXIT_CODE
from tools.netkeiba_html_collector import parse_args
from tools.netkeiba_html_collector import selected_specs


class NetkeibaHtmlCollectorTest(unittest.TestCase):
    def test_jra_default_kinds_collect_prediction_pages_and_jockey_only(self):
        specs = selected_specs("jra", "default")
        kinds = [spec.kind for spec in specs]
        self.assertEqual(["newspaper", "oikiri", "speed", "style", "jockey"], kinds)
        self.assertNotIn("result", kinds)
        self.assertNotIn("shutuba", kinds)

    def test_nar_default_kinds_collect_prediction_pages_and_jockey_only(self):
        specs = selected_specs("nar", "default")
        kinds = [spec.kind for spec in specs]
        self.assertEqual(["newspaper", "speed", "style", "jockey"], kinds)
        self.assertNotIn("result", kinds)
        self.assertNotIn("shutuba", kinds)

    def test_result_and_shutuba_remain_explicitly_supported(self):
        specs = selected_specs("nar", "result,shutuba")
        self.assertEqual(["result", "shutuba"], [spec.kind for spec in specs])

    def test_jra_jockey_courseanalysis_is_a_supported_collection_page(self):
        specs = selected_specs("jra", "jockey")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].kind, "jockey")
        self.assertIn("race.netkeiba.com", specs[0].url_template)
        self.assertIn("mode=courseanalysis", specs[0].url_template)
        self.assertIn("cid=2", specs[0].url_template)

    def test_nar_jockey_courseanalysis_is_a_supported_collection_page(self):
        specs = selected_specs("nar", "jockey")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].kind, "jockey")
        self.assertIn("mode=courseanalysis", specs[0].url_template)
        self.assertIn("cid=2", specs[0].url_template)

    def test_accepts_visible_race_id_links_without_path_restriction(self):
        links = [
            {
                "href": "https://race.netkeiba.com/race/list_card_link.html?race_id=202607020201&rf=race_list",
                "text": "新潟1R",
                "race_id": "202607020201",
                "venue": "新潟",
                "race_number": "1R",
            },
            {
                "href": "https://race.netkeiba.com/race/another_card_link.html?race_id=202607020202",
                "text": "新潟2R",
                "race_id": "202607020202",
                "venue": "新潟",
                "race_number": "2R",
            },
        ]

        targets = extract_race_targets_from_links("jra", links)

        self.assertEqual(["202607020201", "202607020202"], [target.race_id for target in targets])
        self.assertEqual("新潟1R 202607020201", format_race_target_for_log(targets[0]))

    def test_keeps_first_visible_link_for_duplicate_race_id(self):
        links = [
            {
                "href": "https://race.netkeiba.com/race/first.html?race_id=202607020201",
                "text": "新潟1R",
                "race_id": "202607020201",
                "venue": "新潟",
                "race_number": "1R",
            },
            {
                "href": "https://race.netkeiba.com/race/second.html?race_id=202607020201",
                "text": "新潟1R duplicated",
                "race_id": "202607020201",
                "venue": "新潟",
                "race_number": "1R",
            },
        ]

        targets = extract_race_targets_from_links("jra", links)

        self.assertEqual(1, len(targets))
        self.assertEqual("https://race.netkeiba.com/race/first.html?race_id=202607020201", targets[0].source_url)

    def test_guest_text_alone_is_not_login_like(self):
        html = """
        <html>
          <head><title>レース情報</title></head>
          <body>
            <header>ゲストさん ログイン 会員メニュー</header>
            <main>七夕賞 競馬新聞 タイム指数</main>
          </body>
        </html>
        """

        self.assertFalse(is_login_like("https://race.netkeiba.com/race/newspaper.html?race_id=202610020810", html))

    def test_password_form_is_login_like(self):
        html = """
        <html>
          <body>
            <form id="login_form" action="/account/login">
              <input type="password" name="password">
            </form>
          </body>
        </html>
        """

        self.assertTrue(is_login_like("https://regist.netkeiba.com/account/?pid=login", html))

    def test_today_and_date_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            parse_args(["--mode", "nar", "--today", "--date", "20260908"])

    def test_nar_date_builds_race_list_url(self):
        self.assertEqual(
            list_urls_from_dates("nar", ["2026-09-08"]),
            ["https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908"],
        )

    def test_nar_date_venue_links_are_all_discovered(self):
        current = "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908"
        items = [
            {"href": "/top/race_list.html?kaisai_date=20260908&jyo_cd=45", "text": "川崎"},
            {"href": "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=48", "text": "名古屋"},
            {"href": "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=36", "text": "水沢"},
            {"href": "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260907&jyo_cd=45", "text": "前日"},
            {"href": "https://race.netkeiba.com/top/race_list.html?kaisai_date=20260908", "text": "JRA"},
        ]

        urls = extract_nar_race_list_venue_urls(items, current, "20260908")

        self.assertEqual(
            urls,
            [
                current,
                "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=45",
                "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=48",
                "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=36",
            ],
        )

    def test_nar_date_venue_link_without_date_inherits_current_date(self):
        current = "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908"
        items = [
            {"href": "/top/race_list.html?jyo_cd=45", "text": "川崎"},
        ]

        urls = extract_nar_race_list_venue_urls(items, current, "20260908")

        self.assertEqual(
            urls,
            [
                current,
                "https://nar.netkeiba.com/top/race_list.html?jyo_cd=45&kaisai_date=20260908",
            ],
        )

    def test_get_race_link_items_uses_single_playwright_argument_object(self):
        calls = []

        class StrictPage:
            def eval_on_selector_all(self, selector, expression, arg=None):
                calls.append((selector, expression, arg))
                return []

        get_race_link_items(StrictPage(), "nar", visible_only=False)

        self.assertEqual(1, len(calls))
        self.assertEqual('a[href*="race_id="]', calls[0][0])
        self.assertEqual({"mode": "nar", "visibleOnly": False}, calls[0][2])

    def test_main_returns_dedicated_no_races_exit_code_for_empty_race_list(self):
        class EmptyRaceListPage:
            url = "https://race.netkeiba.com/top/race_list.html?kaisai_date=20260909"

            def set_default_timeout(self, _timeout):
                return None

            def goto(self, url, **_kwargs):
                self.url = url

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, *_args, **_kwargs):
                return None

            def content(self):
                return "<html><body>レース一覧</body></html>"

            def eval_on_selector_all(self, selector, expression, arg=None):
                return []

        class FakeContext:
            def __init__(self):
                self.pages = [EmptyRaceListPage()]

            def new_page(self):
                return EmptyRaceListPage()

            def close(self):
                return None

        class FakeChromium:
            def launch_persistent_context(self, *_args, **_kwargs):
                return FakeContext()

        class FakePlaywright:
            chromium = FakeChromium()

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        def fake_sync_playwright():
            return FakePlaywright()

        with tempfile.TemporaryDirectory() as temp:
            with patch("tools.netkeiba_html_collector.import_playwright", return_value=(fake_sync_playwright, TimeoutError)):
                exit_code = collector_main(
                    [
                        "--mode",
                        "jra",
                        "--date",
                        "20260909",
                        "--out",
                        str(Path(temp) / "html"),
                        "--profile-dir",
                        str(Path(temp) / "profile"),
                        "--no-pause-on-login",
                    ]
                )

        self.assertEqual(NO_RACES_EXIT_CODE, exit_code)

    def test_race_list_read_error_is_not_treated_as_no_races(self):
        current = "https://race.netkeiba.com/top/race_list.html?kaisai_date=20260909"

        class BrokenRaceListPage:
            url = current

            def goto(self, url, **_kwargs):
                self.url = url

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, *_args, **_kwargs):
                return None

            def content(self):
                return "<html><body>レース一覧</body></html>"

            def eval_on_selector_all(self, selector, expression, arg=None):
                raise RuntimeError("DOM read failed")

        args = parse_args(["--mode", "jra", "--date", "20260909", "--no-pause-on-login"])

        with self.assertRaises(RuntimeError):
            collect_race_targets_from_list_urls(BrokenRaceListPage(), [current], args, TimeoutError)

    def test_nar_date_collection_reads_all_detected_venue_pages(self):
        current = "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908"
        venue_urls = [
            "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=45",
            "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=48",
            "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20260908&jyo_cd=36",
        ]

        class FakePage:
            url = current

            def goto(self, url, **_kwargs):
                self.url = url

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, *_args, **_kwargs):
                return None

            def content(self):
                return "<html><body>地方競馬レース一覧</body></html>"

            def eval_on_selector_all(self, selector, expression, arg=None):
                if selector == "a[href]":
                    assert arg is None
                    return [{"href": url, "text": f"venue {index}"} for index, url in enumerate(venue_urls, start=1)]
                assert isinstance(arg, dict)
                assert arg["mode"] == "nar"
                assert arg["visibleOnly"] is False
                race_links = {
                    venue_urls[0]: [
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202645090801", "text": "川崎1R", "race_id": "202645090801", "venue": "川崎", "race_number": "1R"},
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202645090802", "text": "川崎2R", "race_id": "202645090802", "venue": "川崎", "race_number": "2R"},
                    ],
                    venue_urls[1]: [
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202648090801", "text": "名古屋1R", "race_id": "202648090801", "venue": "名古屋", "race_number": "1R"},
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202648090802", "text": "名古屋2R", "race_id": "202648090802", "venue": "名古屋", "race_number": "2R"},
                    ],
                    venue_urls[2]: [
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202636090801", "text": "水沢1R", "race_id": "202636090801", "venue": "水沢", "race_number": "1R"},
                        {"href": "https://nar.netkeiba.com/race/newspaper.html?race_id=202636090802", "text": "水沢2R", "race_id": "202636090802", "venue": "水沢", "race_number": "2R"},
                    ],
                }
                return race_links.get(self.url, [])

        args = parse_args(["--mode", "nar", "--date", "20260908", "--no-pause-on-login"])

        targets = collect_race_targets_from_list_urls(FakePage(), [current], args, TimeoutError)

        self.assertEqual(
            [target.race_id for target in targets],
            [
                "202645090801",
                "202645090802",
                "202648090801",
                "202648090802",
                "202636090801",
                "202636090802",
            ],
        )


if __name__ == "__main__":
    unittest.main()
