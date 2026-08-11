# -*- coding: utf-8 -*-
"""
波哥信号复刻 · 全局配置
所有标的池和阈值都在这里改，业务模块不用动。
"""

BENCHMARK = "SPY"          # 超额 Alpha 的基准

# ── 数据源 ──────────────────────────────────────────
DATA_SOURCE = "ib"         # "ib" = IB优先(TWS没开自动降级yfinance) / "yf" = 只用yfinance
IB_PORTS = [7496, 7497, 4001, 4002]   # TWS实盘/模拟, Gateway实盘/模拟, 依次探测
IB_CLIENT_ID = 27          # 别和你其他 IB 脚本的 clientId 撞车
IB_PACING_SLEEP = 0.35     # 每个历史请求间隔秒数（IB pacing 限速保护）

# ── 模块1：大盘量化诊断 ─────────────────────────────
MACRO_TICKERS = {
    "标普500": "^GSPC",
    "VIX恐慌": "^VIX",
    "半导体": "SOXX",
    "动量股": "MTUM",
    "七巨头": "MAGS",
}
RSI_HOT = 65               # RSI 高于此 → 偏热/背离预警
VIX_ALERT = 17             # VIX 高于此 → 去杠杆/避险升温
# 因子轮动改用 比值 vs 自身20日均线 判趋势（原版固定阈值1.25因比值≈4.5恒真, 已弃用）

# ── 模块2：板块 ETF 微观异动 ─────────────────────────
SECTORS = {
    "XLY":  "可选消费 (Discretionary)",
    "XLRE": "房地产 (Real Estate)",
    "XLC":  "通讯服务 (Communication)",
    "XLI":  "工业板块 (Industrials)",
    "XLE":  "能源板块 (Energy)",
    "XLU":  "公用事业/AI电网 (Utilities)",
    "XLK":  "科技板块 (Technology)",
    "XLF":  "金融板块 (Financials)",
    "XLP":  "必选消费 (Staples)",
    "XLV":  "医疗健康 (Health Care)",
    "XLB":  "基础材料 (Materials)",
    "ITA":  "国防军工 (Defense)",
    "SOXX": "半导体主题 (Semis)",
    "GDX":  "黄金矿业 (Gold Miners)",
}
SECTOR_DUMP_ALPHA = -1.0   # 放量砸盘：超额Alpha 低于此
SECTOR_DUMP_VOL = 1.35     # 且成交量倍数高于此
SECTOR_HOT_ALPHA = 1.0     # 🔥 前一日显著跑赢大盘

# ── 模块3：自定义主题股票池 ──────────────────────────
THEMES = {
    "🛡️ 网络安全/AI软件":   ["PLTR", "CRWD", "NET", "S", "ZS", "SNOW"],
    "☁️ 云计算":            ["CRWV", "NBIS", "DDOG", "MDB", "ESTC"],
    "🔥 AI算力/核心芯片":    ["NVDA", "AMD", "AVGO", "INTC", "MU", "TSM"],
    "科技七巨头 (Magnificent 7)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "🏭 传统工业重机/复苏":  ["CAT", "DE", "ETN", "PH", "URI"],
    "⚡ AI电网/核能基础设施": ["VRT", "GEV", "CEG", "VST", "BE", "OKLO", "SMR"],
    "🚀 军工/无人机":        ["KTOS", "AVAV", "LMT", "RTX", "LHX"],
    "🏦 降息受益/数字金融":   ["COIN", "HOOD", "SOFI", "XYZ"],
    "🪙 黄金/贵金属矿业":     ["GDX", "NEM", "GOLD", "AEM", "WPM", "AGI"],
    "💊 减肥药/GLP-1龙头":   ["NVO", "LLY", "VKTX"],
}
THEME_HOT_ALPHA = 2.0      # 组合平均超额高于此 → 强势领涨
THEME_WEAK_ALPHA = -2.0    # 低于此 → 弱势领跌

# ── 模块4/5：专属观察池（自行增删，SQ 已退市换 XYZ）──
WATCHLIST = [
    "BE", "NBIS", "RKLB", "LITE", "AAOI", "MSFT", "LLY", "INTC", "AMAT",
    "SMH", "GEV", "SNDK", "QQQ", "CAT", "NET", "CRWD", "ANET", "CRDO",
    "HOOD", "AMD", "MU", "AXTI", "PLTR", "CIBR", "SNOW", "SPCX", "GDX",
]

