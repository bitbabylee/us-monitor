import unittest
from datetime import datetime, timezone

from us_monitor import m13_bogo, m15_bogo_cn, m21_bogo_etf


class BogoPdfRowClusteringTests(unittest.TestCase):
    def test_words_across_old_rounding_boundary_stay_in_same_row(self):
        words = [
            {"text": "weak", "top": 202.593420, "x0": 11.78},
            {"text": "300308", "top": 202.245520, "x0": 78.28},
            {"text": "next", "top": 212.100000, "x0": 11.78},
        ]

        lines = m13_bogo._cluster_words_by_top(words)

        self.assertEqual(
            [[word["text"] for word in line] for line in lines],
            [["300308", "weak"], ["next"]],
        )


class BogoImageSelectionTests(unittest.TestCase):
    def test_us_detail_images_include_strong_and_weak_signals(self):
        rows = [
            {"代码": "STRONG", "信号": "strong", "信号日": "08-24"},
            {"代码": "WEAK", "信号": "weak", "信号日": "08-24"},
            {"代码": "OLDER", "信号": "weak", "信号日": "08-20"},
        ]

        self.assertEqual(
            {"STRONG", "WEAK", "OLDER"},
            m13_bogo._image_codes(rows),
        )


class BogoFreshnessTests(unittest.TestCase):
    def test_us_batch_compares_source_to_singapore_date(self):
        ci_utc = datetime(2026, 8, 14, 21, 55, tzinfo=timezone.utc)
        warning = m15_bogo_cn._source_warning(
            "us", "0815 us 1630 bo sig.pdf", now=ci_utc
        )
        self.assertEqual(warning, "")

    def test_us_batch_warns_after_due_on_saturday(self):
        saturday = datetime(2026, 8, 15, 7, 0, tzinfo=m15_bogo_cn.SG)
        warning = m15_bogo_cn._source_warning(
            "us", "0814 us 1630 bo sig.pdf", now=saturday
        )
        self.assertIn("今日源件未到", warning)
        self.assertIn("08-14", warning)

    def test_us_batch_does_not_expect_a_sunday_run(self):
        sunday = datetime(2026, 8, 16, 9, 0, tzinfo=m15_bogo_cn.SG)
        warning = m15_bogo_cn._source_warning(
            "us", "0815 us 1630 bo sig.pdf", now=sunday
        )
        self.assertEqual(warning, "")


class BogoEtfContextTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "dataDate": "2026-08-21",
            "rows": [{
                "tk": "QTUM", "r5": -5.1739, "r21": 4.8791, "r63": 0.9302,
                "trend": "弱势", "position": "回撤中",
            }],
        }

    def test_rgti_maps_to_available_quantum_etf_with_performance(self):
        items = m21_bogo_etf.contexts(
            {"代码": "RGTI", "主题": "量子计算"}, self.snapshot
        )

        self.assertEqual(["QTUM"], [item["tk"] for item in items])
        self.assertIn("5日 -5.2%", m21_bogo_etf.summary(items))
        self.assertIn("21日 +4.9%", m21_bogo_etf.summary(items))
        self.assertIn("弱势 / 回撤中", m21_bogo_etf.summary(items))

    def test_etf_row_uses_itself_as_the_context(self):
        items = m21_bogo_etf.contexts(
            {"代码": "QTUM", "主题": "量子计算ETF"}, self.snapshot
        )

        self.assertEqual("标的本身", items[0]["relation"])

    def test_html_links_to_etf_detail(self):
        items = m21_bogo_etf.contexts(
            {"代码": "RGTI", "主题": "量子计算"}, self.snapshot
        )

        rendered = m15_bogo_cn._etf_html(items)
        self.assertIn('href="etf.html#QTUM"', rendered)
        self.assertIn("63日 +0.9%", rendered)

    def test_copper_rule_wins_before_precious_metals_proxy(self):
        mapped = m21_bogo_etf.map_etfs(
            "SCCO", "铜·贵金属·矿业·电气", {"COPX", "GDX"}
        )

        self.assertEqual(("COPX", "直接主题"), mapped[0])

        slash_mapped = m21_bogo_etf.map_etfs(
            "HBM", "铜/贵金属矿", {"COPX", "GDX"}
        )
        self.assertEqual(("COPX", "直接主题"), slash_mapped[0])

    def test_copper_clad_laminate_is_not_treated_as_copper_mining(self):
        mapped = m21_bogo_etf.map_etfs(
            "600183", "覆铜板(CCL)全球龙头", {"COPX"}
        )

        self.assertEqual([], mapped)

    def test_lithium_niobate_is_not_treated_as_lithium_battery(self):
        mapped = m21_bogo_etf.map_etfs(
            "300620", "光纤器件+铌酸锂调制器", {"LIT"}
        )

        self.assertEqual([], mapped)


if __name__ == "__main__":
    unittest.main()
