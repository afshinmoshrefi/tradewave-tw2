# UI Capture Pipeline

Operating manual for TradeWave's automated UI screenshot pipeline. This document
assumes zero prior context. If you are an AI model or a new engineer picking this
up cold, read this document straight through before running anything.

If anything here disagrees with the actual code, the code wins. The two files that
matter most are `/home/flask/tools/ui_capture/capture.js` (extremely heavily
commented - read it, do not just skim it) and `/home/flask/web/app.py` around line
1695-1733 (the server-side auth-bypass route). This document is a map of that code,
not a replacement for reading it.

## 1. What This Is

A headless-Chrome (Puppeteer) harness that:

1. Renders the REAL TradeWave wave-viewer React app on the dev box - the exact same
   app real users see at `/app/` - authenticated as a fixed internal bot user.
2. Drives that app to a declared UI state (theme, market, symbol, pattern, chart
   options) via a JSON spec file.
3. Waits for REAL market/pattern data to actually finish rendering (not just "the
   page loaded" - it waits on explicit readiness flags the React app sets).
4. Waits for on-screen chart animations to visually settle.
5. Captures pixel-exact PNG screenshots at 2x or 4x device-pixel-ratio (i.e.
   Retina-quality or higher).
6. Writes each PNG plus a `meta.json` sidecar recording exactly what was captured,
   proving the capture is trustworthy (not a blank panel or stale cache).

This exists so that marketing pages, docs, and other content can embed real,
current, pixel-accurate screenshots of the product UI without a human manually
opening the app, clicking through to the right state, and taking a screenshot by
hand.

### Location on disk

```
/home/flask/tools/ui_capture/
  capture.js       - the entire harness (one file, heavily commented)
  capture.sh        - thin shell wrapper that runs capture.js with the right cwd
  package.json      - declares the puppeteer dependency
  node_modules/      - LOCAL puppeteer install (see "Why a local Puppeteer install" below)
  specs/            - JSON spec files, one per screenshot you want
  out/              - output directory (PNGs + meta.json), organized by whatever
                      prefix each spec's "out" field uses (e.g. out/demo/...)
```

Everything under this directory is owned `flask:flask` and is NOT deployed to
staging or prod - it is a dev-box-only tool. It talks to the dev box's own running
services (web, appserver, nginx) over localhost.

### How to run a capture

```bash
cd /home/flask/tools/ui_capture
./capture.sh specs/aapl_seasonal_dark.json
```

Must be run as the `flask` user, from inside `/home/flask/tools/ui_capture` (or via
the wrapper script, which `cd`s there for you). It exits 0 on success and 1 on any
failure, printing `[capture] FAIL: <reason>` to stderr before exiting. There is no
partial/silent success - every failure mode either produces a complete, sanity-
checked set of PNGs plus a meta.json, or it exits non-zero with nothing usable
written.

## 2. Why A Local Puppeteer Install

An earlier draft of this tool considered reusing the Puppeteer/Chrome already
installed at `/root/tw-uitools/node_modules` (used by an existing root-owned
screenshot script, `shot.js`). That does not work: `/root` is mode 700 (root-only
access, and that permission is correct - do not weaken it), and `capture.js` runs
as the `flask` user, which cannot traverse into `/root` at all.

The fix is a fully separate, local Puppeteer install inside
`/home/flask/tools/ui_capture/`, owned by `flask:flask`. If you ever see a Puppeteer
"could not find Chrome" or module-not-found error, the fix is:

```bash
cd /home/flask/tools/ui_capture
npm install
```

This downloads Puppeteer's own bundled Chrome (roughly 300MB) into
`node_modules/`. It only needs to happen once, or again if `node_modules/` gets
deleted.

## 3. Architecture, Layer By Layer

This is the critical section. Read it in order - each layer depends on the one
before it.

### Layer 1: Auth bypass via a dev-only internal route

Real users reach the wave-viewer at `/app/` only after logging in through WorkOS
(TradeWave's auth provider). A headless script cannot practically drive a real
OAuth login flow every time it wants a screenshot. Instead, `web/app.py` defines a
special route:

```
GET /internal/capture/app
```

(implemented in `web/app.py`, function `capture_app()`, currently around line
1695-1733 - line numbers drift as the file changes, search for `capture_app` if the
numbers are stale).

This route renders the exact same authenticated app shell HTML that a real logged-
in user gets at `/app/` (it calls the same internal `_render_app_shell(u)` function
the real route uses) - but for a fixed internal service-account user instead of
whoever is logged in via cookie/session.

**The bot account:**
- Email: `capture-bot@tradewave.local`
- `workos_user_id`: `capture-bot-dev` (a placeholder string, NOT a real WorkOS
  subject - this account can never sign in through the normal `/login` flow; it can
  only be looked up directly by this one internal route)
- Roles: `["user"]`
- Tier: `strategist` (the top paid tier, so the bot can see every feature the app
  gates by tier - AI columns, PE-cycle overlays, everything)
- The route looks the user up by email (`filter_by(email="capture-bot@tradewave.local")`).
  There is no seed script for this row in the codebase as of 2026-07-09 - it exists
  only as a database row. **Do not hardcode its UUID anywhere.** The harness always
  re-discovers the UUID at runtime from the HTML response (see Layer 2). If you need
  to know it for manual debugging, the UUID on this box at the time of writing was
  `99705e1e-17a4-4a34-a4c8-2bcd2e6ad5e6` - but treat that as a debugging convenience,
  never as a constant to code against, since a fresh box or a re-seeded row would
  have a different UUID.

**Two independent gates keep this from being an auth-bypass hole in staging/prod:**

1. **Env gate.** The route does `if config.tw2_env != "dev": abort(404)` as its
   first line, before any database query. On any environment other than dev, this
   route simply does not exist (404). This is the gate that actually matters - it
   fails closed regardless of network topology.
2. **Network gate.** Even on dev, this route is served by gunicorn bound to
   `127.0.0.1:5500` (the `tradewave-web` systemd unit), and nginx has no `location`
   block exposing `/internal/capture/app` externally. So even on the dev box, this
   route is unreachable from outside the box - only processes running locally on
   the dev box (like this harness) can reach it. This is belt-and-suspenders on top
   of gate 1, not a substitute for it.

**Consequence:** this pipeline can only ever run on the dev box. It will never work
against staging or prod, by design, on purpose. Do not try to make it work there.

### Layer 2: Document interception (the actual auth-bypass trick)

Even with the internal route above, there's a problem: a browser that anonymously
navigates to `http://127.0.0.1/app/` gets redirected to WorkOS login, because that
route (the real, public `/app/` route) checks for a real session cookie.

The harness solves this with Puppeteer's request interception, intercepting ONLY
the main document navigation request:

1. Puppeteer enables `page.setRequestInterception(true)`.
2. In the request handler, it checks: is this request the top-level navigation to
   `http://127.0.0.1/app/` (or `/app/?...`)? If yes, instead of letting the browser
   actually fetch it, the harness fetches `http://127.0.0.1:5500/internal/capture/app`
   itself (server-side, via Node's `http` module - not through the browser) and
   hands that HTML back to the browser as the response body for the `/app/` request.
3. Every OTHER request the browser makes (JS bundles, CSS, images, and critically
   all `/appserver/...` XHR calls for market/pattern data) is allowed to `continue()`
   untouched, flowing through nginx on port 80 exactly like a real browser session.

The net effect: the browser's address bar and `window.location` stay on the real
origin `http://127.0.0.1/app/?...` (so the React app's own querystring-reading code
works normally), but the actual HTML body it received was server-rendered for the
capture-bot identity. From the app's point of view, it IS a real logged-in
strategist-tier session; it just never went through `/login`.

If you ever see WorkOS login HTML captured instead of the app (recognizable by
WorkOS branding/redirect content in a screenshot, or a meta.json with clearly wrong
`capture_meta_snapshot`), the interception is broken - see the failure-modes table
in section 7.

### Layer 3: State seeding (localStorage + cookies)

Before the app's JavaScript ever runs, the harness seeds `localStorage` and cookies
so the app boots directly into the desired state (dark/light theme, selected
market, chart options, etc.) instead of its out-of-the-box defaults.

This happens via `page.evaluateOnNewDocument(...)`, which injects a script that
Puppeteer guarantees runs at document-start, before any of the app's own scripts,
on every navigation.

**Critical gotcha - key scoping is inconsistent across the app, and you must match
it exactly or your seed silently does nothing:**

- Most app localStorage keys are **user-scoped**: the real key on disk is
  `"<uuid>:<keyName>"`, and the value is JSON-encoded (this is what the app's own
  `Common.js` helpers `lsGet`/`lsSet` do internally). The harness must know the
  bot's UUID (fetched in Layer 1/2) before it can build these keys, which is why
  the harness always fetches the internal shell once up front, purely to extract
  `window.current_user_id` before it does anything else.
- `UITheme` is the one exception: the app reads it via a raw, unscoped
  `localStorage.getItem('UITheme')` call, and the value is a plain string (`"dark"`
  or `"light"`), NOT JSON-encoded. Seed it unscoped and unquoted.
- `tw_notifybell_seen` and `tw_symbolbox_seen` are ALSO unscoped/raw (see the
  Overlay Suppression subsection below for why they matter) - this is inconsistent
  with the rest of the app, but that inconsistency is real and you must seed these
  two the same unscoped way `UITheme` is seeded, not the scoped way most keys are.

**Full seeding map** (mechanism, exact key, format, and where the app reads it):

| Mechanism | Key | Scoping | Format | Where read |
|---|---|---|---|---|
| localStorage | `UITheme` | unscoped, raw | string `"dark"` / `"light"` | App.js |
| localStorage | `tw_notifybell_seen` | unscoped, raw | any non-empty string | SeasonalBarChart.js:1657-1659 |
| localStorage | `tw_symbolbox_seen` | unscoped, raw | any non-empty string | TextBox.js:9,24-26 |
| localStorage | `tw_last_welcomed_tier` | user-scoped, JSON | `{tier:'strategist', wasTrial:false}` | subscription welcome-modal logic |
| localStorage | `tw_lesson_enrolled` | user-scoped, JSON | `'1'` | onboarding.js isEnrolled() |
| localStorage | `tw_lesson_lastopened` | user-scoped, JSON | `7` | LessonBox.js:336 |
| localStorage | `oppTableColumnVisibility` | user-scoped, JSON | object (from spec `oppTable.columnVisibility`) | OppTable.js |
| localStorage | `oppTableColumnOrder` | user-scoped, JSON | array (from spec `oppTable.columnOrder`) | OppTable.js |
| localStorage | `showProjection` | user-scoped, JSON | boolean (from spec `priceChart.showProjection`) | StockLineChart.js |
| localStorage | `showMaxProjection` | user-scoped, JSON | boolean | StockLineChart.js |
| localStorage | `projectionPeriod` | user-scoped, JSON | string (numeric string) | StockLineChart.js |
| localStorage | `showVolume` | user-scoped, JSON | boolean | StockLineChart.js |
| localStorage | `maConfig` | user-scoped, JSON | object (from spec `priceChart.maConfig`) | StockLineChart.js |
| localStorage | `bbConfig` | user-scoped, JSON | object (from spec `priceChart.bbConfig`) | StockLineChart.js |
| localStorage | `priceChartTimeframe` | user-scoped, JSON | string (from spec `priceChart.timeframe`) | StockLineChart.js |
| localStorage | `chartRange` | user-scoped, JSON | string (from spec `priceChart.chartRange`) | StockLineChart.js |
| localStorage | `showEarnings` | user-scoped, JSON | boolean | StockLineChart.js |
| cookie | `WindowNumber` | suffix-scoped by app convention (cookie, not localStorage - see note) | numeric string `0`/`1`/`2` | App.js:454-463 (initialWindowNum) |
| cookie | `selectedSecurity` | plain | market group id string, e.g. `"2"` | App.js market selection |
| cookie | `showPEOpps` | plain | `"true"` / `"false"` | opp table PE-mode toggle |
| cookie | `MFE` | plain | boolean-as-string | SeasonalBarChart MFE overlay |
| cookie | `MAE` | plain | boolean-as-string | SeasonalBarChart MAE overlay |
| cookie | `oppYearsPerGroup` | plain | JSON string (from spec `oppTable.yearsPerGroup`) | OppTable years-per-group state |
| cookie | `oppYearsPerGroupPE` | plain | JSON string (from spec `oppTable.yearsPerGroupPE`) | OppTable PE years-per-group state |
| cookie | `terms_accepted` | suffix-free but VALUE-checked against the uuid | value must literally equal the bot's uuid | App.js:1966-1972 |
| cookie | `first1` | plain | `"1"` | first-visit gating |
| cookie | `tw_onboard_dismissed_<uuid>` | name suffix-scoped by uuid | `"1"` | onboarding dismiss state |
| cookie | `tw_conversion_shown_<uuid>` | name suffix-scoped by uuid | `"1"` | conversion-modal shown state |

Note on `WindowNumber`: this is a cookie, not localStorage, despite the ecosystem
convention of scoping most per-user settings via localStorage - it is included
here because it directly controls which of the three lower-display slides
(seasonal / trade detail / price) the app opens on. See Layer 5 for the important
gotcha that a deep-link querystring silently overrides this cookie.

### Layer 4: Overlay suppression

Beyond seeding the intended UI state, the harness must also suppress a set of
one-time popups, modals, and pulsing attention-animations that the real app shows
to real users on their first visits. If left unsuppressed, these pollute the
screenshot (a modal covering the chart) or - more insidiously - defeat the
stability gate forever (see Layer 7), because an infinite CSS pulse animation can
never produce two byte-identical screenshots.

The full must-seed set, and why each one is needed:

- `terms_accepted=<uuid>` (cookie) - App.js checks this cookie's VALUE against the
  current user's id, not just its presence. Must be seeded with the bot's own UUID,
  not a placeholder.
- `first1=1` (cookie) - first-visit flag.
- `tw_onboard_dismissed_<uuid>=1` (cookie) - suppresses onboarding tour overlay.
- `tw_conversion_shown_<uuid>=1` (cookie) - suppresses the trial-to-paid conversion
  modal.
- `tw_last_welcomed_tier` (user-scoped localStorage, `{tier:'strategist',
  wasTrial:false}`) - suppresses the SubscriptionWelcomeModal, which otherwise pops
  up and covers the screen.
- `tw_lesson_enrolled='1'` AND `tw_lesson_lastopened=7` (both user-scoped
  localStorage) - **this pair was found empirically, the hard way, and enrollment
  alone is NOT sufficient.** Because the capture-bot user's `created_at` is always
  "today" (it's a persistent row, but the onboarding-arc eligibility logic in
  `onboarding.js` treats a fresh-looking account as eligible), the app auto-enrolls
  it into a 7-day "LessonBox" onboarding arc on every load unless
  `tw_lesson_enrolled` is already set. But enrollment status ALONE does not stop the
  box from popping open - `LessonBox.js:336` separately auto-opens the box on mount
  whenever the computed onboarding day is greater than the persisted
  `tw_lesson_lastopened` value (which defaults to 0 if unset). So you must ALSO seed
  `tw_lesson_lastopened=7` (past the entire 7-day arc) so the "already opened today,
  stay collapsed" branch is always taken. Missing either half of this pair
  reproduces as a lesson card sliding into view mid-capture, which looks exactly
  like a chart-animation hang and can burn a lot of debugging time if you don't
  already know this.
- `tw_notifybell_seen='1'` (raw, unscoped localStorage) - suppresses a 2-second
  infinite CSS pulse (`twNotifyPulse ... infinite`) on the "Remind me" bell icon in
  the top control bar. An infinite animation can never settle, so this alone
  permanently defeats the visual-stability gate if unseeded.
- `tw_symbolbox_seen='1'` (raw, unscoped localStorage) - same pattern as the notify
  bell, on the AAPL/symbol input pill (`twSymbolPulse ... infinite`).

**The general lesson here, worth internalizing before you extend this tool:** any
future first-visit UI affordance (a new tooltip, a new pulsing hint, a new modal)
that ships in the React app WILL eventually break this harness's stability gate the
same way, unless its "already seen" flag is added to this seed list. See section 8,
Change Management.

### Layer 5: Deep link (driving the app to a specific pattern)

If a spec includes a `pattern` block, the harness builds a `?o=<base64>` querystring
deep link and navigates to it. The encoded payload, before base64, is:

```
<group_id>|<symbol>|<YYYY-MM-DD>|<daysOut>|<years>
```

- `group_id` is the numeric market/resource-group id (e.g. `"2"` for S&P 500
  Stocks) - see section 4 for the full id-to-name map.
- `symbol` is the ticker, e.g. `AAPL`.
- `<YYYY-MM-DD>` is the pattern's start date.
- `daysOut` is the pattern length in days.
- `years` is either a plain number as a string (e.g. `"10"`, meaning consolidated
  10-year mode) or a PE-cycle-prefixed string like `"pe2-10"` (meaning PE-cycle
  mode, offset 2, 10 years).

**Gotcha 1 - this deep link only applies AFTER data loads, not at parse time.** The
React app decodes `?o=...` early, but the harness must wait until the token,
securities list, and opportunities have all loaded before the deep link visibly
"takes." The harness's actual wait condition is: first `ready.oppTable` becomes
true, THEN it polls until `meta.seasonal.symbol` equals the spec's target symbol
(confirming the deep-linked pattern, not just some default pattern, actually
rendered).

**Gotcha 2 - any querystring except exactly `?set=on` forces the lower display to
slide index 2 (the price chart) at boot,** regardless of the `WindowNumber` cookie
seeded in Layer 3. This is implemented in App.js around line 454-459:
`initialWindowNum` reads the `WindowNumber` cookie, but then overrides it to `2` if
`window.location.search` is non-empty and not literally `?set=on`. Since a deep-
linked capture always uses `?o=...` (never `?set=on` - that value is reserved by
the app for auto-opening the settings panel, and is unrelated to display state),
every deep-linked capture boots on the price slide first, no matter what
`spec.display` actually asked for.

The harness handles this by detecting the mismatch after boot and correcting it:
it clicks the Swiper's own next/prev navigation arrows (`.swiper-button-next` /
`.swiper-button-prev` inside `.stock-linechart-parent`) the right number of times
to reach the intended slide, waiting 300ms between clicks for the slide-transition
animation, then waits again for that slide's own readiness flag. This is done
programmatically via real UI clicks rather than reaching into React state, because
the underlying Swiper instance is not exposed on `window` (it only lives in React
component state).

If a spec has NO `pattern` block, the harness instead navigates with `?set=on`
(the one querystring value that does NOT force slide 2), and in that case the
`WindowNumber` cookie should take effect directly - but the harness still actively
verifies the resulting slide via the DOM rather than assuming the cookie worked,
correcting it the same way if not.

### Layer 6: Readiness flags

`web-react/src/components/captureReady.js` is a tiny, pure instrumentation module
with two exported functions and zero side effects on real user behavior:

```js
markCaptureReady(name, meta)   // sets window.__twCapture.ready[name] = true
                                 // and window.__twCapture.meta[name] = meta
clearCaptureReady(name)        // sets window.__twCapture.ready[name] = false
```

Four components call these at their own real render-complete convergence points:

| Component | `name` | Called on |
|---|---|---|
| OppTable.js | `oppTable` | opp table rows finish rendering (cleared on new fetch, marked once row count > 0, with `{rows, month, day, years}` meta) |
| SeasonalBarChart.js | `seasonal` | seasonal (upper) bar chart finishes rendering (cleared on new `ChartData4` fetch, marked with `{symbol, years, points}` meta) |
| SeasonalBarChart.js | `trendChart` | lower trend-line chart data lands - this is the `consolidated_seasonal_chart2` fetch inside SeasonalBarChart.js that feeds `SeasonalChart.js` (the swiper's slide 0, "N Year Trend Chart for \<symbol\>" / "N PE+2 Year Trend Chart..."). A DIFFERENT fetch/effect than `seasonal` above, in the same file - `seasonal` going true does NOT imply `trendChart` is ready. Cleared at the start of that fetch's effect, marked once `cons_seas_chart` resolves non-empty, with `{symbol, points}` meta |
| StockLineChart.js | `price` | price chart finishes rendering (cleared on new fetch, marked with `{symbol, points}` meta) |
| TradeDetail.js | `tradeDetail` | trade-detail view finishes rendering (cleared both on new symbol AND right before its own re-mark, marked with `{symbol}` meta) |

Each flag is explicitly CLEARED at the moment its component starts a new fetch, and
only set back to true once that fetch's data has actually rendered. This means a
stale `true` value from a previous state can never be misread as "ready" for the
new state - the harness's `page.waitForFunction` polls are safe against races
because a flag briefly goes false again the instant new data starts loading.

The harness's own capture flow waits on these flags directly:
`window.__twCapture.ready.oppTable === true` first (this gates almost everything,
since the opp table is what proves the token+securities+opportunities pipeline is
fully up), then on the specific display's own flag (`seasonal` / `tradeDetail` /
`price`) matching `spec.display`. When `spec.display === "seasonal"`, the harness
ALSO waits on `trendChart` (both in the main post-slide-switch wait and inside
`switchSlide()`, since either path can be the one that lands on slide 0) - this
was added 2026-07-09 after a cold-load blank trend-chart capture slipped past the
`seasonal` flag alone (see the CHANGELOG).

`window.__twCapture.meta` is also what gets embedded in the final `meta.json` as
`capture_meta_snapshot` - it is the harness's evidence that real, current,
correctly-targeted data was on screen at capture time (row counts, symbol, point
counts, timestamps), not just a claim.

### Layer 7: Stability gate

Chart.js (the charting library used for the seasonal bar chart and price chart)
draws with entry animations - bars and lines tween into position over roughly
400-800ms, and charts can briefly re-layout right after first paint. A screenshot
taken the instant a readiness flag goes true can capture a mid-animation frame
(partially-drawn bars, wrong-height lines).

The harness's fix: take a full-page screenshot, wait 600ms, take another, and
byte-compare them. If identical, the page is visually settled and it proceeds to
the real capture. If not identical, repeat, up to 10 tries (6 seconds max). If it
never converges within 10 tries, this is logged as a WARNING (not a hard failure)
and the harness captures anyway - the assumption being that a real, persistent
animation-loop bug (see Layer 4's discussion of infinite CSS pulses) is more likely
than a chart that simply never finishes animating, and the operator should read the
warning and investigate rather than have the whole run silently fail.

### Layer 8: Sanity gates

Before writing the final `meta.json`, the harness runs several fail-fast checks.
Any failure here calls `fail()`, which prints and exits 1 - there is no silent
degraded-success path:

1. Every readiness flag not equal to `true` at capture time produces a WARNING
   (not necessarily a hard failure - a slide that was never visited legitimately
   has `false`).
2. `meta.oppTable.rows` must be greater than 0, or it's a hard failure (empty opp
   table almost always means the market/pattern combination genuinely has no data,
   or something upstream broke).
3. Every written PNG must be larger than 20KB, or it's a hard failure (this is the
   simplest, cheapest signal that a screenshot isn't a blank/broken panel).
4. Every written PNG is also sampled for byte-value entropy (a coarse,
   dependency-free proxy for "does this look like a real chart or a solid-color
   blank" - see the code comment on `countDistinctColorsPNG` for exactly why this
   crude method was chosen over a real image-analysis dependency). Fewer than 20
   distinct byte values in the first 200KB of file content is a hard failure.
5. If a `full` crop was captured, its PNG dimensions (read directly from the PNG's
   IHDR chunk, no image library needed) must exactly equal
   `viewport.width * scale` by `viewport.height * scale`. A mismatch is a hard
   failure.
6. Any browser console errors captured during the run are recorded in the output
   meta.json's `console_errors` array (not a hard failure by itself, but always
   worth reading - a console error alongside a stability-gate warning is a strong
   signal of a real bug, not a flake).

## 4. The Market Group ID Map

The `?o=` deep link needs a numeric market/resource-group id, but specs address
markets by human-readable name (e.g. `"S&P 500 STOCKS"`). `capture.js` hardcodes
this mapping as `RESOURCE_GROUPS` (and its reverse, `RESOURCE_GROUP_IDS`):

```
0  DOW 30 STOCKS
1  NASDAQ 100 STOCKS
2  S&P 500 STOCKS
3  RUSSELL 1000 STOCKS
4  WILSHIRE 5000
5  INDICES COMMON
6  INDICES ALL
7  FUTURES & COMMODITIES
8  FOREX ALL
9  FOREX LIQUID
10 GOVERNMENT BONDS
11 ETFs
12 LONDON EXCHANGE
13 TORONTO STOCKS
   (14, 15 intentionally absent - old Korea markets, removed; do not fill the gap)
16 CRYPTO CURRENCIES
```

This is sourced from `config.py`'s `available_resources` dict (currently around
line 461-480), which is the actual single source of truth - these ids are
documented elsewhere as permanent, stable identifiers that must never be
renumbered. The running React app gets this same mapping at runtime from
`GET /appserver/getResourcesObj`, which just echoes `config.available_resources` -
so this hardcoded table in `capture.js` cannot silently drift from what the live
app actually uses, but if `config.py`'s dict is ever edited (a new market added, an
id repurposed), `capture.js`'s copy must be updated to match by hand. It is not
fetched dynamically at capture time.