def all_daily_tickers():
    """全部日线标的（run_all / m6 / live 共用, 别再各自维护清单）"""
    return (list(MACRO_TICKERS.values()) + [BENCHMARK] + list(SECTORS) + WATCHLIST
            + [t for m in THEMES.values() for t in m] + GAO_EXTRA + CTA_PROXY_ETFS)


# 个股 → 板块ETF / 主题 的映射（cross-check 用；没写的自动归 XLK）
TICKER_SECTOR = {
    "BE": "XLU", "GEV": "XLU", "CAT": "XLI", "RKLB": "ITA",
    "LLY": "XLV", "HOOD": "XLF",
    "SMH": "SOXX", "AMAT": "SOXX", "INTC": "SOXX", "AMD": "SOXX",
    "MU": "SOXX", "CRDO": "SOXX", "AAOI": "SOXX", "LITE": "SOXX",
    "AXTI": "SOXX", "SNDK": "SOXX", "ANET": "XLK", "MSFT": "XLK", "SPCX": "ITA",
    "GDX": "GDX",   # 黄金矿业自成板块, cross-check 时用自身超额确认
    "NET": "XLK", "CRWD": "XLK", "SNOW": "XLK", "PLTR": "XLK",
    "CIBR": "XLK", "NBIS": "XLK", "QQQ": "XLK",
}

# ── 日线形态买点阈值 ────────────────────────────────
PP_LOOKBACK = 10           # Pocket Pivot：回看 N 日的最大阴线量
BREAKOUT_VOLX = 1.2        # 箱体突破的放量确认倍数
EMA_TOUCH_TOL = 0.012      # 10EMA 回调买点：最低价触及 10EMA 的容差 (1.2%)
OVERSOLD_RSI = 32          # 超跌反弹：RSI 低于此后收阳

# ── 模块7：高老师双指数阶段模型 ──────────────────────
GAO_EXTRA = ["HYG", "LQD", "^TNX", "JPY=X"]   # 宏观确认层额外标的（QQQ/SMH 已在观察池）
# 日元套息风控（2026-08 美日联手干预后新增; CLSA 8/5 报告列为头号风险开关）
JPY_SUPPORT = 155.04       # USD/JPY 跌破此位 → 套息平仓螺旋风险, 全球去杠杆
JPY_WATCH = 157.0          # 逼近此位 → 预警观察带
GAO_LOW_LOOKBACK = 30      # "本轮低点/不创新低/失效位"的回看窗口(日)
GAO_REVERSAL_WIN = 5       # 在近N日内找"放量反转日"
GAO_REVERSAL_VOLX = 1.2    # 放量反转日的量倍确认
GAO_BREAKOUT_VOLX = 1.0    # 突破20日线"伴随放量"= 量不低于20日均量（对齐原版口径）
GAO_ATR_PCTL_PASS = 80     # QQQ ATR14 一年分位 < 80 → 恐慌定价消退
GAO_TNX_PASS = 4.5         # 10Y 美债 ≤ 4.5% → 利率压制解除
GAO_HYG_TOL = -0.002       # HYG/LQD 5日变化 > -0.2% → 信用利差稳

# ── 财报风险窗口 ────────────────────────────────────
EARNINGS_PRE_DAYS = 7      # 财报前N日: 日线买点信号降级(禁追)
EARNINGS_POST_DAYS = 2     # 财报后N日: 价格发现观察期, 旧形态失效
EARNINGS_STALE_DAYS = 75   # 距上次财报超过N日且查不到下次日期 → 数据缺失预警

