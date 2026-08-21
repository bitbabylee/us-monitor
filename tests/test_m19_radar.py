import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from us_monitor import m19_radar


def frame(daily_returns):
    idx = pd.bdate_range("2026-01-02", periods=len(daily_returns))
    close = 100 * pd.Series(1 + np.asarray(daily_returns), index=idx).cumprod()
    return pd.DataFrame({
        "Close": close,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Volume": 1_000_000,
    }, index=idx)


class EtfRadarTests(unittest.TestCase):
    def setUp(self):
        n = 210
        self.metas = {
            "SPY": {"name": "标普500", "group": "宽基"},
            "XBI": {"name": "生物科技", "group": "医疗"},
            "BURST": {"name": "单日脉冲", "group": "测试"},
            "DOWN": {"name": "下降", "group": "测试"},
            "MISSING": {"name": "缺数据", "group": "测试"},
        }
        self.frames = {
            "SPY": frame([0.001] * n),
            "XBI": frame([0.0025] * n),
            "BURST": frame([0.0] * (n - 1) + [0.08]),
            "DOWN": frame([-0.001] * n),
        }

    def test_complete_universe_keeps_missing_and_xbi(self):
        result = m19_radar.analyze_frames(
            self.frames, self.metas, aum={"XBI": 9_625_333_760}
        )
        by_ticker = {r["tk"]: r for r in result["rows"]}
        self.assertEqual(result["total"], 5)
        self.assertIn("XBI", by_ticker)
        self.assertTrue(by_ticker["MISSING"]["missing"])
        self.assertEqual(by_ticker["MISSING"]["tier"], "数据缺失")
        self.assertEqual(by_ticker["XBI"]["aum"], 9_625_333_760)
        self.assertEqual(by_ticker["XBI"]["volume"], 1_000_000)
        self.assertEqual(by_ticker["XBI"]["avg_volume21"], 1_000_000)
        self.assertGreater(by_ticker["XBI"]["avg_dollar_volume21"], 1_000_000)
        self.assertEqual(by_ticker["XBI"]["volume_ratio"], 1.0)
        self.assertEqual(by_ticker["XBI"]["liquidity"], "通过")

    def test_persistent_gain_is_ranked_and_not_hidden_by_top_n(self):
        result = m19_radar.analyze_frames(
            self.frames, self.metas, aum={"XBI": 9_625_333_760}
        )
        by_ticker = {r["tk"]: r for r in result["rows"]}
        self.assertIsNotNone(by_ticker["XBI"]["rank"])
        self.assertLess(by_ticker["XBI"]["rank"], by_ticker["DOWN"]["rank"])
        self.assertGreater(by_ticker["XBI"]["r21"], by_ticker["SPY"]["r21"])
        self.assertGreater(by_ticker["XBI"]["consistency"], by_ticker["BURST"]["consistency"])
        self.assertEqual(by_ticker["XBI"]["trend"], "多头")

    def test_page_has_filters_clickable_rows_and_direct_hash_data(self):
        result = m19_radar.analyze_frames(
            self.frames, self.metas, aum={"XBI": 9_625_333_760}
        )
        with TemporaryDirectory() as tmp, patch("us_monitor.m6_dashboard.OUT_DIR", Path(tmp)):
            out = m19_radar.build_page(result)
            page = Path(out).read_text(encoding="utf-8")
            symbols = (Path(tmp) / m19_radar.TV_SYMBOLS_FILENAME).read_text(encoding="utf-8")
            snapshot = json.loads((Path(tmp) / m19_radar.ETF_TRENDS_FILENAME).read_text(encoding="utf-8"))
        self.assertIn("全量 ETF 涨幅榜", page)
        self.assertIn('id="q"', page)
        self.assertIn('data-ticker="XBI"', page)
        self.assertIn("location.hash", page)
        self.assertIn("主题不参与评分", page)
        self.assertIn("下载 TV 导入 List", page)
        self.assertIn("复制 市场:TICKER", page)
        self.assertIn('<a href="prescreen.html">信号预筛</a>', page)
        self.assertIn("规模(AUM)", page)
        self.assertIn("21日均成交额", page)
        self.assertIn('id="liquidity"', page)
        self.assertIn('<option value="eligible" selected>符合准入（默认）</option>', page)
        self.assertIn("liquidity.value==='eligible'", page)
        self.assertIn("页面生成", page)
        self.assertIn('http-equiv="Cache-Control"', page)
        self.assertIn('value="aum"', page)
        self.assertIn('value="dollarVolume"', page)
        self.assertIn('data-aum="9625333760.0"', page)
        self.assertIn('data-volume="1000000.0"', page)
        self.assertIn('data-dollar-volume="', page)
        self.assertIn('data-liquidity="通过"', page)
        self.assertIn("盘前/盘后", page)
        self.assertIn("一行一个", page)
        self.assertNotIn(",", symbols.strip())
        self.assertGreaterEqual(len(symbols.strip().splitlines()), 1)
        self.assertEqual(1, snapshot["schemaVersion"])
        self.assertEqual(result["date"], snapshot["dataDate"])
        self.assertEqual(result["total"], len(snapshot["rows"]))
        self.assertIn("position", snapshot["rows"][0])

    def test_tv_import_list_uses_allowed_tiers_and_rank_order(self):
        aum = {tk: 1_000_000_000 for tk in self.metas}
        result = m19_radar.analyze_frames(self.frames, self.metas, aum=aum)
        text, selected = m19_radar.tv_import_list(result, limit=3)
        self.assertLessEqual(len(selected), 3)
        self.assertTrue(all(r["tier"] in m19_radar.TV_LIST_TIERS for r in selected))
        self.assertTrue(all(r["liquidity"] in m19_radar.TV_LIST_LIQUIDITY for r in selected))
        self.assertIn("###", text)
        self.assertEqual([r["rank"] for r in selected], sorted(r["rank"] for r in selected))
        symbols = m19_radar.tv_symbol_list(selected)
        self.assertNotIn("###", symbols)
        self.assertNotIn(",", symbols)
        self.assertEqual(len(symbols.splitlines()), len(selected))

    def test_extended_quote_uses_previous_close_for_premarket(self):
        result = {"rows": [{"tk": "XBI"}]}
        idx = pd.DatetimeIndex(["2026-08-19 04:00", "2026-08-19 08:25"], tz=m19_radar.NY)
        extended = pd.DataFrame({"Close": [101.0, 102.0], "Volume": [100, 200]}, index=idx)
        daily = pd.DataFrame(
            {"Close": [99.0, 100.0]},
            index=pd.to_datetime(["2026-08-17", "2026-08-18"]),
        )
        m19_radar.add_extended_quotes(result, {"XBI": daily}, extended)
        row = result["rows"][0]
        self.assertEqual(row["ext_session"], "盘前")
        self.assertEqual(row["ext_price"], 102.0)
        self.assertAlmostEqual(row["ext_change"], 2.0)
        self.assertEqual(row["ext_volume"], 300.0)
        self.assertEqual(row["ext_time"], "2026-08-19 08:25 ET")

    def test_extended_quote_uses_same_day_regular_close_for_postmarket(self):
        result = {"rows": [{"tk": "XBI"}]}
        idx = pd.DatetimeIndex(
            ["2026-08-19 15:55", "2026-08-19 16:05", "2026-08-19 18:00"],
            tz=m19_radar.NY,
        )
        extended = pd.DataFrame(
            {"Close": [110.0, 111.0, 112.0], "Volume": [500, 100, 200]}, index=idx
        )
        daily = pd.DataFrame(
            {"Close": [100.0]}, index=pd.to_datetime(["2026-08-18"])
        )
        m19_radar.add_extended_quotes(result, {"XBI": daily}, extended)
        row = result["rows"][0]
        self.assertEqual(row["ext_session"], "盘后")
        self.assertEqual(row["ext_base"], 110.0)
        self.assertAlmostEqual(row["ext_change"], (112 / 110 - 1) * 100)
        self.assertEqual(row["ext_volume"], 300.0)

    def test_liquidity_gate_excludes_aum_below_300m(self):
        status, reason = m19_radar.liquidity_status(299_999_999, 10_000_000)
        self.assertEqual(status, "排除")
        self.assertIn("$3亿", reason)
        self.assertEqual(m19_radar.liquidity_status(300_000_000, 1_999_999)[0], "排除")
        self.assertEqual(m19_radar.liquidity_status(300_000_000, 3_000_000)[0], "谨慎")
        self.assertEqual(m19_radar.liquidity_status(300_000_000, 5_000_000)[0], "通过")
        self.assertEqual(m19_radar.liquidity_status(None, 5_000_000)[0], "数据缺失")

    def test_tv_list_backfills_past_excluded_etf(self):
        rows = [
            {"tk": "HERO", "tier": "领涨", "rank": 1, "liquidity": "排除"},
            {"tk": "SPY", "tier": "领涨", "rank": 2, "liquidity": "通过"},
            {"tk": "XBI", "tier": "强势", "rank": 3, "liquidity": "谨慎"},
        ]
        _, selected = m19_radar.tv_import_list({"rows": rows}, limit=2)
        self.assertEqual([r["tk"] for r in selected], ["SPY", "XBI"])

    def test_aum_daily_cache_avoids_repeat_network_fetch(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / "etf_meta.json"
            cache.write_text(json.dumps({
                "fetched": datetime.now(m19_radar.NY).date().isoformat(),
                "aum": {"XBI": 9_625_333_760},
            }), encoding="utf-8")
            with patch.object(m19_radar, "META_CACHE", cache), \
                    patch.object(m19_radar, "_fetch_aum") as fetch:
                values = m19_radar._load_aum(["XBI"])
        fetch.assert_not_called()
        self.assertEqual(values["XBI"], 9_625_333_760)


if __name__ == "__main__":
    unittest.main()