If a spec's `market` field is not a recognized name, `capture.js` fails immediately
with a message listing every valid name it knows.

## 5. Spec File Schema (spec_version 1)

Every spec is a JSON file under `specs/`. `spec_version` MUST be present and equal
to `1` - the harness hard-fails otherwise. This is a deliberate version guard: if
the schema ever changes in a backward-incompatible way, `spec_version` must be
bumped and the harness updated to handle old and/or new versions explicitly, rather
than silently misinterpreting an old spec file under new rules.

**Field names in a v1 spec are a stable contract.** Do not casually rename a field
- that breaks every existing spec file silently (wrong/missing data, not an error).
If you need to change a field's meaning or name, bump `spec_version` and add
explicit handling for both versions, or do a coordinated rename across every spec
file in `specs/` in the same change.

**2026-07-09 note:** the new crop names (`waveViewer`, `viewerPlusDisplay`,
`appNoBanner`) and the new `oppTable.cropRows` field are ADDITIVE - they did
not require a `spec_version` bump because every existing spec file continues
to mean exactly what it meant before (no field was renamed or reinterpreted;
`crops` simply now accepts three more valid string values, and `oppTable`
simply now accepts one more optional field). `spec_version` stays `1`.

| Field | Required | Type / values | Meaning |
|---|---|---|---|
| `spec_version` | yes | `1` | Schema version guard |
| `theme` | no (default `"dark"`) | `"dark"` \| `"light"` | Seeds `UITheme` |
| `display` | yes | `"seasonal"` \| `"tradeDetail"` \| `"aiScores"` \| `"price"` | Which lower display to capture. The harness selects the accessible semantic dot because Price Chart may be index 2 or 3 when AI Scores is available. `aiScores` waits for a populated stats view by default and therefore requires an eligible U.S. stock/ETF account and market. |
| `aiScores` | no | object with optional `expectedState`, `openGuide`, `changeDaysTo`, and `changeDaysBy` | `expectedState` defaults to `"populated"`; use `"empty"` with no `pattern` to verify the selected-market/no-Wave-Viewer-pattern watermark. `openGuide: true` opens the information guide after a populated panel is ready. `changeDaysTo: N` or `changeDaysBy: D` (mutually exclusive integers) changes the visible Wave Viewer duration after the initial populated selection, then requires exactly one isolated `request_origin: "wave_viewer"` ML score batch and a populated panel for the new duration. A relative change reverses its delta only when the requested value is beyond the selector boundary, keeping boundary-row captures useful. TradeWave windows are measured in calendar days: the harness verifies the request's raw `daysOut` equals the displayed target minus 1 and that `years` remains a string. |
| `market` | yes if `pattern` is set | one of the names in section 4 | Which resource group to select |
| `symbol` | yes if `pattern` is set | ticker string, e.g. `"AAPL"` | Which symbol the deep link targets |
| `pattern` | no | object: `{startDate, daysOut, years, pe}` | If present, builds a `?o=` deep link (see Layer 5 above). Omit entirely to capture the app's default/no-pattern state |
| `pattern.startDate` | yes if `pattern` set | `"YYYY-MM-DD"` | Pattern start date |
| `pattern.daysOut` | yes if `pattern` set | integer | Pattern length in days |
| `pattern.years` | yes if `pattern` set | integer | Years of history (consolidated mode) |
| `pattern.pe` | no | string or `null` | If set (e.g. `"pe2"`), builds PE-cycle mode years field as `"pe2-<years>"` instead of plain `"<years>"` |
| `scale` | no (default `2`) | `2` \| `4` | `deviceScaleFactor` - 2 = Retina-equivalent, 4 = extra-high-density |
| `viewport` | no (default `{width:1920, height:1080}`) | `{width, height}` | Browser viewport size in CSS pixels (actual PNG pixels = viewport * scale) |
| `leftPanelCollapsed` | no (default `false`) | boolean | Seeds the saved desktop Opportunity Table/Tara panel state before the app starts. Use `true` to verify a requested lower display still renders correctly with the narrow reopen rail visible. |
| `priceChart` | no | object, all fields optional | Seeds price-chart localStorage options: `showProjection`, `showMaxProjection`, `projectionPeriod`, `showVolume`, `maConfig`, `bbConfig`, `timeframe`, `chartRange`, `showEarnings` (see the full table in Layer 3) |
| `seasonal` | no | `{showMFE, showMAE}` (booleans, default both `true`) | Seeds the `MFE`/`MAE` cookies controlling seasonal-chart overlays |
| `oppTable` | no | object, all fields optional | `columnVisibility`, `columnOrder` (localStorage), `yearsPerGroup`, `yearsPerGroupPE` (cookies, JSON-stringified), `cropRows` (integer, crop-sizing only - see section 6), and `selectRow` (zero-based visible row or `"firstAvailableAI"`). Use `selectRow` to populate the viewer exactly as a user does; `"firstAvailableAI"` requires one visible AI column and verifies that row's symbol loads. The AI Scores panel requires a real table selection rather than an arbitrary viewer deep link. |
| `crops` | no (default `["full"]`) | array of `"full"` \| `"waveViewer"` \| `"viewerPlusDisplay"` \| `"appNoBanner"` \| `"display"` \| `"oppTable"` | Which screenshots to take (see section 6) |
| `out` | no (default `"out/capture"`) | path prefix string | Output files are written as `<out>.<crop>.png` and `<out>.meta.json` |

