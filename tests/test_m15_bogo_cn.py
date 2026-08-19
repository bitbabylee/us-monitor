import unittest
from datetime import datetime, timezone

from us_monitor import m13_bogo, m15_bogo_cn


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


if __name__ == "__main__":
    unittest.main()
