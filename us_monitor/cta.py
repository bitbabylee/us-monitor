# -*- coding: utf-8 -*-
"""
CTA 仓位估算 —— 填补 Brendon 信号#3 的数据缺口。

业界四种做法, 本模块实现其中两种免费可自动化的:
  ① 付费研报(GS/DB/Nomura/UBS 周频)     —— 拿不到, 但他们也是"模型估算"不是真仓位
  ② 趋势模型复制 (本模块主方法)          —— CTA 绝大多数是系统化趋势跟踪, 仓位是
     价格对多周期均线的机械函数, 可复制。GS/DB 的模型本质也是这个。
  ③ 管理期货ETF 代理 (本模块辅助)        —— DBMF/KMLM/CTA 等, 每日净值可得,
     反映趋势策略的"表现", 与市场方向结合可反推方向暴露
  ④ CFTC COT 持仓 (周频, 滞后3天)        —— Managed Money 净头寸, 真实但滞后

诚实标注原则(学自原版看板): 估算就标"模型估算", 绝不冒充真实仓位读数;
拿不到可靠数据时标"未验证", 不沿用旧值或猜测。
"""
import numpy as np
import pandas as pd

from . import config as C


def _trend_signal(close: pd.Series) -> float:
    """趋势跟踪仓位复制: 多周期均线信号 × 波动率倒数缩放, 输出 -100~+100"""
    sigs = []
    for n in C.CTA_LOOKBACKS:
        if len(close) < n + 1:
            continue
        ma = close.rolling(n).mean().iloc[-1]
        # 用"偏离均线的幅度/波动率"做连续信号, 再压到 [-1,1]
        vol = close.pct_change().rolling(n).std().iloc[-1] * np.sqrt(n)
        if not vol or np.isnan(vol):
            continue
        z = (close.iloc[-1] / ma - 1) / vol
        sigs.append(np.tanh(z))
    return float(np.mean(sigs) * 100) if sigs else np.nan


def estimate(daily: pd.DataFrame) -> dict:
    """返回 CTA 仓位估算 + ETF 代理交叉验证"""
    from .data import col
    try:
        spx = col(daily, "Close", C.CAM_INDEX)
    except (KeyError, IndexError):
        return {"ok": False, "note": "未验证: 缺少指数数据"}

    pos = _trend_signal(spx)
    if np.isnan(pos):
        return {"ok": False, "note": "未验证: 趋势信号计算失败"}

    # 各周期分解（看是短周期先翻多还是长周期已转向）
    legs = []
    for n in C.CTA_LOOKBACKS:
        if len(spx) < n + 1:
            continue
        ma = spx.rolling(n).mean().iloc[-1]
        legs.append((n, spx.iloc[-1] > ma, (spx.iloc[-1] / ma - 1) * 100))

    # ETF 代理: 管理期货ETF 近5日表现 vs 大盘, 交叉验证方向
    proxy = []
    for tk in C.CTA_PROXY_ETFS:
        try:
            e = col(daily, "Close", tk)
            if len(e) > 6:
                proxy.append((tk, (e.iloc[-1] / e.iloc[-6] - 1) * 100))
        except (KeyError, IndexError):
            continue
    spx_5d = (spx.iloc[-1] / spx.iloc[-6] - 1) * 100 if len(spx) > 6 else np.nan
    proxy_avg = np.mean([v for _, v in proxy]) if proxy else np.nan
    # 趋势基金与大盘同向 → 大概率净多; 反向 → 大概率净空或已减仓
    if not np.isnan(proxy_avg) and not np.isnan(spx_5d) and abs(spx_5d) > 0.3:
        agree = (proxy_avg > 0) == (spx_5d > 0)
        cross = f"{'同向, 支持净多' if agree else '反向, 提示已减仓/翻空'}"
    else:
        cross = "信号不足"

    state = ("重仓做多" if pos >= 60 else "净多" if pos >= 20 else
             "中性/观望" if pos > -20 else "净空" if pos > -60 else "重仓做空")
    return {"ok": True, "pos": pos, "state": state, "legs": legs,
            "proxy": proxy, "proxy_avg": proxy_avg, "spx_5d": spx_5d, "cross": cross,
            "note": "模型估算(趋势跟踪复制), 非真实仓位读数"}


def render_console(r: dict):
    if not r.get("ok"):
        print(f"❓ #3   CTA 仓位          {r['note']}")
        return
    print(f"📐 #3   CTA 仓位估算        {r['pos']:+.0f}/100 ({r['state']})   "
          f"—— {r['note']}")
    print(f"{'':7}└─ 趋势分解: " + " | ".join(
        f"{n}日{'多' if up else '空'}({dev:+.1f}%)" for n, up, dev in r["legs"]))
    if r["proxy"]:
        print(f"{'':7}└─ ETF交叉验证: " + ", ".join(f"{t} {v:+.1f}%" for t, v in r["proxy"])
              + f" vs 大盘 {r['spx_5d']:+.1f}% → {r['cross']}")