### The six crop types

Added 2026-07-09: `waveViewer`, `viewerPlusDisplay`, `appNoBanner`, and the
`oppTable.cropRows` proportional-sizing option (see the CHANGELOG entry at the
end of this document for the full story, including a real Puppeteer bug that
had to be worked around along the way). `full`, `display`, and unbounded
`oppTable` are unchanged and remain backward compatible.

| Crop | DOM region | Excludes `#main-header`? | Prefer for... |
|---|---|---|---|
| `full` | entire viewport, full-page screenshot | **No** - the one crop that intentionally keeps the site banner (logo + top menu). Use only for the rare case the banner itself is wanted | The ~1% case where the TradeWave banner needs to be in the shot |
| `waveViewer` | `.seasonal-barchart-parent` - the seasonal bar chart + its OWN control header (symbol/date/years/PE dropdowns), NOT the site banner | Yes | **Default for articles**: the wave viewer alone, most-requested crop |
| `viewerPlusDisplay` | `#right-content` - `waveViewer` stacked on top of the lower swiper display pane (seasonal trend chart / trade detail / price chart, whichever is active) | Yes | **Default for articles**: wave viewer + one lower display together, the full right column |
| `appNoBanner` | `#root` - everything the React app renders (opp table + wave viewer + lower display), banner excluded | Yes | Occasional "everything together" shots without the banner |
| `display` | `.stock-linechart-parent` - just the lower swiper display pane (whichever of seasonal/tradeDetail/price is active), unchanged since initial build | Yes (it never included the banner to begin with) | Just the lower display alone |
| `oppTable` | `.opp-container .opp-table-controls` (top) through the last captured data row (bottom) - see `cropRows` below for how many rows | Yes (it never included the banner to begin with) | The opportunity table alone, sized to its actual content |

