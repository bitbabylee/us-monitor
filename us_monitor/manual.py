# -*- coding: utf-8 -*-
"""
使用手册生成器 —— 按【师承来源】分章, 不把不同人的方法论混成一套。
每章标明: 出处 / 核心逻辑 / 验证状态。阈值从 config 实时读取。
    python3 -m us_monitor.manual
输出 dashboard/manual.html
"""
from pathlib import Path

from . import config as C
from .m6_dashboard import CSS, OUT_DIR

EXTRA_CSS = """
.wrap { max-width: 920px; margin: 0 auto; }
h2 { font-size:17px; color:var(--ink); margin:30px 0 4px; padding-bottom:6px;
     border-bottom:2px solid var(--pos); }
h3 { font-size:15px; margin:18px 0 6px; }
p, li { color:var(--ink2); line-height:1.75; }
li { margin-bottom:5px; }
.src { display:flex; gap:14px; flex-wrap:wrap; font-size:12.5px; color:var(--muted);
       margin:4px 0 12px; }
.src b { color:var(--ink2); }
.sig { background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--pos);
       border-radius:8px; padding:12px 16px; margin:12px 0; }
.sig.warn { border-left-color:var(--warn); }
.sig.bad { border-left-color:var(--critical); }
.sig .name { font-size:15px; font-weight:650; color:var(--ink); }
.sig .do { background:color-mix(in srgb, var(--pos) 10%, transparent);
           border-radius:6px; padding:8px 12px; margin-top:8px; color:var(--ink); }
.tip { background:color-mix(in srgb, var(--pos) 7%, transparent); border-radius:8px;
       padding:12px 16px; margin:14px 0; }
.warnbox { background:color-mix(in srgb, var(--warn) 13%, transparent); border-radius:8px;
       padding:12px 16px; margin:14px 0; color:var(--ink); }
table { margin:10px 0; }
"""


def _verify_badges():
    """从 m14 回放结果给各形态生成验证状态徽章（有数据就用数据说话）"""
    try:
        from . import m14_journal
        r = m14_journal.load_replay()
        out = {}
        for row in r.get("by_signal", []):
            k = f"T+{C.JRN_HORIZONS[-1]}"
            d = row.get(k)
            if not d:
                continue
            edge, n = d.get("edge", 0), row.get("n", 0)
            if not row.get("enough"):
                out[row["signal"]] = f'<span class="badge b-muted">回放样本不足(n={n})</span>'
            elif edge > 0.5:
                out[row["signal"]] = (f'<span class="badge b-good">250日回放: {k} 超额 '
                                      f'{edge:+.2f}pp (n={n})</span>')
            elif edge < -0.2:
                out[row["signal"]] = (f'<span class="badge b-critical">250日回放: {k} 超额 '
                                      f'{edge:+.2f}pp (n={n}) — 未跑赢随机买入</span>')
            else:
                out[row["signal"]] = (f'<span class="badge b-warn">250日回放: {k} 超额 '
                                      f'{edge:+.2f}pp (n={n}) — 边际优势微弱</span>')
        return out
    except Exception:
        return {}


UNTESTED = '<span class="badge b-warn">未回测</span>'