from pathlib import Path as _P
# 财报日期三层数据源: 手工覆盖 > 自维护事件日历xlsx > yfinance（AMD 2026-08-04 yahoo缺漏的教训）
EARNINGS_XLSX = _P(__file__).resolve().parent.parent / "美股_宏观x财报_事件日历_v3.xlsx"
EARNINGS_OVERRIDE = {
    "AMD": ["2026-08-04"],
    "ANET": ["2026-08-04"],   # 已核实: Q2财报8/4盘后, beat+上调指引; 用户xlsx的08/19是过期信息
    "CAT": ["2026-08-04"],    # 已核实: Q2财报8/4盘前(BMO), 单季营收$20B创纪录; yahoo缺漏
    "SNDK": ["2026-08-05"],   # 已核实(官方公告); yahoo事后撤行导致丢失
    "LLY": ["2026-08-05"],    # 已核实: 8/5盘前 EPS$8.38大超+上调指引; yahoo事后撤行
    # 2026-08-07 第二轮 WebSearch 核实(官方公告/IR为准):
    "AAOI": ["2026-08-06"],   # 已核实: Q2 8/6盘后(营收$191.9M); yahoo 缺该行
    "NET":  ["2026-08-06"],   # 已核实: Q2 8/6盘后(营收$696.1M)
    "NBIS": ["2026-08-12"],   # 已核实: Q2 8/12【盘前】(非盘后)
    "AMAT": ["2026-08-13"],   # 已核实: FQ3 8/13盘后(官方新闻稿)
    "CRDO": ["2026-09-09"],   # 已核实: FQ1'27 9/9盘后; 原 08-13/09-02 均为错误推测
}
# 已人工核实过财报日期的标的（官方公告/IR WebSearch 过）; 不在此名单的财报日期
# 一律标 "?" 提示二次核实 —— yahoo/xlsx 都出过错(AMD缺漏/BE过期/SNDK事后撤行)
EARNINGS_VERIFIED = {"AMD", "ANET", "CAT", "SNDK", "LLY", "AAOI", "NET",
                     "NBIS", "AMAT", "CRDO", "RKLB", "LITE", "BE"}

# 剔除清单: 任何源里确认错误的日期在这里删掉（override 只能加不能减）
# 2026-08-05 逐一 WebSearch 核实过:
EARNINGS_REMOVE = {
    "BE":   ["2026-08-06"],   # 实际7/28盘后已发(营收+166%上调指引); xlsx行过期
    "ANET": ["2026-08-19"],   # 实际8/4盘后已发; xlsx行过期
    "SNDK": ["2026-08-06"],   # 官方公告: 8/5盘后(8/13是Investor Day不是财报)
    "LITE": ["2026-08-05"],   # 官方公告: 8/11盘后
    "RKLB": ["2026-08-07"],   # 官方公告: 8/10盘后
    # 2026-08-07 第二轮核实剔除:
    "CRDO": ["2026-08-13", "2026-09-02"],  # 均错; 实际 9/9盘后(历史节奏是3/6/9/12月初,8月中不可能)
}

# ── 模块14：信号日志 + 历史回放 ──────────────────────
JRN_HORIZONS = [1, 5, 10]   # 回填/统计的前瞻天数
JRN_REPLAY_DAYS = 250       # 历史回放窗口(交易日)
JRN_MIN_SAMPLE = 20         # 少于此样本量 → 标「样本不足」, 结论不可信

# ── 模块13：波哥七维信号聚合 ────────────────────────
BOGO_IMG_SCALE = 1.6        # PDF 单页图导出倍率(1.0≈72dpi; 1.6≈115dpi, 体积/清晰度折中)
BOGO_DIRS = [                       # 找 `MMDD us 1630 bo sig.pdf` 的目录(按序探测)
    "/Users/clair/My Drive (0xamberlbb01@gmail.com)/波哥信号归档",
    "/Users/clair/My Drive/波哥信号归档",
]

# ── 模块12：AI 资本周期看门狗（capexcycle.com, 季度频率）──
CAPEX_OCF_ALERT = 100      # Capex/OCF > 此% → 靠外部融资扩张
RPO_GAP_ALERT = 0          # (Capex增速−RPO增速) > 此pp → 需求见顶预警（转正即警）
T1_COVER_ALERT = 1.0       # T1覆盖 < 此倍 → 合同利润填不满建设
T1_COVER_CRIT = 0.35       # 低于此倍 → 严重不足, 升级报警

# ── 模块11：筛选器（复刻 TradingView 那套流水线）──
SCR_VOL_WIN = 20           # RVOL 的均量窗口
SCR_RVOL_MIN = 1.5         # RVOL 扫描门槛
SCR_ADR_SHORT = 10         # 波动压缩: 短期 ADR 窗口
SCR_ADR_LONG = 60          # 波动压缩: 长期 ADR 窗口（对照基准）
SCR_COMPRESS_RATIO = 0.90  # 短ADR/长ADR ≤ 此值 → 压缩（0.90 ≈ 池内最紧的 10%）
SCR_NEAR_HIGH = -3.0       # 距20日高 ≥ 此% → 高位压缩（最强形态: 横盘不跌=惜售）
SCR_ADR_MIN = 1.5          # 长期 ADR 低于此% 的死水票不看（压缩也没意义）
SCR_GAP_MIN = 2.0          # Gappers 门槛(延长时段涨跌%)