Any other crop name is a hard failure with a message listing the valid options.

**`waveViewer` vs `viewerPlusDisplay` vs `appNoBanner` - which to pick:** all
three exclude the banner identically (they all start at the same `y` - the
banner's own bottom edge, verified empirically to be flush with zero gap).
The difference is only how much of the right column / whole app they include.
`waveViewer` and `viewerPlusDisplay` are the defaults for articles per the
owner's usage preference; reach for `appNoBanner` only when the opp table
needs to be in the same image, and `full` only when the banner itself must be
shown (rare).

#### `oppTable.cropRows` - proportional opp-table sizing

Before 2026-07-09, the `oppTable` crop always screenshotted `.opp_table_div`
via `element.screenshot()` - a fixed-height pane (`oppTableHeight` in
OppTable.js, e.g. `calc(100% - 90px)` on desktop) with `overflow-y:auto`. A
1-row result still produced a PNG as tall as the whole pane (empirically
1954px), mostly empty space below the single row. This was a real, reported
bug, not a hypothetical one.

Fixed by computing the crop rect directly from real row `boundingClientRect`s
instead of the pane's fixed CSS height:

- **Top** of the crop = the top of `.opp-container .opp-table-controls` (the
  PE/month/day/years controls row).
- **Bottom** of the crop = the bottom of the LAST included data row (from
  `.opp-container .opp-table table.table-striped tbody tr`), clamped to the
  scroll pane's own visible viewport (`.opp-container .opp-table`'s own
  `clientRect` - a row that's scrolled out of view can't be captured; the
  harness always starts unscrolled, so in practice this only matters if a
  future spec seeds a non-zero scroll position).
