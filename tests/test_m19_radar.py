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
        self.assertEqual(by_ticker["XBI"]["volume_ratio"], 1.0)

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
        self.assertIn("全量 ETF 涨幅榜", page)
        self.assertIn('id="q"', page)
        self.assertIn('data-ticker="XBI"', page)
        self.assertIn("location.hash", page)
        self.assertIn("主题不参与评分", page)
        self.assertIn("下载 TV 导入 List", page)
        self.assertIn("复制 市场:TICKER", page)
        self.assertIn("规模(AUM)", page)
        self.assertIn("成交量", page)
        self.assertIn('value="aum"', page)
        self.assertIn('value="volume"', page)
        self.assertIn('data-aum="9625333760.0"', page)
        self.assertIn('data-volume="1000000.0"', page)

    def test_tv_import_list_uses_allowed_tiers_and_rank_order(self):
        result = m19_radar.analyze_frames(self.frames, self.metas)
        text, selected = m19_radar.tv_import_list(result, limit=3)
        self.assertLessEqual(len(selected), 3)
        self.assertTrue(all(r["tier"] in m19_radar.TV_LIST_TIERS for r in selected))
        self.assertIn("###", text)
        self.assertEqual([r["rank"] for r in selected], sorted(r["rank"] for r in selected))
        symbols = m19_radar.tv_symbol_list(selected)
        self.assertNotIn("###", symbols)
        self.assertEqual(len(symbols.split(",")), len(selected))

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