# ── CTA 仓位估算（Brendon 信号#3, 免费数据自动化）──
CTA_LOOKBACKS = [20, 50, 100, 200]      # 趋势跟踪复制的多周期
CTA_PROXY_ETFS = ["DBMF", "KMLM", "CTA"]  # 管理期货ETF, 交叉验证方向

# ── 模块10：CAMSLIM 派发日体系（欧奈尔/IBD）────────
CAM_INDEX = "^GSPC"
CAM_WINDOW = 25            # 派发日计数的滚动窗口(交易日)
CAM_HIGH_WIN = 60          # "创新高"的参照窗口 & 回撤基准高点。必须 > CAM_WINDOW:
                           # 否则25日内的次级高点会被误判为新高而错误清零派发压力
CAM_DIST_PCT = 0.2         # 派发日: 收跌≥此% 且放量
CAM_ACC_PCT = 0.2          # 吸筹日: 收涨≥此% 且放量（对齐原版口径, 非IBD的0.7%强吸筹）
CAM_STALL_PCT = 0.2        # 滞涨日: 收涨但<此% + 放量 + 收在下半区
CAM_RALLY_PCT = 1.0        # 软作废: 现价较派发日收盘涨超此% 即消除。
                           # IBD标准是5%, 但对6个原版时点做阈值扫描后, 1% 拟合最好——
                           # 原版的派发计数会随指数小幅反弹而下降(卖压被买盘吸收即释放)
CAM_INVALIDATION = "hard_remove"   # hard_remove=创窗口新高即全清 / soft=只用5%规则
CAM_CAUTION = 4            # 派发日≥此 → 警戒
CAM_CORRECTION = 6         # 派发日≥此 → 卖压高位/回调
CAM_HIGH_PRESSURE = 6      # 定义"卖压高位"的门槛(用于识别缓解)
# 仓位公式: 由原版4个时点(7/29 dist5→20% / 7/30,7/31 dist4→40% / 8/5 dist0→100%)反推
# 得 exposure = min(100, (CAM_EXPO_BASE - dist) * CAM_EXPO_STEP)，原版看板上印的
# "0-2→90-100% | 3→75% | 4→60% | 5+→20-40%" 只是说明文字, 与其实际输出不符。
CAM_EXPO_BASE = 6
CAM_EXPO_STEP = 20
CAM_EXPO_FLOOR = 20        # 下限: 派发≥6 时仍给 20%（原版 7/27,7/28 dist6→20% 实证）
CAM_EXPO_CAP = 100
# 可选叠加: 卖压从高位被动衰减时不一次给满仓, 每站稳一天加一档（原版无此逻辑,
# 属于我们加的风控保守层, 默认关闭以保持与原版一致）
CAM_USE_RAMP = True        # 用户明确要求启用（原版无此层, 属更保守的风控叠加）
CAM_CORRECTION_LINE = 5    # 派发≥5 → CONFIRMED CORRECTION（原版实证）
CAM_RAMP_STEPS = [20, 40, 60, 80]   # 第1/2/3/4天的仓位上限(%)
CAM_RAMP_LOOKBACK = 10     # 回看N日判断"是否刚从卖压高位下来"

# ── 模块8：信号预警卡（复刻 hello231101 signal-system, 数值层每日重算）──
FIB_PEAK_WIN = 60          # 斐波那契锚: 峰=近N日最高收盘
FIB_LOW_WIN = 30           # 低=近N日最低收盘（与失效位同窗口）
SMH_STREAK_N = 3           # SMH连续跑赢QQQ N日 → Brendon信号#2正式成立
# 事件类锚位（来自博主帖子, 是"史料"不重算; 但带锚定日期+失效条件, 触发即归档）
ALERT_EVENT_LEVELS = [
    {"id": "qqq_680", "ticker": "QQQ", "level": 680.0,
     "anchor": "2026-07-31", "desc": "博主7/31确认位#1(真有买盘的第一道确认)",
     "invalid": "SPY创60日新高(大盘定性反转, 事件锚过期)",
     "source": "github.com/bitbabylee/hello231101/blob/main/signal-system/inbox/zsxq/2026-07-31_55522445144522114.md"},
]