- **Row count**: by default (no `oppTable.cropRows` in the spec), ALL current
  rows are included - this is a proportionality fix, not a truncation; a
  308-row table still shows all 308 rows, just without the old empty-space
  padding below them. Set `oppTable.cropRows: N` (integer) to cap the crop to
  at most N rows - e.g. `{"oppTable": {"cropRows": 10}}` for a 10-row teaser
  crop. If N is greater than the number of rows actually returned, ALL
  available rows are used instead (no error, no filler) - the actual number
  used is recorded as `actualRows` in that crop's entry in `meta.json`'s
  `files` array, so you can always tell after the fact whether the cap was
  hit or the table simply had fewer rows than requested.

Verified empirically on both ends of the range: a 308-row AAPL/S&P 500 table
with `cropRows: 10` produced a 446px-tall crop (10 rows, no filler); a
genuinely 1-row PE-mode SPX table with `cropRows: 10` requested produced a
127px-tall crop with `actualRows: 1` (all available rows used, still no
filler, correctly short rather than padded out to 10 rows' worth of height).

### Worked example: adding a new spec

Say you want a 2x dark-theme screenshot of TSLA's price chart with volume and
Bollinger Bands shown, cropped to just the display region. Create
`specs/tsla_price_bb.json`:

```json
{
  "spec_version": 1,
  "theme": "dark",
  "display": "price",
  "market": "S&P 500 STOCKS",
  "symbol": "TSLA",
  "pattern": { "startDate": "2026-03-01", "daysOut": 20, "years": 10, "pe": null },
  "scale": 2,
  "viewport": { "width": 1920, "height": 1080 },
  "priceChart": { "showVolume": true, "bbConfig": { "enabled": true, "period": 20 }, "timeframe": "daily", "chartRange": "1y" },
  "crops": ["display"],
  "out": "out/demo/tsla_price_bb"
}
```

Then run:

```bash
cd /home/flask/tools/ui_capture
./capture.sh specs/tsla_price_bb.json
```

Check `out/demo/tsla_price_bb.meta.json` afterward to confirm `capture_meta_snapshot`
shows `symbol: "TSLA"` and a sane `points` count, and that no warnings or console
errors were recorded. If `bbConfig`'s exact shape is unfamiliar, check how
`StockLineChart.js` reads and applies it before guessing the field names - a wrong
shape will silently no-op rather than error, since it's just an opaque JSON blob
seeded into localStorage.

### Existing example specs (as of 2026-07-09)

Six working specs live in `specs/`, all targeting AAPL with the same pattern
(`2026-01-15`, 15 days out, 10 years, S&P 500 Stocks):

- `aapl_opptable_dark.json` - dark theme, `oppTable` crop only.
- `aapl_price_dark.json` - dark theme, price display, `full` + `display` crops,
  with projection and volume overlays on.
- `aapl_seasonal_dark.json` - dark theme, seasonal display, all three crops
  (`full`, `display`, `oppTable`), MFE/MAE overlays on.
- `aapl_seasonal_light.json` - same as above but light theme.
- `aapl_tradedetail_dark.json` - dark theme, tradeDetail display (the wave
  stats + cumulative-return panel), `full` + `display` crops.
- `aapl_seasonal_dark_4x.json` - same as `aapl_seasonal_dark` but at `scale: 4`
  and only `full` + `display` crops, for testing extra-high-density output.

The later `first_opportunity_ai_scores_dark.json` regression spec selects the first
visible S&P 500 opportunity with an available AI value and the semantic `aiScores`
display. It verifies that row's symbol reaches the Wave Viewer and waits for the numeric
Quick Read before taking `full` and `display` crops. Selecting a real Opportunity Table
row matters: an arbitrary Wave Viewer deep link does not publish the row-bound AI bundle
used by the panel.

`first_opportunity_ai_scores_duration_change_dark.json` extends that real-row flow by
moving the Wave Viewer one calendar day shorter after the initial AI Scores panel is
populated (or one day longer if the selected row is already at the lower boundary). It
captures only sanitized MLScoreBatch fields--never the token-bearing request URL--and
fails unless the change sends exactly one top-level `request_origin: "wave_viewer"`
batch containing one opportunity, raw `daysOut = displayed days - 1`, and string
`years`. It then waits for both the new `N-day historical pattern` line and the
`Wave Viewer AI reading` Quick Read before allowing a screenshot.

`dow_ai_scores_empty_dark.json` selects DOW 30 without a pattern and waits for the
empty AI Scores watermark. This protects the market-selected/no-Wave-Viewer-pattern
case from regressing into a loading or instruction card.

`first_opportunity_ai_guide_dark.json` follows the same real-row selection as the
populated panel spec, opens the information guide, and captures the full app so its
plain-language first screen can be reviewed visually.

`first_opportunity_ai_scores_1366_dark.json` repeats the real-row populated-panel
capture at a 1366x768 viewport. It is the compact-desktop release gate for internal
scrolling, cramped checkpoint columns, and title/dot overlap.

`first_opportunity_ai_scores_collapsed_dark.json` repeats the populated AI Scores
capture with the Opportunity Table/Tara panel collapsed. Its full crop verifies the
narrow reopen rail while its display crop verifies that the semantic fourth window
and populated AI content remain available after the surrounding layout changes width.
Both expanded and collapsed AI captures require the exact semantic panel order
`Trend Chart`, `Wave Stats`, `AI Scores`, `Price Chart`; the harness fails if one is
missing, duplicated, or replaced.

## 6. Reading `meta.json`

Every capture run writes `<out>.meta.json`. Fields:

- `spec` - the exact input spec, echoed back (so the output is self-describing
  without needing to keep the spec file around).
- `resolved.deep_link_o` / `resolved.deep_link_decoded` / `resolved.querystring_used`
  - the actual base64 deep link built and the querystring navigated to, decoded for
  human readability.
- `resolved.ai_score_duration_change` - `null` for ordinary captures; for an AI
  duration-change capture, the requested and resolved calendar-day change plus a
  sanitized proof that exactly one Wave Viewer batch used one opportunity, the
  correct engine-day offset, and a string `years` value. Tokens and raw request
  bodies are never written here.
- `bot_uuid` - the capture-bot's UUID as discovered at runtime (see Layer 1 - never
  hardcode this elsewhere; read it from here if you need it for manual debugging).
