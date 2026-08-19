import unittest
from datetime import date

from us_monitor.m20_pt2_signals import (
    SignalEvent,
    build_states,
    parse_page_text,
    resolve_signal_date,
)


class PivotTrendSignalParsingTests(unittest.TestCase):
    def test_parses_only_signal_summary_line(self):
        text = """⚠ 风险 NASDAQ:IREN IREN LIMITED
信号归纳：3H 08-19▼ · 1D 08-18▼ · 3D 08-18▼
图中另有 2H 01-01▲ 字样
"""
        rows = parse_page_text(text, date(2026, 8, 19))
        self.assertEqual(
            [(row.symbol, row.timeframe, row.signal_date.isoformat(), row.side) for row in rows],
            [
                ("NASDAQ:IREN", "3H", "2026-08-19", "short"),
                ("NASDAQ:IREN", "1D", "2026-08-18", "short"),
                ("NASDAQ:IREN", "3D", "2026-08-18", "short"),
            ],
        )

    def test_december_signal_in_january_uses_prior_year(self):
        self.assertEqual(resolve_signal_date("12-28", date(2026, 1, 5)), date(2025, 12, 28))

    def test_symbol_can_follow_chinese_label_without_space(self):
        text = "⚠ 风险NASDAQ:IREN IREN LIMITED\n信号归纳：3D 08-18▼\n"
        rows = parse_page_text(text, date(2026, 8, 19))
        self.assertEqual([(row.symbol, row.side) for row in rows], [("NASDAQ:IREN", "short")])


class PivotTrendStateTests(unittest.TestCase):
    @staticmethod
    def event(tf, day, side):
        return SignalEvent(
            symbol="NASDAQ:TEST",
            timeframe=tf,
            signal_date=date.fromisoformat(day),
            side=side,
            first_seen=date(2026, 8, 19),
            last_seen=date(2026, 8, 19),
        )

    def test_marks_multitimeframe_alignment_and_reversal(self):
        states = build_states(
            [
                self.event("3D", "2026-08-10", "long"),
                self.event("3D", "2026-08-18", "short"),
                self.event("1D", "2026-08-18", "short"),
            ]
        )
        self.assertEqual(states[0]["structure"], "多周期同向")
        self.assertEqual(states[0]["dominant"], "short")
        self.assertIn("3D翻空", states[0]["change"])

    def test_marks_mixed_timeframes_without_directional_claim(self):
        states = build_states(
            [
                self.event("3D", "2026-08-18", "long"),
                self.event("1D", "2026-08-19", "short"),
            ]
        )
        self.assertEqual(states[0]["structure"], "多空并存")
        self.assertEqual(states[0]["dominant"], "mixed")


if __name__ == "__main__":
    unittest.main()
