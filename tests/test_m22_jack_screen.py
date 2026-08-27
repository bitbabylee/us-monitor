import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from us_monitor.m22_jack_screen import (
    A_SHARE_BENCHMARK,
    A_SHARE_BENCHMARK_SYMBOL,
    CANDIDATES,
    Candidate,
    candidate_payload,
    enrich_frame,
    render_page,
    state_events,
)


def rising_frame(periods=340):
    index = pd.bdate_range("2025-01-02", periods=periods)
    close = pd.Series(np.linspace(40, 120, periods), index=index)
    return pd.DataFrame(
        {
            "Open": close * 0.997,
            "High": close * 1.012,
            "Low": close * 0.988,
            "Close": close,
            "Volume": 2_000_000,
        },
        index=index,
    )


class JackScreenStateTests(unittest.TestCase):
    def test_requested_etf_universe_is_present_with_tradingview_symbols(self):
        symbols = {candidate.symbol for candidate in CANDIDATES}
        requested = {
            "AMEX:GDXJ", "AMEX:SIL", "AMEX:ARKG", "AMEX:COPX", "AMEX:URA",
            "AMEX:PICK", "AMEX:XBI", "AMEX:IEO", "AMEX:NLR", "AMEX:BLOK",
        }
        self.assertTrue(requested.issubset(symbols))
        self.assertEqual(len(symbols), len(CANDIDATES))

    def test_requested_a_share_universe_uses_china_market_benchmark(self):
        requested = {
            "SZSE:000973", "SZSE:002812", "SZSE:300568", "SZSE:300214",
            "SSE:688353", "SZSE:301292", "SSE:600110", "SSE:688388",
            "SSE:603876", "SSE:603906", "SZSE:002709",
        }
        candidates = {candidate.symbol: candidate for candidate in CANDIDATES}
        self.assertTrue(requested.issubset(candidates))
        for symbol in requested:
            self.assertEqual(A_SHARE_BENCHMARK, candidates[symbol].benchmark)
            self.assertEqual(A_SHARE_BENCHMARK_SYMBOL, candidates[symbol].benchmark_symbol)
            self.assertEqual("¥", candidates[symbol].currency_symbol)

    def test_rising_series_reaches_mature_trend_without_lookahead(self):
        frame = rising_frame()
        benchmark = pd.Series(np.linspace(100, 130, len(frame)), index=frame.index)
        enriched = enrich_frame(frame, benchmark)
        self.assertEqual("mature", enriched.iloc[-1]["State"])
        self.assertGreaterEqual(int(enriched.iloc[-1]["Score"]), 85)
        self.assertGreater(int(enriched.iloc[-1]["Stage2Age"]), 20)

    def test_forward_returns_remain_empty_until_future_bars_exist(self):
        index = pd.bdate_range("2026-01-02", periods=100)
        states = ["range"] * 20 + ["base"] * 20 + ["expansion"] * 20 + ["trend"] * 20 + ["mature"] * 20
        frame = pd.DataFrame(
            {
                "Close": np.arange(100, 200, dtype=float),
                "State": states,
                "Score": [40] * 20 + [60] * 20 + [75] * 20 + [90] * 40,
            },
            index=index,
        )
        events = state_events(frame)
        latest = events[-1]
        self.assertEqual("mature", latest["state"])
        self.assertIsNotNone(latest["forward"]["10"])
        self.assertIsNone(latest["forward"]["20"])
        self.assertIsNone(latest["forward"]["63"])

    def test_generated_page_contains_per_symbol_chart_and_event_table(self):
        frame = rising_frame()
        benchmark = pd.Series(np.linspace(100, 130, len(frame)), index=frame.index)
        candidate = Candidate("TEST", "NASDAQ:TEST", "Test Company", "优先研究")
        payload = candidate_payload(candidate, frame, benchmark)
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "jack-screen.html"
            render_page([payload], output)
            page = output.read_text(encoding="utf-8")
        self.assertIn("NASDAQ:TEST", page)
        self.assertNotIn('"ticker":"TEST"', page)
        self.assertIn("EMA10", page)
        self.assertIn("蓝色 T 是本页可复算的趋势状态切换", page)
        self.assertIn('id="eventRows"', page)
        self.assertIn("TradingView", page)
        self.assertIn('"benchmark_symbol":"AMEX:SPY"', page)
        self.assertIn("相对基准", page)


if __name__ == "__main__":
    unittest.main()
