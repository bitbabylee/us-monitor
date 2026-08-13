# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-08-13
- Primary product surfaces: `docs/index.html`, `docs/bogo.html`, `docs/summary.html`, `docs/etf.html`
- Evidence reviewed: `README.md`, `us_monitor/m15_bogo_cn.py`, `us_monitor/m19_radar.py`, generated `docs/bogo.html`, `SPEC_三层信号引擎_20260813.md`, production handoff and pit list.

## Brand
- Personality: restrained, quantitative, direct, research-oriented.
- Trust signals: visible formulas, data date, complete-universe counts, explicit inclusion/exclusion reasons, and research-only disclaimer.
- Avoid: opaque scores, hype language, decorative dashboards, hidden rows, and color-only meaning.

## Product goals
- Goals: make daily market evidence easy to scan; keep every configured ETF discoverable; explain why an ETF ranks high or low; connect ranking to a detail view without losing context.
- Non-goals: automated trade execution, guaranteed-return language, or treating candlestick triggers as proven selection alpha.
- Success signals: XBI and every other configured ETF are searchable; users can sort by raw return windows; clicking any ETF opens an explanatory detail view; data failures remain visible.

## Personas and jobs
- Primary personas: an active investor reviewing US-market signals after the close.
- User jobs: find which ETFs rose most, distinguish one-day spikes from persistent gains, inspect trend/extension risk, and hand a shortlist to the three-layer execution engine.
- Key contexts of use: desktop and mobile browser, often during a quick post-close review.

## Information architecture
- Primary navigation: Bogo signals, ETF return ranking, aggregate history.
- Core routes/screens: `bogo.html` for source signals; `etf.html` for complete ETF discovery; `summary.html` for historical aggregation.
- Content hierarchy: transparent scoring logic -> ranked priority set -> complete searchable table -> click-through detail.

## Design principles
- Returns first: ETF ranking is driven primarily by 5/21/63-day price appreciation, not company-quality narratives.
- Complete before curated: the priority list is a view over the full universe, never a replacement for it.
- Explain every state: the detail view states both supporting evidence and the main reason not to chase.
- Tradeoff: density is preferred over decorative space, while touch targets and mobile readability remain usable.

## Visual language
- Color: reuse the existing light/dark tokens; green for positive/leading, amber for caution/improving, muted gray for observation, red only for clear weakness or errors.
- Typography: system UI and PingFang SC, numeric columns use tabular numerals.
- Spacing/layout rhythm: compact 4/8/12/16px rhythm consistent with the existing Bogo tables.
- Shape/radius/elevation: subtle borders, 6-12px radii, no heavy shadows.
- Motion: minimal; native dialog open/close only, with reduced-motion support.
- Imagery/iconography: no new imagery; text labels must accompany symbols.

## Components
- Existing components to reuse: sticky pill navigation, compact tables, status tags, light/dark CSS variables.
- New/changed components: scoring explainer, filter bar, sortable complete-universe table, ETF detail dialog, missing-data row state, and downloadable/copyable TradingView Top-22 list.
- Variants and states: leading/strong/improving/watch; extended/near-pivot/pullback; loading/empty/error.
- Token/component ownership: page-local CSS until a shared component system exists.

## Accessibility
- Target standard: practical WCAG 2.1 AA.
- Keyboard/focus behavior: ETF ticker is a real button; dialog supports Escape and returns focus; filters have visible labels.
- Contrast/readability: status text accompanies color; numerical signs remain explicit.
- Screen-reader semantics: semantic table headers, labelled dialog, live visible-count text.
- Reduced motion and sensory considerations: no required animation or color-only state.

## Responsive behavior
- Supported breakpoints/devices: mobile browsers from 360px and desktop browsers.
- Layout adaptations: table scrolls horizontally; controls wrap; detail dialog becomes a near-full-width sheet on mobile.
- Touch/hover differences: rows may highlight on hover, but the ticker button remains the explicit touch target.

## Interaction states
- Loading: static build avoids client data loading.
- Empty: show “没有符合当前筛选的 ETF” while retaining reset controls.
- Error: configured ETFs with missing/stale data remain listed and explain the data gap.
- Success: filtered count and data date update visibly.
- Disabled: unavailable detail actions use explanatory text rather than silent disabled controls.
- Offline/slow network: the generated page and embedded data remain usable; only external TradingView links require network.

## Content voice
- Tone: concise Chinese research language, factual and non-promotional.
- Terminology: “涨幅评分”, “持续性”, “趋势”, “追高提示”, “优先研究名单”.
- Microcopy rules: distinguish “排名靠前” from “可以买”; always display the measurement window and data date.

## Implementation constraints
- Framework/styling system: generated static HTML, CSS, and vanilla JavaScript; no frontend framework or new dependency.
- Design-token constraints: reuse existing Bogo page variables and dark-mode behavior.
- Performance constraints: one self-contained page; no per-row network request; lazy external navigation only.
- Compatibility constraints: GitHub Pages, current Python build pipeline, and macOS/CI execution.
- Test/screenshot expectations: unit-test score calculations; build static page; verify XBI presence, configured-universe count, filters/dialog markup, and mobile/desktop render.

## Open questions
- [ ] Whether future “全部 ETF” should expand beyond the configured research universe to every US-listed ETF; owner: user; impact: data volume and page scope.