# ── 日内 VWAP/ORB 择时阈值（2026-08-05 对齐朋友最新版）──
ORB_MINUTES = 30           # 开盘区间分钟数
DEV_STOPLOSS = -1.5        # 偏离 VWAP 低于此% → 规避/止损（原-1.2, 对齐朋友版）
DEV_OVERBOUGHT = 2.5       # 偏离高于此% → 强主升浪 或 锁定利润（看结构）
DEV_TRIM = 0.7             # 偏离高于此% 且 15m 结构破位 → 锁定利润
DEV_GOLD = 1.0             # 偏离 0~此% 且放量 → 黄金买点（放量站回VWAP）
VOL15_GOLD = 1.2           # "放量"确认倍数（黄金买点/强动能突破共用）
VOL15_WEAK = 0.5           # 15m 量能低于此倍 → 缩量突破预警
NEAR_HIGH_TOL = 0.01       # 距离前高 1% 以内 → 谨防双顶
RUNUP_WARN = 2.5           # 从日内低点已拉升超过此% → 追高警告（原3.0, 对齐朋友版）

# ── 盘前/盘后雷达 & 跳空闸门 ─────────────────────────
EXT_MOVE_ALERT = 2.0       # 延长时段涨跌超过此% → 高亮预警
GAP_VOID = 2.0             # 低开超过此% → 当日买点信号降级(前提失效)
GAP_CHASE = 3.0            # 高开超过此% → 买点信号附"勿追, 等回踩VWAP"警示

# ── 模块15：A股重演监控（反转/反弹五条件判定, 2026-08-11 策略会重演论）──
# 数据: yfinance .SS/.SZ 日线（云端 CI 亦可用）; 判定框架见 manual
CN_BENCH = "000300.SS"          # 沪深300 = 超额基准
CN_INDEX = "000001.SS"          # 上证综指
CN_NAMES = {
    "300476.SZ": "胜宏", "002463.SZ": "沪电", "600183.SS": "生益",
    "688519.SS": "南亚", "300308.SZ": "旭创", "300502.SZ": "新易盛",
    "300394.SZ": "天孚", "688498.SS": "源杰", "002837.SZ": "英维克",
    "301018.SZ": "申菱", "300499.SZ": "高澜", "300990.SZ": "同飞",
    "603986.SS": "兆易", "301308.SZ": "江波龙", "688525.SS": "佰维",
    "001309.SZ": "德明利", "688627.SS": "精智达", "688072.SS": "拓荆",
    "601208.SS": "东材", "605589.SS": "圣泉", "601138.SS": "富联",
}
CN_LEADERS = ["300476.SZ", "600183.SS", "601138.SS"]   # 检验①②③的"龙头"
CN_BATONS = {                    # 四棒 + 新逻辑探测器(第五棒)
    "PCB":  ["300476.SZ", "002463.SZ", "600183.SS", "688519.SS"],
    "光":   ["300308.SZ", "300502.SZ", "300394.SZ", "688498.SS"],
    "液冷": ["002837.SZ", "301018.SZ", "300499.SZ", "300990.SZ"],
    "存储": ["603986.SS", "301308.SZ", "688525.SS", "001309.SZ"],
    "探测": ["688627.SS", "688072.SS", "601208.SS", "605589.SS"],
}
CN_HIGH_WIN = 60                # ①前高参照窗口(交易日)
CN_HIGH_SKIP = 5                # ①前高不含最近N日(防止把本波当参照)
CN_VOLRATIO_N = 10              # ②量能结构回看(≈2周)
CN_VOLRATIO_OK = 1.2            # ②涨日均量/跌日均量 ≥此 → 健康
CN_RS_N = 5                     # ③⑤四棒/扩散的超额窗口(日)
CN_SH_BOX = (3946.0, 3980.0)    # ④上证滞涨区(0.382反弹+布林上轨+套牢平台)
CN_SH_GAP = (3983.0, 3996.0)    # ④7/13缺口, 收盘>上沿=回补(反转确认)
CN_ANCHORS = ["TSM", "SMH", "QQQ"]   # ⑤海外锚价格代理(台积电ADR+费半比值)

# ── 跟随策略复评节点(策略会"炒作到11月"时间框架, 到期强制重估非顺延) ──
CN_REVIEWS = [
    ("2026-09-09", "苹果发布会·iPhone18逻辑验真(果链腿去留)"),
    ("2026-10-30", "Q3财报兑现+中期选举前·跟随整体降仓评估"),
]
