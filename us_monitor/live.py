# -*- coding: utf-8 -*-
"""
实时维护模式：盘中循环刷新仪表盘。

    python3 -m us_monitor.live                # 等开盘→盘中每5分钟刷新→收盘后收官一次→退出
    python3 -m us_monitor.live --interval 180 # 改刷新间隔(秒)
    python3 -m us_monitor.live --once         # 立即生成一次就退出（不管开不开盘）

设计：
- 日线数据每天只拉一次（已完结K线, 不被盘中污染）; 每个周期只重拉观察池分钟数据
- latest.html 原子替换 + <meta refresh> 自动刷新, 浏览器开着就是实时看板
- 文件锁防止 LaunchAgent 重复拉起两个实例
- 盘前最多等 100 分钟(覆盖 EDT/EST 两种开盘时刻), 收盘后自动收官退出
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as C
from .data import fetch_daily, fetch_intraday, NY
from .m6_dashboard import build, OUT_DIR

LOCK = OUT_DIR / ".live.lock"


def market_open_now() -> bool:
    ny = dt.datetime.now(NY)
    if ny.weekday() >= 5:
        return False
    t = (ny.hour, ny.minute)
    return (9, 30) <= t < (16, 0)


def acquire_lock() -> bool:
    OUT_DIR.mkdir(exist_ok=True)
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip())
            os.kill(pid, 0)                     # 进程还活着 → 已有实例
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass                                # 死锁文件, 覆盖
    LOCK.write_text(str(os.getpid()))
    return True


def fetch_all_daily():
    return fetch_daily(C.all_daily_tickers())


def main():
    interval = 300
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    once = "--once" in sys.argv

    if not acquire_lock():
        print("已有 live 实例在运行, 退出")
        return
    try:
        if once:
            build(with_intraday=True)
            return

        # 盘前: 等开盘（最多100分钟, 覆盖夏令/冬令时差）
        waited = 0
        while not market_open_now() and waited < 100 * 60:
            ny = dt.datetime.now(NY)
            if ny.weekday() >= 5 or (ny.hour, ny.minute) >= (16, 0):
                print("今日已收盘/休市, 生成收官版后退出")
                build(with_intraday=True)
                return
            print(f"等待开盘 (纽约时间 {ny:%H:%M}) ...")
            time.sleep(60)
            waited += 60

        print(f"开盘, 进入实时模式: 每 {interval}s 刷新一次")
        daily = fetch_all_daily()               # 日线一天拉一次
        cycle = 0
        while market_open_now():
            cycle += 1
            try:
                build(with_intraday=True, daily=daily, refresh_sec=interval)
            except Exception as e:              # 网络抖动不退出, 下轮重试
                print(f"⚠️ 第{cycle}轮失败: {e}")
            time.sleep(interval)

        print("收盘, 用完整日线重算收官版 ...")
        build(with_intraday=True)               # 收盘后重拉日线(含今日完结K)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
