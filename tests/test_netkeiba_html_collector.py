import unittest

from tools.netkeiba_html_collector import extract_race_targets_from_links
from tools.netkeiba_html_collector import format_race_target_for_log
from tools.netkeiba_html_collector import is_login_like
from tools.netkeiba_html_collector import selected_specs


class NetkeibaHtmlCollectorTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
