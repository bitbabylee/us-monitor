# -*- coding: utf-8 -*-
"""
使用手册生成器：把所有信号/指令翻译成小白能看懂的话。
阈值从 config 实时读取, 改参数手册自动同步。
    python3 -m us_monitor.manual
输出 dashboard/使用手册.html
"""
from pathlib import Path

from . import config as C
from .m6_dashboard import CSS, OUT_DIR

EXTRA_CSS = """
.wrap { max-width: 900px; margin: 0 auto; }
h2 { font-size:17px; color:var(--ink); margin:26px 0 10px; padding-bottom:6px;
     border-bottom:2px solid var(--pos); }
h3 { font-size:15px; margin:18px 0 6px; }
p, li { color:var(--ink2); line-height:1.75; }
li { margin-bottom:5px; }
.sig { background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--pos);
       border-radius:8px; padding:12px 16px; margin:12px 0; }
.sig.warn { border-left-color:var(--warn); }
.sig.bad { border-left-color:var(--critical); }
.sig .name { font-size:15px; font-weight:650; color:var(--ink); }
.sig .one { color:var(--ink); margin:6px 0; }
.sig .do { background:color-mix(in srgb, var(--pos) 10%, transparent);
           border-radius:6px; padding:8px 12px; margin-top:8px; color:var(--ink); }
.sig.bad .do { background:color-mix(in srgb, var(--critical) 12%, transparent); }
.sig.warn .do { background:color-mix(in srgb, var(--warn) 14%, transparent); }
.tip { background:color-mix(in srgb, var(--pos) 7%, transparent); border-radius:8px;
       padding:12px 16px; margin:14px 0; }
.step { display:flex; gap:12px; margin:10px 0; align-items:flex-start; }
.step .n { flex:0 0 30px; height:30px; border-radius:50%; background:var(--pos); color:#fff;
           display:flex; align-items:center; justify-content:center; font-weight:700; }
table { margin:10px 0; }
"""


