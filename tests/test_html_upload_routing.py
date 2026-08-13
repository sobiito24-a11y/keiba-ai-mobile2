from __future__ import annotations

import unittest

from core.html_classifier import classify_html, classify_many, validate_upload_bundle


def page_html(
    mode: str,
    kind: str,
    race_id: str = "202604020609",
    *,
    include_canonical: bool = True,
    include_og_url: bool = True,
    include_self_url: bool = True,
    title: str | None = None,
) -> str:
    host = "nar.netkeiba.com" if mode == "nar" else "race.netkeiba.com"
    mobile_host = "nar.sp.netkeiba.com" if mode == "nar" else "race.sp.netkeiba.com"
    path = {
        "newspaper": "newspaper.html",
        "speed": "speed.html",
        "style": "data_list.html",
        "oikiri": "oikiri.html",
    }[kind]
    query = f"race_id={race_id}"
    if kind == "style":
        query += "&amp;mode=courseanalysis&amp;cid=1"
    url = f"https://{host}/race/{path}?{query}"
    mobile_url = f"https://{mobile_host}/race/{path}?{query}"
    titles = {
        "newspaper": "競馬新聞",
        "speed": "タイム指数",
        "style": "有利な脚質 データ分析",
        "oikiri": "調教タイム・追い切り",
    }
    title_text = title if title is not None else f"テストレース {titles[kind]} ({mode.upper()})"
    canonical = f'<link rel="canonical" href="{url}">' if include_canonical else ""
    og_url = f'<meta property="og:url" content="{url}">' if include_og_url else ""
    self_url = (
        f'<link rel="alternate" media="only screen and (max-width: 640px)" href="{mobile_url}">'
        f'<script type="application/ld+json">{{"@id":"{url}"}}</script>'
        if include_self_url
        else ""
    )
    body = {
        "newspaper": '<body id="Netkeiba_Race_Newspaper"><div data-is="riot-shutuba-past"></div></body>',
        "speed": '<body id="Netkeiba_Race_Speed"><table class="Speed_List"><tr></tr></table></body>',
        "style": '<body class="race_data_list"><div class="DataGraphWrap1"><canvas id="score1"></canvas></div></body>',
        "oikiri": '<body id="Netkeiba_Race_Oikiri" class="page_race_oikiri"><table class="Oikiri_Table"></table></body>',
    }[kind]
    return f"<!doctype html><html><head><title>{title_text}</title>{canonical}{og_url}{self_url}</head>{body}</html>"