def build() -> Path:
    vb = _verify_badges()

    def v(sig_name):
        return vb.get(sig_name, UNTESTED)

    h = f"""<div class="wrap">
<p><a href="index.html" style="color:var(--pos)">← 回到看板</a> ·
<a href="history.html" style="color:var(--pos)">历史归档</a></p>
<h1>📖 使用手册 <small>按来源分章 —— 这不是一套系统，是几套独立方法的并置</small></h1>

<div class="warnbox"><b>先读这段，这是整本手册最重要的话。</b><br>
看板上的方法来自<b>不同的人</b>：朋友的日频监控、高老师(即Brendon, 同一人)的双指数模型与宏观五信号、
博主的 0.618 模板、欧奈尔的派发日体系、波哥的七维回测。它们是<b>互相独立</b>的思路，
被并排放在一个页面上，<b>不代表它们互相认可或构成一个整体</b>。<br><br>
验证状态用徽章标注：<span class="badge b-warn">未回测</span> = 只是忠实复刻，无已知胜率；
带「250日回放」的 = 已在观察池近一年数据上重放过（口径：信号日收盘买入的裸收益 vs 随机买入，
不含止损/仓位/滑点）。<b>回放不是回测策略收益，只是信号质量的粗测。</b><br><br>
<b>各家结论冲突是常态</b>（比如 CAMSLIM 说满仓、高老师说不买）——冲突不是谁错了，
是它们看的东西不同。怎么裁决见最后一章。</div>

<h2>📄 一页纸 · 每天只需要做这几件事</h2>
<div class="src"><span><b>更新:</b> 2026-08-13（含 m15-m19 新模块与三层版面）</span>
<span><b>用法:</b> 这一章是速查；下面各章是每个方法的出处与细节</span></div>

<h3>① 日报三层怎么读（首页从上到下）</h3>
<p><b>① 决策区</b>——只有这一层需要行动：【结论】给仓位上限，【候选】是三关全过的票，
【否决】说明谁被拦下、为什么，【风险】+【财报7日】是一票否决项。<br>
<b>② 证据区</b>——回答"凭什么"：大盘/日性质、全市场主题雷达（池外资金去向）、板块、
个股信号分类、走势中频（资格三档）、期权异动。<b>看不懂可以跳过，不影响执行。</b><br>
<b>③ 参考区</b>——独立体系与背景：A股重演五条件、资金面周频、复评节点、波哥七维对照。
<b>这一层不产生任何买卖动作。</b></p>

<h3>② 一只票要过六道关才轮到下单</h3>
<div class="sig"><div class="name">资格链（任何一关不过 = 不做）</div>
<p><b>1 走势中频(m18)</b> 🟢合格 / 🟡待定 / 🔴淘汰 —— 只给资格，<b>上升趋势 ≠ 可以买</b><br>
<b>2 日线形态(m4)</b> 口袋支点 / 箱体突破 / 金叉 —— 给"买点存在"<br>
<b>3 位置检查</b> 距 20 日枢轴 ≤5%（欧奈尔口径；<b>不能用距均线判追高</b>）<br>
<b>4 板块共振</b> cross-check：板块或主题 α &gt; 0<br>
<b>5 财报窗口</b> 前 {C.EARNINGS_PRE_DAYS} 日 / 后 {C.EARNINGS_POST_DAYS} 日一律作废<br>
<b>6 日内时机(m5)</b> VWAP/ORB 八档给 🟢 才扣扳机</p>
<div class="do">仓位上限由 CAMSLIM 派发日定，不由信心定；止损 = 信号日低点。</div></div>

<h3>③ 新增模块速查（这一版新加的）</h3>
<p><b>m15 A股重演</b>：反转/反弹五条件 + 四棒轮动（含 RRG 象限与加速度）。
判定 ≥4 才算"反转倾向"，否则一切上涨按反弹操作。<br>
<b>m16 资金面周频</b>：私募仓位/指增超额（人工周更，&gt;12 天标⚠️）+ 风格温度计（自动）。
只定环境，不给信号。<br>
<b>m17 期权异动</b>：不猜买卖方向，只用 vol/OI≥1.5 找疑似新开仓，次日用 OI 增量确认。仅佐证。<br>
<b>m18 走势中频</b>：Weinstein 阶段 × 摆动结构 × 波段回撤 → 资格三档。<br>
<b>m19 全市场主题雷达</b>：65 个主题 ETF 按 z 分（当日涨跌÷自身60日波动）排序 +
改善象限=下一棒候选。<b>只做发现，个股信号仍只在观察池内产生。</b></p>

<h3>④ 三条铁律</h3>
<p><b>1. 各家冲突是常态</b>——CAMSLIM 说满仓、高老师说 P0 不买，同时成立，裁决见末章。<br>
<b>2. 全部方法未回测</b>（除标了「250日回放」的），10EMA 回调已被数据否定为负超额。<br>
<b>3. 波哥七维是外部独立体系</b>——日报里只做对照，不参与候选/否决判定；
公开的 <a href="bogo.html">波哥信号页</a> 与本报无任何交互。</p>

<h2>第一章 · 朋友的微观资金监控</h2>
<div class="src"><span><b>来源:</b> 朋友的 Colab 脚本与每日截图（逐版复刻+对齐）</span>
<span><b>覆盖:</b> 大盘简报 / 板块榜 / 主题榜 / 日线形态 / 日内VWAP / CAMSLIM看板</span></div>
<p>核心思想两条：<b>① 所有涨跌先减掉 SPY 变成「超额」</b>（剔除大盘噪音看相对强弱）；
<b>② 用成交量确认资金参与度</b>（涨跌×量倍才能区分主力行为和随波逐流）。</p>

<h3>日线买点形态（原生 3 个 + 本系统补 2 个）</h3>
<div class="sig"><div class="name">💡 Pocket Pivot 口袋支点 {v("【Pocket Pivot 口袋支点】")}</div>
<p>收阳且成交量超过近 {C.PP_LOOKBACK} 日所有阴线的最大量 = 有人在盘整区偷偷扫货（散户没那个量）。
形态学出处是 Gil Morales/欧奈尔系，按朋友的截图版式复刻。</p>
<div class="do">位置早、成本低。小仓试，止损放近期低点。</div></div>

<div class="sig bad"><div class="name">🟢 10 EMA 强动能回调 {v("【10 EMA 强动能回调】")}</div>
<p>多头排列中缩量回踩 10 日线企稳（Qullamaggie 式）。
<b>注意：250 日回放里这是唯一超额为负的形态（样本 1090，最可靠的一个负结论）——
早前版本手册说它"性价比最高"，被数据否定，特此更正。</b>可能原因：观察池强势股多、
随便买的基准本来就高；或阈值太松导致信号泛滥（n=1090 远多于其他形态）。</p>
<div class="do">在收紧阈值或单独回测前，把它当「位置参考」而不是「买点信号」。</div></div>

<div class="sig"><div class="name">🚀 超跌反弹起爆点 {v("【超跌反弹起爆点】")}</div>
<p>RSI 跌破 {C.OVERSOLD_RSI} 后收阳。抢反弹不是买趋势。</p>
<div class="do">只做短线，止损更严，别当底部抄底。</div></div>

<div class="sig warn"><div class="name">📦 20日箱体突破 {v("【20日箱体突破】")} ·
🌊 EMA金叉 {v("【EMA10/21 金叉启动】")}</div>
<p><b>这两个不是朋友原版的</b>——是复刻时为凑齐截图里"5大形态"补的（截图只看得到 3 个）。
箱体突破回放显示 T+5 为负、T+10 转正（突破后先洗盘再走）；金叉数字漂亮但样本太小，别当真。</p></div>

<h3>日内 VWAP / ORB 八档信号 {UNTESTED}</h3>
<p>VWAP=当日真金白银的平均成本（「团购成本价」）。铁律：<b>VWAP 下方不做多</b>。
八档按危险度排序：止损({C.DEV_STOPLOSS}%) → 锁润(15m结构破位) → 强主升浪(&gt;{C.DEV_OVERBOUGHT}%
持有勿追) → 弱突破预警(&lt;{C.VOL15_WEAK}x) → 双顶警告 → 放量突破ORB(≥{C.VOL15_GOLD}x)
→ 放量站回VWAP → 观望。跳空闸门（低开{C.GAP_VOID}%作废 / 高开{C.GAP_CHASE}%勿追）是本系统补的。
<b>日内信号无法用日线数据回放，完全未验证。</b></p>

<h3>CAMSLIM 派发日（欧奈尔/IBD 体系，朋友的实现）</h3>
<p>数「机构出货日」定总仓位：收跌≥{C.CAM_DIST_PCT}%且放量=派发日，{C.CAM_WINDOW}日窗口。
仓位=min({C.CAM_EXPO_CAP}, max({C.CAM_EXPO_FLOOR}, ({C.CAM_EXPO_BASE}−派发日)×{C.CAM_EXPO_STEP}))
——从朋友看板 6 个历史时点反推，价格指标 6/6 对齐。
<span class="badge b-good">已对原版 6 时点校验</span>（但欧奈尔体系本身在本池的有效性未测）。
爬坡层（卖压降档后逐日加仓 {"/".join(str(x)+"%" for x in C.CAM_RAMP_STEPS)}）是按你的经验加的，
原版数据显示它没有这层。</p>

<h2>第二章 · 高老师的双指数阶段模型</h2>
<div class="src"><span><b>来源:</b> 高老师日报（逐题复刻，失效位/共识分逐项对齐）</span>
<span><b>覆盖:</b> P0→P1→C1 阶段判定</span> <span>{UNTESTED}</span></div>
<p>灵魂是 <b>SMH/QQQ 比值</b>：半导体是进攻先锋，<b>真反弹必须先锋带头</b>。
两道关卡（恐慌释放 4 题 / 资金共识 5 题），必选题一票否决——防止"看到几个好消息就上头"。
它天生保守：宁可错过，不可做错。注意它和 CAMSLIM 经常打架（口径不同：它看科技先锋，
CAMSLIM 看标普整体）。</p>

<h2>第三章 · 高老师(Brendon)的宏观五信号</h2>
<div class="src"><span><b>来源:</b> 高老师/Brendon docx（好友群转述, 与第二章双指数模型同一作者）+ 本系统自动化</span>
<span>{UNTESTED}</span></div>
<p>底部确认计分卡（≥3/5 确认见底）：①站上20日线 ②SMH连续{C.SMH_STREAK_N}日跑赢
③CTA转多（无真数据——本系统用趋势模型估算并明确标注，连高盛发的也是估算）
④ATR分位&lt;{C.GAO_ATR_PCTL_PASS}%（波动收敛。ATR 是绝对值不分方向：高=多空还在剧烈换手）
⑤10Y≤{C.GAO_TNX_PASS}% 且信用利差稳（HYG/LQD 5日不恶化）。
USD/JPY 套息开关（破 {C.JPY_SUPPORT} 告警）是 2026-08 美日联手干预汇市后本系统补的。</p>

<h2>第四章 · 博主的 0.618 模板与确认位</h2>
<div class="src"><span><b>来源:</b> zsxq 帖子（hello231101 归档）· 2015 创业板类比</span>
<span>{UNTESTED}</span></div>
<p>暴跌后的反弹通常到前高 0.618 回撤位滞涨、随后走第二腿——所以 0.618 是<b>卖点不是买点</b>。
锚位（峰/低）本系统改为每日重算，并补了原版没有的<b>失效条件</b>：站上 0.786 位或前高，模板作废。
事件确认位（如 680）是史料，触发一次即归档。<b>这是单一历史类比，不是统计规律。</b></p>

<h2>第五章 · 波哥的七维信号</h2>
<div class="src"><span><b>来源:</b> 波哥系统每日 PDF（只做解析聚合，不改动其结论）</span>
<span><b>验证:</b> 表内 CA%/Pnls%/胜率/Fit 是波哥自己的回测值，口径未独立复核</span></div>
<p>与本页其他方法完全独立的选股来源。🔗 = 该标的同时在本系统观察池——两套独立方法共同覆盖，
值得优先研究；但「都覆盖」≠「都看多」，要点开各自的信号方向看。原图（当日强信号）可在表内 🖼 查看。</p>

<h2>第六章 · TradingView 筛选流水线</h2>
<div class="src"><span><b>来源:</b> 别人分享的 6 个 screener（复刻其筛选条件）</span>
<span>{UNTESTED}</span></div>
<p>RVOL（相对量≥{C.SCR_RVOL_MIN} 找资金异动）· Compression（{C.SCR_ADR_SHORT}日/{C.SCR_ADR_LONG}日
ADR ≤{C.SCR_COMPRESS_RATIO} 找蓄势——贴近前高的压缩才是惜售）· Gappers（跳空≥{C.SCR_GAP_MIN}%）。
命令行工具（m11），不进看板。</p>

<h2>第七章 · 本系统自己加的层</h2>
<div class="src"><span><b>来源:</b> 复刻过程中为堵漏洞新增（不属于任何一家）</span></div>
<ul>
<li><b>财报否决</b> {UNTESTED}：财报前{C.EARNINGS_PRE_DAYS}日/后{C.EARNINGS_POST_DAYS}日一票否决。
依据是 AMD(-8%)/ANET(+14%) 同晚一反一正的实例——财报日的形态≈掷硬币。三层数据源+人工核实清单。</li>
<li><b>板块共振 Cross-Check</b> {UNTESTED}：个股信号需板块或主题超额为正背书。</li>
<li><b>AI 资本周期看门狗</b>：capexcycle.com 季度数据（SEC/XBRL），只判 AI 主线是否成立，不择时。</li>
<li><b>信号回放（m14）</b>：本页各徽章的来源。回放≠回测，只测裸收益差。</li>
</ul>

<h2>最后 · 各家冲突时怎么读</h2>
<div class="tip">
<p><b>先分清各家在回答什么问题</b>：CAMSLIM 答「大盘机构在不在卖」（标普口径），
双指数层答「科技进攻主线修好没有」（QQQ/SMH 口径），宏观层答「宏观环境松没松绑」——两层同出高老师(Brendon)一人之手, 是体系内分层而非独立互证，
博主答「这波反弹走到什么位置了」。<b>它们同时分歧是常态</b>——2026-08 初就同时出现过：
CAMSLIM 满仓（SPX 创新高）+ 高老师不买（半导体没确认）。</p>
<p><b>实用裁决顺序</b>（这是本系统的观点，不代表任何一家）：<br>
① 有人喊「危险」永远优先于有人喊「机会」（止损/否决类一票优先）<br>
② 仓位上限听最保守的那家<br>
③ 个股方向要求至少两套独立方法同向（如波哥 strong + 本系统形态）<br>
④ 记住谁都没被充分验证——任何单一信号都不构成行动理由</p></div>

<p class="footer">阈值全在 us_monitor/config.py，改完重跑 manual 自动同步 ·
仅供研究，不构成投资建议</p>
</div>"""

    page = (f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>使用手册 · 按来源分章</title><style>{CSS}{EXTRA_CSS}</style>{h}')
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "manual.html"
    out.write_text(page, encoding="utf-8")
    print(f"✅ 使用手册已生成: {out}")
    return out


if __name__ == "__main__":
    build()