- `bundle_hash` - the React bundle's content hash, extracted from the
  `main.<hash>.js` script tag actually loaded. This is your proof of exactly which
  build of the app produced this screenshot - if a screenshot looks wrong, check
  this against what you expect to be currently built (see the CHANGELOG at the end
  of this document for the hash at time of writing).
- `capture_meta_snapshot` - the full `window.__twCapture.meta` object at capture
  time: per-display symbol/years/points/row-count/timestamp evidence that real,
  correctly-targeted data was on screen (this is the "data-as-of" evidence
  referenced elsewhere in TradeWave docs - it is what lets you trust a screenshot
  wasn't blank or stale).
- `files` - array of `{crop, path, bytes}` for everything written, PLUS (added
  2026-07-09, all crops except `full`): `clip` - the exact `{x, y, width,
  height}` CSS-px clip rect that was measured and captured for that crop
  (viewport coordinates, pre-`scale` - multiply by `scale` to get the PNG's
  actual pixel dimensions). For `oppTable` specifically, also `actualRows` -
  how many data rows actually ended up in the crop (see the `cropRows`
  section above for why this can differ from the requested count).
- `warnings` - non-fatal issues (e.g. stability gate didn't converge).
- `console_errors` - any browser console.error or page error text captured during
  the run.
- `wall_time_ms` - total run time.
- `captured_at` - ISO timestamp.

A completely clean run has empty `warnings` and `console_errors` arrays. Always
check both before trusting output for anything customer-facing.

## 7. Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| `403` on JS/CSS assets right after a React rebuild | `npm run build` can leave files under `build/` unreadable by nginx's `www-data` user (wrong permissions from the build process or a restrictive umask) | `chmod -R 755` on build directories, `644` on files; re-verify nginx can read them (nginx runs as `www-data`, not `flask`) |
| Timeout waiting for `__twCapture.ready.oppTable` | Opp table never rendered non-empty data - could be the appserver being down, the pattern/market combination legitimately having no data, or a slower-than-usual data pipeline | Check which display it was waiting on from the log output; check appserver logs/health; try the same market/symbol manually in a real browser session first |
| Timeout waiting for a specific display's ready flag (`seasonal`/`tradeDetail`/`price`) after a slide switch | That component's own fetch never completed or never called `markCaptureReady` | Check appserver logs for that specific data endpoint; check browser console_errors in the partial output; confirm the component's `markCaptureReady` call wasn't accidentally removed/broken in a recent React change |
| Stability gate never converges (`warnings` mentions it, 10 tries exhausted) | Almost always a new infinite CSS animation was added somewhere in the app (a new pulsing hint, a new "seen" style first-visit affordance) that was never added to the seed list | Reproduce visually (run without the capture, or diff two consecutive PNGs to spot what's moving), find the new "seen"/dismissed flag controlling it, add it to `buildLocalStorageSeed`/`buildCookieSeed`/the raw-key seeding block in `capture.js`'s `evaluateOnNewDocument` call, per Layer 4 |
| Internal capture route returns `404` | Either `config.tw2_env` is not `"dev"` on this box, or the route was never deployed/registered (stale gunicorn process, code not pulled) | Confirm `config.tw2_env == "dev"` via `python3 -c "import config; print(config.tw2_env)"`; confirm `web/app.py` on disk actually has `capture_app()`; restart `tradewave-web` if code was just pulled (gunicorn does not auto-reload) |
| Internal capture route returns `500` with `{"error": "capture bot user missing"}` | The `capture-bot@tradewave.local` database row does not exist (fresh box, or it was deleted) | Recreate the row directly (there is no seed script as of 2026-07-09 - see section 1's note on the bot account for the exact field values needed: email, `workos_user_id="capture-bot-dev"`, `roles=["user"]`, `tier="strategist"`) |
| A captured screenshot shows WorkOS login branding/redirect content instead of the app | The document-interception logic (Layer 2) broke - either the URL-matching condition no longer matches the real navigation URL, or the internal shell fetch itself is failing/erroring silently | Check `consoleErrors` and the raw meta.json; manually curl `http://127.0.0.1:5500/internal/capture/app` to confirm it still returns real app-shell HTML; check that the intercepted-URL match in capture.js still matches `APP_ORIGIN + APP_PATH` exactly |
| `Chrome not found` / Puppeteer launch error | Local `node_modules/` Puppeteer install is missing or incomplete | `cd /home/flask/tools/ui_capture && npm install` (see section 2) |
| PNG under 20KB / low byte-entropy sanity failure | Genuinely blank or broken render (data didn't load, canvas never painted, wrong crop selector matched nothing meaningful) | Re-run with the failing crop only, inspect the PNG directly, check `console_errors` and `capture_meta_snapshot` in the (still-written, since this check runs after files are on disk) meta.json for clues |

## 8. Honest-Data Rules

Captures on the dev box show DEV data. This is fine, and expected, for anything
about the mechanics of the UI itself - opp table layout, wave-pattern chart shapes,
column arrangements, chart styling. Dev's CSV/pattern data is current enough for
that purpose.

**It is NOT fine to present scorecard or performance-ledger statistics (win rates,
target-hit rates, any specific performance numbers) sourced from a dev-box
capture in any public-facing content.** Dev's `featured_history.json` (the file
backing those stats) is known to be stale. Prod is the only authoritative claim
source for performance statistics - see the TradeWave ecosystem doc and GTM
strategy notes on the ledger-stat claim rail for the exact two metrics that exist
(win_rate vs target_hit_rate) and which wording each maps to. If a screenshot
needs to show real performance numbers for a public claim, either capture it
against prod once that becomes possible, or hand-verify the numbers separately
against the prod source of truth before publishing.

## 9. Extension Points (Not Yet Built)

These are documented here as the intended next steps, so a future engineer or
model does not have to guess at the shape. As of 2026-07-09, none of the following
exist yet - only the CLI (`capture.js` run via `capture.sh`) exists.

- **HTTP wrapper.** Wrapping `capture.js` behind a small local HTTP endpoint so
  other tools/processes on the dev box can request a capture without shelling out
  directly. Same spec schema, same output contract - just a different transport
  in front of the same logic.
- **MCP tool** (working name `capture_tradewave_ui`). Exposing the same capability
  as an MCP tool so an AI agent session can request a UI screenshot directly. Same
  spec schema again - the schema is meant to be the stable contract regardless of
  which transport calls into it.
- **Per-display crop presets.** Right now `crops` is a flat list of the three
  generic regions (`full`/`display`/`oppTable`). A future version might add named
  presets for specific sub-elements (e.g. just the legend, just a single stat
  card) as new crop selectors.
- **Mobile viewports.** Not yet exercised by any example spec. Note before
  attempting one: the app forces dark theme on mobile widths (a genuine app
  behavior, not a capture-harness quirk - see App.js's "Force dark mode on mobile
  (non-tablet-landscape) - no toggle available" comment). A `theme: "light"` spec
  combined with a narrow mobile `viewport` would likely be silently overridden by
  the app itself, not a capture bug - do not "fix" this in the harness without
  first confirming it's actually a harness problem and not correct app behavior.

## 10. Change Management

If a React component that this harness depends on is renamed, restructured, or has
its DOM/CSS-class structure changed, you must update BOTH of the following in the
same change, or the harness will silently break (or worse, silently capture wrong
content) the next time someone runs it:

1. `capture.js` itself - specifically whichever of these it touches: the
   `RESOURCE_GROUPS` map (if `config.py`'s `available_resources` changes), the
   `DISPLAY_BOTTOM_PANEL` labels/semantic names (if the lower-panel contract
   changes), the localStorage/cookie seeding maps (if a state key is
   renamed), the crop selectors `.opp_table_div` / `.stock-linechart-parent` (if
   those class names change), or the swiper nav selectors
   `.swiper-button-next`/`.swiper-button-prev` (if the Swiper version or markup
   changes).
2. This document - update the relevant table/section so it matches.

The one thing that should NOT need to change for an internal refactor is the spec
file schema (section 5) - that is the stable contract specs are written against.
If a refactor forces a spec-schema change anyway, bump `spec_version` per section 5's
rules rather than silently reinterpreting existing fields.

If you add a new first-visit UI affordance anywhere in the app (a new pulsing
hint, a new one-time modal, a new "seen" flag), assume it WILL eventually break
either overlay suppression (section 3, Layer 4) or the stability gate (Layer 7),
and add its suppression to `capture.js` proactively rather than waiting to
discover it empirically the hard way, as happened with the lesson box and the two
pulse animations documented above.

## Prerequisites Checklist

Before running any capture, confirm on the dev box:

- [ ] `tradewave-web` systemd unit is running (serves the internal capture route
      on `127.0.0.1:5500`)
- [ ] `tradewave-appserver` is running (serves all the real `/appserver/...` data
      the app fetches)
- [ ] nginx is running and proxying `:80` normally (the harness's browser session
      goes through nginx for everything except the one intercepted document
      request)
- [ ] `config.tw2_env == "dev"` on this box (confirm with
      `python3 -c "import config; print(config.tw2_env)"`)
- [ ] The React bundle is built and current - build with `npm run build` from
      `web-react/` ONLY (this script carries `PUBLIC_URL=/app/`; a raw
      `react-scripts build` has previously blanked the app in production by
      emitting root-relative asset paths - never run it raw). At the time this
      document was written, the built bundle hash was `d6a04c8a`
      (`main.d6a04c8a.js`); after the `trendChart` instrumentation rebuild on
      2026-07-09 it became `0a32b236` (`main.0a32b236.js`) - if you see a
      different hash in a fresh meta.json, that's expected after any rebuild,
      just confirm it's the hash you intended.
- [ ] The `capture-bot@tradewave.local` user row exists in the database (see the
      failure-modes table if it's missing)
- [ ] `/home/flask/tools/ui_capture/node_modules/` exists (run `npm install` in
      that directory if not - see section 2)

## CHANGELOG

**2026-07-09 - Initial build.**

Built the full pipeline described in this document: the internal dev-only auth-
bypass route (`web/app.py:capture_app`), the `captureReady.js` instrumentation
module and its four call sites (OppTable.js, SeasonalBarChart.js,
StockLineChart.js, TradeDetail.js), and the `capture.js` Puppeteer harness plus
`capture.sh` wrapper.

Verified with 4 acceptance specs (`aapl_opptable_dark`, `aapl_price_dark`,
`aapl_seasonal_dark`, `aapl_seasonal_light` - a 5th, `aapl_seasonal_dark_4x`, was
added afterward to exercise `scale: 4`). All produced correctly-dimensioned,
correctly-sized PNGs:

- `aapl_opptable_dark.oppTable.png` - 406,567 bytes
- `aapl_price_dark.full.png` - 694,032 bytes; `aapl_price_dark.display.png` -
  136,427 bytes
- `aapl_seasonal_dark.full.png` - 802,036 bytes; `.display.png` - 146,755 bytes;
  `.oppTable.png` - 406,567 bytes
- `aapl_seasonal_light.full.png` - 758,035 bytes; `.display.png` - 232,658 bytes;
  `.oppTable.png` - 363,237 bytes

All ran against React bundle `main.d6a04c8a.js`, captured as the bot user
`99705e1e-17a4-4a34-a4c8-2bcd2e6ad5e6` on this box, all with zero warnings and zero
console errors in their meta.json output.

Two infrastructure bugs were found and fixed during this build:

1. Nginx could not read freshly-built React `build/` files (wrong permissions
   left over from the build process) - fixed by correcting permissions to `755`
   on directories / `644` on files so `www-data` could read them.
2. `/root` being mode 700 blocked the `flask` user from reaching the existing
   Puppeteer install at `/root/tw-uitools/node_modules` - fixed by giving this
   tool its own local `npm install` under `/home/flask/tools/ui_capture/`
   instead of weakening `/root`'s permissions (see section 2).

**2026-07-09 - `trendChart` readiness flag added.**

Closed a readiness gap: slide 0's lower trend-line chart (the "N Year Trend
Chart for \<symbol\>" panel rendered by `SeasonalChart.js`, fed by a
`consolidated_seasonal_chart2` fetch that lives in `SeasonalBarChart.js`, a
DIFFERENT effect than the one backing the `seasonal` flag) had no readiness
flag of its own. On a cold/slow load the harness could capture that pane
blank while still passing every existing gate (stable-but-blank), because the
`seasonal` flag it was actually waiting on covers only the upper bar chart.

Added `clearCaptureReady('trendChart')` / `markCaptureReady('trendChart',
{symbol, points})` to `SeasonalBarChart.js`'s `consolidated_seasonal_chart2`
fetch effect (flag calls only - no state, prop, JSX, or control-flow changes;
`captureReady.js` itself was untouched). Updated `capture.js` so that whenever
`spec.display === "seasonal"`, it also waits on `ready.trendChart === true`
(both in the main post-slide-switch wait and inside `switchSlide()`, since a
deep-linked capture can reach slide 0 via either path) and added `trendChart`
to the capture-time sanity-check flag list.

Verified empirically: `100yp_wave_pe2_dark.json` (a real cold deep-window PE
pattern) and `aapl_seasonal_dark.json` (the common-path regression check) both
exited 0 with zero warnings and zero console errors, `trendChart.points > 0`
in both meta.json outputs. Rebuilt bundle `main.0a32b236.js`.

**2026-07-09 - New crop regions (`waveViewer`, `viewerPlusDisplay`,
`appNoBanner`) + proportional `oppTable.cropRows`.**

Harness-only change (no React changes) adding the crop vocabulary the owner
actually wants for content work - the wave viewer alone excluding the site
banner, the wave viewer plus one lower display together, and everything
excluding the banner - plus fixing a real proportionality bug in the
`oppTable` crop. Full crop vocabulary and the `cropRows` mechanics are in
section 5/6 above; this entry is the "what changed and why," including two
real bugs found and worked around along the way.

*Selectors relied on (see section 3 for full context):* `#main-header`
(App.js/web/app.py `capture_app()` shell - confirmed via direct probe to be a
SIBLING of `#root` in the raw HTML, not an ancestor, with its own real
rendered height, e.g. 62px in the acceptance run below - not a stub);
`#right-content` (DesktopLayout.js right-column wrapper, parent of both the
wave viewer and the lower display panes); `.seasonal-barchart-parent`
(DesktopLayout.js wave-viewer pane); `.opp-container .opp-table-controls` and
`.opp-container .opp-table table.table-striped tbody tr` (OppTable.js /
TableBox.js controls row and data rows).

*Implementation approach:* clip rects are computed via `page.evaluate()`
reading real `getBoundingClientRect()` boxes (not hardcoded offsets), clamped
to the viewport. `appNoBanner` uses `#root` directly - since `#main-header`
sits OUTSIDE `#root` in the raw HTML (a sibling, populated by server-side
string substitution, not part of the React tree at all - see Layer 2/3 and
`web-react/public/index.html`'s own comment on this), `#root`'s own box is
already "everything below the banner," no further math needed. Verified
directly with a probe script: `#main-header` bottom = 62px, `#right-content`
top = 62px, flush with zero gap.

*The `oppTable` proportionality fix:* `.opp-table` (OppTable.css) is a
fixed-height (`oppTableHeight`, e.g. `calc(100% - 90px)`), `overflow-y:auto`
scroll pane - the OLD crop (`.opp_table_div` via `element.screenshot()`)
always captured that whole fixed box regardless of content, so a 1-row result
produced a 1954px-tall mostly-empty PNG (the bug as reported). Fixed by
measuring the actual row `boundingClientRect`s and sizing the crop to the
last included row's bottom edge instead of the pane's CSS height. New
optional `oppTable.cropRows: N` caps how many rows are included; omitted
means "all rows, but still proportional" (not "unbounded pane height" - the
old bug is fixed either way). If `N` exceeds the available row count, all
available rows are used and the actual count is recorded as `actualRows` in
`meta.json` - no error, no filler.

*A real Puppeteer bug found and worked around (the reason `capture.js` no
longer uses `page.screenshot({clip})` for anything but `full`):* while
building and testing `waveViewer`, the crop rect math was verified correct
(a manual software crop of a `full` screenshot at the exact same rect showed
the chart perfectly) but `page.screenshot({clip: {...}})` on that same
region, at the same instant, wrote a PNG with a completely BLANK chart -
reproducibly, not a rare flake. This was isolated with a controlled A/B
(same page state, immediately consecutive calls): `getImageData()` read
directly against the canvas's own backing store proved real, fully-painted
pixel data existed at the exact moment `page.screenshot({clip})` was called,
yet the clip screenshot still came out blank. This is a genuine
Puppeteer/Chrome capture-path bug in this environment (GPU-composited canvas
content desyncing from the `clip`-region screenshot path at 2x/4x
`deviceScaleFactor`), not a timing/animation-settle issue - the existing
stability gate and a new canvas-paint gate (below) both already confirmed
everything had settled and painted before this was tried, and a plain
unclipped `page.screenshot()` of the same page state never exhibited the bug.
**Fix: `capture.js` no longer calls `page.screenshot({clip})` for any crop
except `full`.** Instead (`captureCroppedRegion()` in `capture.js`), every
other crop takes one unclipped full-page screenshot, then crops it entirely
INSIDE the page via an offscreen `<canvas>` (`drawImage` + `toDataURL`) - a
software crop, immune to the clip-capture bug because it never invokes
Puppeteer's `clip` option at all. Verified this fixes it reliably across
repeated back-to-back runs of the same previously-always-blank spec.

*A second, unrelated real bug found along the way (defended against but not
the fix for the above):* `<BarChart>` (react-chartjs-2, rendered by
`SeasonalBarChart.js` only when `seasonalBarChartData.length > 0`) can
unmount and remount - a brand new `<canvas>`, entry animation restarting from
empty - if its `ChartData4` fetch effect re-fires for the same final
symbol/pattern after a deep link's props settle in more than one render pass
(`clearCaptureReady('seasonal')` fires on every new fetch, not just the
first). This can happen AFTER `ready.seasonal` already fired true once (the
harness's existing wait already passed). Defended against with a new canvas-
paint gate (`findBlankCanvases()`/`waitForCanvasesPainted()` in
`capture.js`): before the stability gate, every laid-out `<canvas>` under
`#right-content`/`.opp_table_div` is sampled via `getImageData()` (a coarse
20x20 grid, cheap) and confirmed non-blank, with retries and a `resize`-event
nudge (Chart.js redraws synchronously on resize); a second, crop-scoped check
runs again immediately before each canvas-bearing crop is captured, with its
own retries, and is a HARD FAILURE (not a warning) if still blank after
retries - per the fail-fast house rule, a silently-blank chart in a
marketing screenshot is exactly the failure mode worth stopping the run for.

*Verification (as the `flask` user, `cd /home/flask/tools/ui_capture`):* five
new `specs/crop_demo_*.json` files plus a re-run of the existing
`100yp_opptable_july_pe.json` (sparse, 1 row) and `aapl_seasonal_dark.json`
(legacy 3-crop backward-compat check) - all 7 runs exited 0, zero warnings,
zero console errors:

- `crop_demo_wave_viewer.waveViewer.png` - 2678x1018 (clip 1339x509 CSS px \*
  scale 2), 148,933 bytes, real chart content confirmed by eye
- `crop_demo_viewer_plus_display.viewerPlusDisplay.png` - 2678x2036, 458,426
  bytes (wave viewer + tradeDetail stats panel stacked, banner excluded)
- `crop_demo_app_no_banner.appNoBanner.png` - 3840x2036, 1,034,363 bytes (opp
  table + wave viewer + trend chart, banner excluded)
- `crop_demo_opptable_rows10.oppTable.png` (AAPL/S&P 500, 308 available rows,
  `cropRows: 10`) - 1152x892, 232,841 bytes, `actualRows: 10`, no filler
- `crop_demo_opptable_sparse.oppTable.png` (SPX PE-mode, 1 available row,
  `cropRows: 10` requested) - 1152x254, 53,874 bytes, `actualRows: 1` (all
  available rows used, correctly short, no filler)
- `100yp_opptable_july_pe.oppTable.png` (same 1-row sparse case, no
  `cropRows` - default/legacy behavior) - 1152x254, 53,441 bytes, matching
  the sparse case above almost exactly (proof the proportionality fix applies
  identically whether or not `cropRows` is set)
- `aapl_seasonal_dark.*` (legacy 3-crop spec, unchanged crop names) -
  `full` 3840x2160, `display` 2678x1008, `oppTable` 1152x1894 (308 rows, all
  included, proportional - not the old 1954px-tall-with-1-row bug shape) -
  all three crops matched their pre-change selectors/behavior exactly,
  confirming backward compatibility

Banner exclusion verified directly (not just by eye): every new crop's
recorded `clip.y` in `meta.json` is `62`, matching a direct probe of
`#main-header`'s own `getBoundingClientRect().bottom`.

No React changes were made - `web-react/src/` is untouched by this change;
everything above is `capture.js` (DOM measurement + crop/capture logic) and
this document.