def build() -> Path:
    h = f"""<div class="wrap">
<p><a href="index.html" style="color:var(--pos)">← 回到看板</a> · <a href="history.html" style="color:var(--pos)">历史归档</a></p>
<h1>📖 波哥信号系统 · 使用手册 <small>每个信号是什么意思、看到了该干什么</small></h1>

<div class="tip"><b>先记住一件事：这套系统分三层，回答三个不同的问题。</b><br>
① <b>大盘层</b>问「现在能下多大注」 → ② <b>个股层</b>问「下注在哪只」 →
③ <b>日内层</b>问「现在这一刻能不能动手」。<br>
三层都过关才出手。任何一层亮红灯，后面的都不用看了。</div>

<h2>第一层 · 大盘：现在能下多大注</h2>

<h3>📊 派发日（Distribution Day）—— 最重要的一个数</h3>
<p><b>是什么：</b>指数当天<b>收跌超过 {C.CAM_DIST_PCT}% 且成交量比前一天大</b>，就记一个派发日。
跌得有量 = 大机构在出货，不是散户瞎砸。系统数最近 {C.CAM_WINDOW} 个交易日里有几天这样。</p>
<p><b>为什么重要：</b>大盘顶部不是一天砸出来的，是机构在高位连续派发堆出来的。
这个数就是在数「有多少机构在偷偷卖」。</p>

<div class="sig bad"><div class="name">派发日 停在 6-7-8 不下来</div>
<div class="one">机构<b>一直在卖</b>，市场是卖方主导。你买什么都容易被人家卖出去。</div>
<div class="do"><b>怎么做：</b>不是完全不能做，但要——只做<b>最强势</b>的那几只；
突破、追高都要谨慎；<b>止损带窄一点</b>（错了赶紧走）；总仓位压住。</div></div>

<div class="sig warn"><div class="name">从高位（6-8）突然降到 4</div>
<div class="one">在卖的机构少了，卖压真的小了。但这只是<b>第一天</b>。</div>
<div class="do"><b>怎么做：</b><b>别一次满仓</b>。第一天变 4 先给 20%，第二天还站在 4 才加到 40%，
一天加一档。给市场时间证明它是真的缓解了。</div></div>

<div class="sig"><div class="name">降到 0-2</div>
<div class="one">机构不卖了，市场是买方主导。</div>
<div class="do"><b>怎么做：</b>强势股突破的成功率明显提高，可以放手做，仓位可以给足。</div></div>

<h3>💰 建议仓位</h3>
<p>公式：<code>min({C.CAM_EXPO_CAP}, max({C.CAM_EXPO_FLOOR},
({C.CAM_EXPO_BASE} − 派发日) × {C.CAM_EXPO_STEP}))</code></p>
<p><b>这是仓位<u>上限</u>，不是叫你买满。</b>显示 40% 的意思是：这个市场环境下，
你的钱最多投 40%，剩下 60% 拿现金等更好的时候。
它<b>不告诉你买什么</b>（那是第二层的活），只告诉你<b>该下多大注</b>。</p>

<h3>📐 阶段状态（P0 → P1 → C1）</h3>
<p>用 QQQ（大盘）和 SMH（半导体＝进攻先锋）两个指数打分。
核心思想：<b>真正的反弹必须由先锋带头</b>——半导体不涨，科技股的反弹都是假的。</p>
<ul>
<li><b>P0 恐慌未释放</b>：还在跌，别接飞刀，空仓/防守</li>
<li><b>P1 恐慌已释放</b>：跌势止住了，但买家还没回来 → <b>不买，等</b></li>
<li><b>C1 资金共识</b>：买家确认回来了 → 可以按纪律分批试仓</li>
</ul>
<p><b>必选题一票否决</b>：有几道题是必答的（比如 SMH/QQQ 比值要站上 20 日均线），
不管其他几题多好看，必选题不过就升不了级。这是防止「看到几个好消息就上头」。</p>

<h3>🌍 宏观确认层（4 个自动 + 1 个估算）</h3>
<table><tr><th class="l">指标</th><th class="l">通过条件</th><th class="l">人话</th></tr>
<tr><td class="l">ATR14 一年分位</td><td class="l">&lt; {C.GAO_ATR_PCTL_PASS}%</td>
<td class="l">市场每天上蹿下跳的幅度回到正常了没有。还在高位＝恐慌没消化完</td></tr>
<tr><td class="l">10Y 美债收益率</td><td class="l">≤ {C.GAO_TNX_PASS}%</td>
<td class="l">利率是所有资产的定价锚。太高＝压着科技股估值抬不起头</td></tr>
<tr><td class="l">HYG/LQD 信用利差</td><td class="l">5 日变化 &gt; {C.GAO_HYG_TOL*100:+.1f}%</td>
<td class="l">垃圾债有没有被抛售。债市先崩＝要出系统性风险；债市稳＝股市只是自己在调整</td></tr>
<tr><td class="l">USD/JPY</td><td class="l">&gt; {C.JPY_WATCH:.0f}（破 {C.JPY_SUPPORT} 告警）</td>
<td class="l">全球有上万亿美元是「借日元买美股」。日元一涨，这些人被迫卖股还钱，会连锁踩踏</td></tr>
<tr><td class="l">CTA 仓位</td><td class="l">≥ +20 净多</td>
<td class="l">趋势跟踪基金是行情放大器：趋势翻多它们被迫追买，翻空被迫砸卖。
<b>注意这是模型估算，不是真实仓位</b>（连高盛发的也是估算）</td></tr></table>

<h2>第二层 · 个股：下注在哪只</h2>

<h3>五大日线买点形态</h3>

<div class="sig"><div class="name">💡 Pocket Pivot 口袋支点</div>
<div class="one">今天收阳线，而且<b>成交量超过了近 {C.PP_LOOKBACK} 天所有下跌日的最大量</b>。</div>
<p>正常盘整时，涨的时候量该缩、跌的时候量该放（散户在割肉）。
一旦上涨的量超过了近期最大的下跌量，说明<b>有人在偷偷扫货</b>——散户没那个量，只可能是机构。
叫「口袋」是因为它藏在口袋里，还没被大众发现。</p>
<div class="do"><b>怎么做：</b>机构刚开始建仓，位置早、成本低。可以小仓试，止损放近期低点。</div></div>

<div class="sig"><div class="name">📦 20 日箱体突破</div>
<div class="one">收盘创 20 日新高，且成交量放大 {C.BREAKOUT_VOLX} 倍以上确认。</div>
<p>和口袋支点的区别：口袋支点是「机构刚开始买」（还在箱体里），
箱体突破是「机构已经买到突破了」（所有人都看见了）。
好处是上方没有套牢盘，坏处是位置高、容易买在假突破。</p>
<div class="do"><b>怎么做：</b>放量才算数（缩量突破多半是骗人的）。止损放回箱体内。</div></div>

<div class="sig"><div class="name">🟢 10 EMA 强动能回调 —— 性价比最高</div>
<div class="one">上升趋势中，最低价踩到 10 日均线，<b>缩量</b>企稳后收回来。</div>
<p>10 日均线是强势股的「生命线」，主升浪里每次踩到都有人接。
<b>缩量最关键</b>：放量跌到均线＝有人出货，支撑要破；缩量跌到均线＝只是没人买，
获利盘歇口气，一有买盘就弹。</p>
<div class="do"><b>怎么做：</b>这是<b>最好的建仓位</b>——止损就放 10EMA 下方一点点，
错误成本被这条线量化了，上方是主升浪的空间。跌破就走，别摊平。</div></div>

<div class="sig"><div class="name">🌊 EMA10/21 金叉启动</div>
<div class="one">短均线（10日）向上穿过长均线（21日），趋势由跌转涨。</div>
<div class="do"><b>怎么做：</b>趋势刚转向，位置好但还需确认。适合小仓位埋伏，等放量再加。</div></div>

<div class="sig warn"><div class="name">🚀 超跌反弹起爆点</div>
<div class="one">RSI 跌破 {C.OVERSOLD_RSI}（超卖）之后，今天收阳企稳。</div>
<p>抛售衰竭了，容易有一波修复性反弹。但注意：<b>这是抢反弹不是买趋势</b>，
下跌趋势可能还没结束。</p>
<div class="do"><b>怎么做：</b>只做短线，快进快出，止损要更严格。别当成底部抄底。</div></div>

<h3>三个资金指标（判断上涨是不是真的有钱推）</h3>
<ul>
<li><b>量倍</b>＝当天成交量 ÷ 20 日平均量。回答「有没有人来」。1.0x 是平量，2x 以上是明显异动。
<b>无量的大涨随时可以无量跌回去。</b></li>
<li><b>CMF 资金流</b>（-1 ~ +1）：看收盘价在当天振幅的哪个位置，用成交量加权 20 天。
正数＝买方吸筹，负数＝卖方派发。<b>如果涨了但 CMF 是负的，说明拉高的过程一直有人在卖</b>——
这是冲高回落的高危信号。</li>
<li><b>MFI</b>（0-100）：带成交量的 RSI。>80 超买（追高危险），&lt;20 超卖（可能反弹）。</li>
</ul>

<h3>🔗 板块共振 Cross-Check（自动缩减标的）</h3>
<p>个股有买点还不够，还要问：<b>它所在的板块/主题今天是不是也在涨？</b>
系统要求「板块 ETF 超额为正 <b>或</b> 所属主题超额为正」才保留，否则降级为「仅观察」。</p>
<div class="tip"><b>为什么：</b>孤军奋战的信号不可信。机构建仓通常是<b>整个板块一起买</b>，
一只票涨而板块不动，多半是消息面或游资，持续性差。</div>

<h2>第三层 · 日内：现在这一刻能不能动手</h2>

<h3>先理解 VWAP —— 日内交易的圣经</h3>
<p><b>VWAP = 成交量加权平均价</b>，就是「今天所有真金白银换手的平均成本」。
从开盘累计计算，收盘归零，第二天重来。</p>
<ul>
<li><b>价格在 VWAP 上方</b>＝今天进场的人平均在赚钱，拿得住，主力愿意抬轿</li>
<li><b>跌破 VWAP</b>＝今天买入的人集体被套，随时可能踩踏 → <b>系统的铁律：VWAP 下方不做多</b></li>
</ul>
<p>打个比方：VWAP 就是今天这只股票的「团购成本价」。在成本价下方接货是捡便宜，
在上方 4% 追高就是替别人抬轿。</p>

<h3>八档日内信号（按危险程度排序，命中即停）</h3>

<div class="sig bad"><div class="name">🔴 规避 / 止损（破位走弱）</div>
<div class="one">跌破开盘 30 分钟的最低价，或低于 VWAP {C.DEV_STOPLOSS}%。</div>
<div class="do"><b>怎么做：</b>保命第一。有仓位就走，没仓位别碰。</div></div>

<div class="sig bad"><div class="name">🔴 锁定利润（高位 15m 结构破位）</div>
<div class="one">涨了不少（偏离 VWAP 超过 {C.DEV_TRIM}%），但<b>跌破了前一根 15 分钟 K 的低点或 15m 8EMA</b>。</div>
<p>15 分钟结构是持仓者的「离场哨」：涨的时候只要防线不破就拿着，防线一破就该分批兑现。</p>
<div class="do"><b>怎么做：</b>分批锁利润，不用一次清光，但要开始减。</div></div>

<div class="sig"><div class="name">🔥 强主升浪（切勿卖飞！）</div>
<div class="one">偏离 VWAP 超过 {C.DEV_OVERBOUGHT}%，<b>但 15 分钟结构完好没破</b>。</div>
<div class="do"><b>怎么做：</b>拿住别卖，把止损<b>上移</b>到 15m 8EMA，让利润奔跑。
但也<b>不要在这个位置追进</b>——已经离平均成本太远了。</div></div>

<div class="sig"><div class="name">🟢 强动能买点（放量突破 ORB）</div>
<div class="one"><b>ORB = 开盘区间突破</b>。突破开盘 {C.ORB_MINUTES} 分钟的最高价，
站稳 VWAP，且 15 分钟量能 ≥ {C.VOL15_GOLD} 倍。</div>
<p>开盘头半小时是隔夜消息和大单集中释放的时段，它的高低点是当天多空第一道分界线。
向上突破 + 放量 + 站稳 VWAP ＝ 早盘抛压消化完了，买方还在加力。</p>
<div class="do"><b>怎么做：</b>可以进场追强势。止损放开盘区间低点或 VWAP。</div></div>

<div class="sig"><div class="name">🟢 黄金买点（放量站回 VWAP）</div>
<div class="one">价格回踩后重新站上 VWAP（偏离 0~{C.DEV_GOLD}%），
且 15 分钟量能 ≥ {C.VOL15_GOLD} 倍。</div>
<p>和 ORB 突破的区别：ORB 是<b>追强势</b>（高位向上突破），黄金买点是<b>抄回踩</b>（跌到平均成本又站回来）。
<b>「放量」是灵魂</b>：缩量站回只说明没人卖；放量站回说明<b>有大资金在这个位置主动接货</b>。</p>
<div class="do"><b>怎么做：</b>这是低吸位，风险收益比比追高好。止损就放 VWAP 下方。</div></div>

<div class="sig warn"><div class="name">🟡 弱突破预警（缩量突破 ORB）</div>
<div class="one">突破了开盘高点，但量能不到 {C.VOL15_WEAK} 倍。</div>
<div class="do"><b>怎么做：</b>警惕诱多假突破。宁可等放量确认再进，也别赌。</div></div>

<div class="sig warn"><div class="name">🟡 警告：临近前高（谨防双顶）</div>
<div class="one">从日内低点已经拉升超过 {C.RUNUP_WARN}%，且逼近前期高点。</div>
<div class="do"><b>怎么做：</b>切勿在前高附近追高。要么等突破确认，要么等回踩。</div></div>

<div class="sig warn"><div class="name">🟡 跳空低开，买点降级</div>
<div class="one">今天开盘比昨收低了 {C.GAP_VOID}% 以上。</div>
<p>昨天那个买点信号的前提是「在昨收附近能上车」。低开 2% 以上说明隔夜出了事，前提被推翻了。</p>
<div class="do"><b>怎么做：</b>昨天的信号作废，等企稳后重新评估。
（反过来高开 {C.GAP_CHASE}% 以上，信号保留但标「勿追，等回踩 VWAP」）</div></div>

<h2>第四层 · 财报：什么绝对不能碰</h2>
<div class="sig bad"><div class="name">⚠️ 财报前 {C.EARNINGS_PRE_DAYS} 日内 / 📊 财报后 {C.EARNINGS_POST_DAYS} 日内</div>
<div class="one">再漂亮的形态，只要落在这个窗口，<b>系统一票否决</b>。</div>
<p><b>为什么：</b>财报是掷硬币。8/4 那晚 AMD（-8%）和 ANET（+14%）同一天出财报，
一反一正——技术形态在这种时候<b>完全无效</b>。财报后 2 天叫「价格发现期」，
市场在重新定价，财报前的形态已经作废。</p>
<div class="do"><b>怎么做：</b>不碰。想赌财报是另一回事，但那不叫交易系统，叫赌博。
持仓遇到财报，自己决定是减仓避险还是扛过去——但别用技术信号骗自己。</div></div>

<h2>把三层串起来：完整决策流程</h2>
<div class="step"><div class="n">1</div><div><b>看派发日和建议仓位</b> → 决定今天总共能投多少钱。
派发 6-8 就压到 20-40%，别想着满仓。</div></div>
<div class="step"><div class="n">2</div><div><b>看阶段状态和宏观层</b> → 还在 P1「不买等」就以观望为主，
宏观 4 项通过不到 2 项也要谨慎。</div></div>
<div class="step"><div class="n">3</div><div><b>看聚焦清单</b>（已经帮你过滤过了）→ 这些是日线有形态 + 板块资金确认 +
没有财报风险的标的。清单为空就是今天没得做。</div></div>
<div class="step"><div class="n">4</div><div><b>看日内信号决定时机</b> → 清单里的票，日内是 🟢 才动手，
⚪ 观望就等，🔴 就别碰。</div></div>
<div class="step"><div class="n">5</div><div><b>进场就设止损</b> → 每个信号都标了止损位（VWAP、开盘区间低点、10EMA）。
<b>止损不是可选项。</b></div></div>

<div class="tip"><b>最后提醒：这套系统是过滤器，不是印钞机。</b><br>
它的价值在于<b>帮你不做什么</b>——不在财报前赌博、不追没有板块支持的孤股、
不在机构派发期满仓、不在 VWAP 下方接飞刀。<br>
过滤完剩下的机会，才轮到你判断要不要做、做多大。<b>系统给概率，决定权在你。</b></div>

<p class="footer">阈值全部可在 us_monitor/config.py 调整，改完这份手册会自动同步 ·
仅供研究，不构成投资建议</p>
</div>"""

    page = (f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>波哥信号系统 · 使用手册</title><style>{CSS}{EXTRA_CSS}</style>{h}')
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "使用手册.html"
    out.write_text(page, encoding="utf-8")
    print(f"✅ 使用手册已生成: {out}")
    return out


if __name__ == "__main__":
    build()