class HtmlUploadRoutingTest(unittest.TestCase):
    def test_jra_newspaper_is_newspaper(self) -> None:
        item = classify_html("keiba_data.html", page_html("jra", "newspaper"), "jra")
        self.assertEqual(item.kind, "newspaper")
        self.assertEqual(item.meta.detected_mode, "jra")
        self.assertEqual(item.meta.race_id, "202604020609")

    def test_jra_speed_is_speed(self) -> None:
        item = classify_html("keiba_data.html", page_html("jra", "speed"), "jra")
        self.assertEqual(item.kind, "speed")
        self.assertEqual(item.meta.detected_mode, "jra")

    def test_nar_newspaper_is_newspaper(self) -> None:
        item = classify_html("keiba_data.html", page_html("nar", "newspaper"), "nar")
        self.assertEqual(item.kind, "newspaper")
        self.assertEqual(item.meta.detected_mode, "nar")

    def test_nar_speed_is_speed(self) -> None:
        item = classify_html("keiba_data.html", page_html("nar", "speed"), "nar")
        self.assertEqual(item.kind, "speed")
        self.assertEqual(item.meta.detected_mode, "nar")

    def test_newspaper_speed_and_style_are_kept_as_distinct_kinds(self) -> None:
        for mode in ("jra", "nar"):
            with self.subTest(mode=mode):
                race_id = "202604020609" if mode == "jra" else "202655080903"
                grouped = classify_many(
                    [
                        ("same-name.html", page_html(mode, "newspaper", race_id).encode()),
                        ("same-name.html", page_html(mode, "speed", race_id).encode()),
                        ("same-name.html", page_html(mode, "style", race_id).encode()),
                    ],
                    mode,
                )
                self.assertEqual(set(grouped), {"newspaper", "speed", "style"})
                self.assertTrue(all(len(grouped[kind]) == 1 for kind in grouped))
                validation = validate_upload_bundle(grouped, mode)
                self.assertTrue(validation.is_valid)
                self.assertEqual(validation.race_id, race_id)

    def test_content_wins_after_files_are_renamed_to_the_wrong_kind(self) -> None:
        speed = classify_html("newspaper.html", page_html("jra", "speed"), "jra")
        newspaper = classify_html("speed.html", page_html("jra", "newspaper"), "jra")
        self.assertEqual(speed.kind, "speed")
        self.assertTrue(speed.reasons[0].startswith("canonical:"))
        self.assertEqual(newspaper.kind, "newspaper")
        self.assertTrue(newspaper.reasons[0].startswith("canonical:"))

    def test_self_page_url_is_used_when_canonical_and_og_are_missing(self) -> None:
        item = classify_html(
            "renamed.html",
            page_html("jra", "speed", include_canonical=False, include_og_url=False),
            "jra",
        )
        self.assertEqual(item.kind, "speed")
        self.assertTrue(item.reasons[0].startswith("page url:"))

    def test_dom_is_used_before_misleading_title_and_filename(self) -> None:
        html = page_html(
            "jra",
            "speed",
            include_canonical=False,
            include_og_url=False,
            include_self_url=False,
            title="競馬新聞 JRA",
        )
        item = classify_html("newspaper.html", html, "jra")
        self.assertEqual(item.kind, "speed")
        self.assertTrue(item.reasons[0].startswith(("body id:", "dom marker:", "table id/class:")))

    def test_unidentifiable_html_is_unknown_and_not_routed(self) -> None:
        grouped = classify_many([("newspaper.html", b"<html><body><p>plain</p></body></html>")], "jra")
        self.assertEqual(set(grouped), {"newspaper"})

        truly_unknown = classify_many([("renamed.html", b"<html><body><p>plain</p></body></html>")], "jra")
        self.assertEqual(set(truly_unknown), {"unknown"})
        self.assertEqual(truly_unknown["unknown"][0].label, "不明なHTML")

    def test_conflicting_canonical_and_og_url_is_unknown(self) -> None:
        html = page_html("jra", "speed").replace(
            'property="og:url" content="https://race.netkeiba.com/race/speed.html',
            'property="og:url" content="https://race.netkeiba.com/race/newspaper.html',
        )
        self.assertEqual(classify_html("speed.html", html, "jra").kind, "unknown")

    def test_race_id_mismatch_is_an_error(self) -> None:
        grouped = classify_many(
            [
                ("a.html", page_html("jra", "newspaper", "202604020609").encode()),
                ("b.html", page_html("jra", "speed", "202604020610").encode()),
            ],
            "jra",
        )
        validation = validate_upload_bundle(grouped, "jra")
        self.assertFalse(validation.is_valid)
        self.assertTrue(any("race_idが一致していません" in error for error in validation.errors))

    def test_jra_nar_mode_mismatch_is_an_error(self) -> None:
        grouped = classify_many(
            [("nar.html", page_html("nar", "newspaper", "202655080903").encode())],
            "jra",
        )
        validation = validate_upload_bundle(grouped, "jra")
        self.assertFalse(validation.is_valid)
        self.assertTrue(any("JRAモードとは一致しません" in error for error in validation.errors))

    def test_duplicate_kind_is_preserved_and_warned_not_overwritten(self) -> None:
        grouped = classify_many(
            [
                ("newspaper-a.html", page_html("jra", "newspaper").encode()),
                ("newspaper-b.html", page_html("jra", "newspaper").encode()),
            ],
            "jra",
        )
        self.assertEqual(len(grouped["newspaper"]), 2)
        validation = validate_upload_bundle(grouped, "jra")
        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.duplicate_kinds, ("newspaper",))
        self.assertTrue(any("自動上書きせず" in warning for warning in validation.warnings))

    def test_pc_and_mobile_names_take_the_same_content_route(self) -> None:
        html = page_html("jra", "speed").encode()
        pc = classify_many([("download (12).html", html)], "jra")
        mobile = classify_many([("iPhoneショートカット.html", html)], "jra")
        self.assertEqual(next(iter(pc)), "speed")
        self.assertEqual(next(iter(mobile)), "speed")
        self.assertEqual(pc["speed"][0].meta.race_id, mobile["speed"][0].meta.race_id)

    def test_courseanalysis_and_oikiri_are_separate(self) -> None:
        style = classify_html("renamed.html", page_html("jra", "style"), "jra")
        oikiri = classify_html("renamed.html", page_html("jra", "oikiri"), "jra")
        self.assertEqual(style.kind, "style")
        self.assertEqual(oikiri.kind, "oikiri")


if __name__ == "__main__":
    unittest.main()
