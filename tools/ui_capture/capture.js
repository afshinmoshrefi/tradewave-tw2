#!/usr/bin/env node
// =============================================================================
// TradeWave wave-viewer screenshot-capture CLI.
//
// Renders the REAL React wave-viewer (the same app users see at /app/) in
// headless Chrome, seeds its UI state deterministically, waits for real data
// to actually render (not just "the page loaded"), and captures pixel-exact
// PNG crops from a declarative JSON spec.
//
// Usage:  node capture.js <spec.json>
//
// This file is deliberately over-commented. It exists to survive a maintainer
// (human or model) who has never read the wave-viewer source and does not
// know the gotchas below. Every non-obvious line says WHY, not just WHAT.
// =============================================================================

const fs = require('fs');
const path = require('path');
const http = require('http');

// Local puppeteer install (package.json in this dir). NOTE: an earlier
// version of this tool reused the puppeteer already installed at
// /root/tw-uitools/node_modules (verified working, used by shot.js) to
// avoid a second ~300MB Chrome download - but /root is mode 700 (root-only,
// correctly so; do not weaken it) and this tool is chown'd flask:flask to
// run as the flask user, which cannot traverse into /root at all. Hence a
// local install instead: `npm install` in this directory.
const puppeteer = require('puppeteer');

// -----------------------------------------------------------------------
// Ground-truth market-group id -> display-name map.
//
// Source: config.py (single source of truth, comment there says "keys are
// permanent IDs, never renumber" - see docs/TRADEWAVE_ECOSYSTEM.md and the
// project_tw2_resource_keys_stable memory note). Verified 2026-07-09 against
// /home/flask/config.py:461-480 (available_resources dict). The React app
// gets the SAME map at runtime from GET /appserver/getResourcesObj, which
// just echoes config.available_resources - so this table cannot silently
// drift from what the app actually uses. Keys 14/15 were removed (old Korea
// markets) and are intentionally absent; do not fill the gap.
// -----------------------------------------------------------------------
const RESOURCE_GROUPS = {
  '0': 'DOW 30 STOCKS',
  '1': 'NASDAQ 100 STOCKS',
  '2': 'S&P 500 STOCKS',
  '3': 'RUSSELL 1000 STOCKS',
  '4': 'WILSHIRE 5000',
  '5': 'INDICES COMMON',
  '6': 'INDICES ALL',
  '7': 'FUTURES & COMMODITIES',
  '8': 'FOREX ALL',
  '9': 'FOREX LIQUID',
  '10': 'GOVERNMENT BONDS',
  '11': 'ETFs',
  '12': 'LONDON EXCHANGE',
  '13': 'TORONTO STOCKS',
  '16': 'CRYPTO CURRENCIES',
};
// Reverse map (display name -> numeric id) for building the ?o= deep link.
const RESOURCE_GROUP_IDS = Object.fromEntries(
  Object.entries(RESOURCE_GROUPS).map(([id, name]) => [name, id])
);

// Slide index within the lower-display Swiper (DesktopLayout.js:1504-1531).
// Order is fixed by JSX order: SeasonalChart, TradeDetail, StockLineChart.
const DISPLAY_SLIDE_INDEX = { seasonal: 0, tradeDetail: 1, price: 2 };
const SLIDE_INDEX_DISPLAY = ['seasonal', 'tradeDetail', 'price'];
const DISPLAY_BOTTOM_PANEL = {
  seasonal: { semantic: 'trend_chart', label: 'Trend Chart' },
  tradeDetail: { semantic: 'wave_stats', label: 'Wave Stats' },
  price: { semantic: 'price_chart', label: 'Price Chart' },
};

// Internal dev-only route that renders the authenticated app shell for the
// capture-bot service account (web/app.py:1718, capture_app()). Only live
// when config.tw2_env == "dev" AND only bound to 127.0.0.1:5500 - see the
// module docstring in app.py for the two-gate rationale. NEVER assume this
// exists off dev.
const INTERNAL_CAPTURE_URL = 'http://127.0.0.1:5500/internal/capture/app';
// Real app origin (nginx :80 on dev), what the browser actually navigates to.
const APP_ORIGIN = 'http://127.0.0.1';
const APP_PATH = '/app/';

function log(...args) { console.error('[capture]', ...args); }

function fail(msg) {
  console.error('[capture] FAIL:', msg);
  process.exit(1);
}

// -----------------------------------------------------------------------
// Fetch the internal capture-shell HTML server-side (node http, not the
// browser). Two uses:
//   1. Up front, to pull out the bot's UUID (window.current_user_id) so we
//      can build user-scoped localStorage keys BEFORE navigation.
//   2. Inside Chrome's request interception handler, to fulfill the browser's
//      main-document request for http://127.0.0.1/app/ - because an
//      anonymous request to /app/ redirects to WorkOS login. Fetching this
//      HTML server-side and handing it to the browser as the response body
//      keeps the browser's address bar (and therefore window.location.search,
//      which the app reads directly) on http://127.0.0.1/app/?o=... while
//      still being "logged in" as the capture bot.
// -----------------------------------------------------------------------
function fetchInternalShell() {
  return new Promise((resolve, reject) => {
    http.get(INTERNAL_CAPTURE_URL, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`internal capture route returned HTTP ${res.statusCode} (is TW2_ENV=dev? is web bound to :5500?)`));
        res.resume();
        return;
      }
      let body = '';
      res.on('data', (c) => { body += c; });
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

function extractUserId(html) {
  // window.current_user_id is JSON-escaped via json.dumps in _render_app_shell,
  // so it's a plain quoted string literal: window.current_user_id="...";
  const m = html.match(/window\.current_user_id=("(?:[^"\\]|\\.)*")/);
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch (e) { return null; }
}

function extractGlobal(html, name) {
  const re = new RegExp(`window\\.${name}=("(?:[^"\\\\]|\\\\.)*"|true|false|[0-9.]+)`);
  const m = html.match(re);
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch (e) { return m[1]; }
}

// -----------------------------------------------------------------------
// Build the ?o=base64(...) deep-link param.
// Format (App.js:2448 param_str.split('|')): fg_id|symbol|YYYY-MM-DD|daysOut|years
// years is "10" for consolidated mode, or "pe2-10" for PE-cycle mode
// (App.js:2482-2489 parses "pe" prefix + "-N" suffix).
// -----------------------------------------------------------------------
function buildDeepLink(spec) {
  if (!spec.pattern) return null;
  const groupId = RESOURCE_GROUP_IDS[spec.market];
  if (groupId === undefined) {
    fail(`spec.market "${spec.market}" is not a known resource group. Known: ${Object.keys(RESOURCE_GROUP_IDS).join(', ')}`);
  }
  const { startDate, daysOut, years, pe } = spec.pattern;
  if (!startDate || !daysOut || !years) {
    fail('spec.pattern requires startDate, daysOut, years');
  }
  const yearsField = pe ? `${pe}-${years}` : String(years);
  const paramStr = `${groupId}|${spec.symbol}|${startDate}|${daysOut}|${yearsField}`;
  const b64 = Buffer.from(paramStr, 'utf8').toString('base64');
  return { b64, paramStr };
}

// -----------------------------------------------------------------------
// Seed localStorage BEFORE any app JS runs, via page.evaluateOnNewDocument.
// Must happen per-navigation (Puppeteer re-runs evaluateOnNewDocument on
// every new document, which is what we want since we only navigate once).
//
// localStorage is user-scoped: real key = "<uuid>:<key>", JSON-encoded value
// (Common.js userScopedKey/lsGet/lsSet) - EXCEPT UITheme, which App.js reads
// via raw localStorage.getItem('UITheme') (unscoped, raw string not JSON).
// -----------------------------------------------------------------------
function buildLocalStorageSeed(uuid, spec) {
  const scoped = {};

  // tw_last_welcomed_tier: ALWAYS seed strategist/non-trial so the
  // SubscriptionWelcomeModal never pops up and steals the screenshot.
  scoped['tw_last_welcomed_tier'] = { tier: 'strategist', wasTrial: false };

  // tw_lesson_enrolled: ALWAYS seed '1'. Discovered empirically 2026-07-09:
  // the capture-bot user has a fresh (today's) created_at, so
  // isAutoArcEligible() in onboarding.js is true, and App.js:2098
  // (`if (isAutoArcEligible() && !isEnrolled() && !isTipsDismissed())`)
  // auto-enrolls it into the 7-day LessonBox onboarding arc on every load -
  // popping a "DAY 1 // LESSON" card that slides/settles into position and
  // was the actual cause of the visual-stability gate never converging (it
  // looks like a chart-animation hang but isn't). isEnrolled() just reads
  // this one localStorage flag (onboarding.js:359-360) and is the "master
  // switch" for isOnboardingArcActive() (onboarding.js:442) - seeding it
  // pre-marks the bot as already enrolled/past the arc, so LessonBox never
  // auto-pops. Not in the original spec's cookie/localStorage list; added
  // after hitting it live.
  //
  // tw_lesson_enrolled ALONE is not sufficient, though - LessonBox.js:336
  // (`if (d > lastOpened)`) auto-OPENS the box on mount any time the
  // computed onboarding day `d` is greater than the persisted
  // 'tw_lesson_lastopened' (defaults to 0 when unset), REGARDLESS of
  // enrollment state. Seed lastopened past the entire 7-day arc so the
  // "already opened today" branch (collapsed, no auto-open) is always taken.
  scoped['tw_lesson_enrolled'] = '1';
  scoped['tw_lesson_lastopened'] = 7;

  const oppTable = spec.oppTable || {};
  if (oppTable.columnVisibility) scoped['oppTableColumnVisibility'] = oppTable.columnVisibility;
  if (oppTable.columnOrder) scoped['oppTableColumnOrder'] = oppTable.columnOrder;

  const priceChart = spec.priceChart || {};
  if ('showProjection' in priceChart) scoped['showProjection'] = priceChart.showProjection;
  if ('showMaxProjection' in priceChart) scoped['showMaxProjection'] = priceChart.showMaxProjection;
  if ('projectionPeriod' in priceChart) scoped['projectionPeriod'] = String(priceChart.projectionPeriod);
  if ('showVolume' in priceChart) scoped['showVolume'] = priceChart.showVolume;
  if ('maConfig' in priceChart) scoped['maConfig'] = priceChart.maConfig;
  if ('bbConfig' in priceChart) scoped['bbConfig'] = priceChart.bbConfig;
  if ('timeframe' in priceChart) scoped['priceChartTimeframe'] = priceChart.timeframe;
  if ('chartRange' in priceChart) scoped['chartRange'] = priceChart.chartRange;
  if ('showEarnings' in priceChart) scoped['showEarnings'] = priceChart.showEarnings;

  return scoped;
}

function buildCookieSeed(spec, deepLink) {
  const cookies = [];
  const push = (name, value) => cookies.push({ name, value: String(value), url: `${APP_ORIGIN}/` });

  // WindowNumber selects the initial swiper slide (App.js:454-463 reads this
  // cookie for initialWindowNum) - but note the GOTCHA below: any querystring
  // other than ?set=on FORCES slide 2 regardless of this cookie
  // (App.js:454-459). We seed it anyway so a same-market re-render without a
  // deep link (or a future no-pattern spec) still lands correctly, and we
  // handle the forced-slide-2 case explicitly after boot (see switchSlide()).
  const wantSlideIdx = DISPLAY_SLIDE_INDEX[spec.display];
  if (wantSlideIdx === undefined) fail(`spec.display "${spec.display}" must be one of seasonal|tradeDetail|price`);
  push('WindowNumber', wantSlideIdx);
  push('BottomWindowName', DISPLAY_BOTTOM_PANEL[spec.display].semantic);

  if (spec.market) push('selectedSecurity', spec.market);
  if (deepLink && deepLink.paramStr) {
    // pe field is the 5th | separated token, lowercased 'pe...' prefix means PE mode.
    const peMode = deepLink.paramStr.split('|')[4].toLowerCase().startsWith('pe');
    push('showPEOpps', peMode ? 'true' : 'false');
  }
  push('MFE', (spec.seasonal && 'showMFE' in spec.seasonal) ? spec.seasonal.showMFE : true);
  push('MAE', (spec.seasonal && 'showMAE' in spec.seasonal) ? spec.seasonal.showMAE : true);

  if (spec.oppTable && spec.oppTable.yearsPerGroup) {
    push('oppYearsPerGroup', JSON.stringify(spec.oppTable.yearsPerGroup));
  }
  if (spec.oppTable && spec.oppTable.yearsPerGroupPE) {
    push('oppYearsPerGroupPE', JSON.stringify(spec.oppTable.yearsPerGroupPE));
  }

  // Overlay-suppression cookies - ALWAYS seed these regardless of spec so
  // welcome/onboarding/conversion modals never cover the chart under test.
  // terms_accepted's VALUE must equal the bot's own uuid (App.js:1966-1972
  // compares getCookie('terms_accepted') against the current user id, not
  // just presence) - caller fills this in after uuid is known.
  cookies.__needsUuid = true; // marker consumed by caller
  return cookies;
}

// -----------------------------------------------------------------------
// Stability gate: Chart.js draws with entry animations (bars/lines tween in
// over ~400-800ms) and the seasonal/price charts can re-layout briefly after
// first paint. Screenshotting too early captures a mid-animation frame.
// Strategy: screenshot twice, 600ms apart, byte-compare; repeat until two
// consecutive shots are identical (chart settled) or we give up.
// -----------------------------------------------------------------------
async function waitForVisualStability(page, maxTries = 10, gapMs = 600) {
  let prev = await page.screenshot({ encoding: 'binary' });
  for (let i = 0; i < maxTries; i++) {
    await new Promise((r) => setTimeout(r, gapMs));
    const cur = await page.screenshot({ encoding: 'binary' });
    if (Buffer.compare(prev, cur) === 0) return true;
    prev = cur;
  }
  return false; // caller decides whether this is fatal
}

// -----------------------------------------------------------------------
// Canvas-paint gate - see the Step 7.5 comment at the call site for the full
// story of why this exists. Reads real pixel data via getImageData() (not a
// screenshot) so it's checking exactly what the GPU/canvas backing store
// actually has, independent of Puppeteer's screenshot path entirely.
// -----------------------------------------------------------------------
const CANVAS_SELECTOR = '#right-content canvas, .opp_table_div canvas';

// clipFilter is an optional {x,y,width,height} (CSS px, viewport coords, same
// shape computeCropRect produces) - when given, only canvases whose own
// bounding box intersects that rect are checked. Omit to check every laid-out
// canvas on the page.
async function findBlankCanvases(page, selector, clipFilter) {
  return page.evaluate((sel, clip) => {
    const canvases = Array.from(document.querySelectorAll(sel));
    const blankIds = [];
    for (const c of canvases) {
      if (c.width === 0 || c.height === 0) continue; // not laid out / not painted at all yet, not our concern here
      const rect = c.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue; // hidden (e.g. an inactive swiper slide's canvas)
      if (clip) {
        const intersects = rect.left < clip.x + clip.width && rect.right > clip.x && rect.top < clip.y + clip.height && rect.bottom > clip.y;
        if (!intersects) continue;
      }
      let ctx;
      try { ctx = c.getContext('2d'); } catch (e) { continue; }
      if (!ctx) continue; // WebGL canvas or similar - can't cheaply sample, skip rather than false-positive
      try {
        // Sample a coarse grid rather than the full canvas (getImageData on
        // a full 2x/4x-scale canvas is expensive) - 20x20 points is enough
        // to distinguish "one flat fill color" from "an actual chart".
        const stepX = Math.max(1, Math.floor(c.width / 20));
        const stepY = Math.max(1, Math.floor(c.height / 20));
        const seen = new Set();
        for (let y = 0; y < c.height; y += stepY) {
          const row = ctx.getImageData(0, y, c.width, 1).data;
          for (let x = 0; x < c.width; x += stepX) {
            const i = x * 4;
            seen.add(row[i] + ',' + row[i + 1] + ',' + row[i + 2] + ',' + row[i + 3]);
          }
        }
        if (seen.size <= 1) blankIds.push(c.id || c.className || '(canvas)');
      } catch (e) {
        // getImageData can throw (tainted canvas, detached, etc.) - treat as
        // "can't verify", not "blank", to avoid false-failing on something
        // this check was never meant to cover.
        continue;
      }
    }
    return blankIds;
  }, selector, clipFilter || null);
}

async function waitForCanvasesPainted(page, maxTries = 6, gapMs = 400) {
  let stillBlank = await findBlankCanvases(page, CANVAS_SELECTOR);

  for (let i = 0; i < maxTries && stillBlank.length > 0; i++) {
    await new Promise((r) => setTimeout(r, gapMs));
    stillBlank = await findBlankCanvases(page, CANVAS_SELECTOR);
  }

  // Still blank after plain retries - nudge Chart.js's resize-triggered
  // synchronous redraw path once, then give it one more real chance. This is
  // a defensive measure for a genuine canvas-not-painted-yet case; it is
  // NOT the fix for the separate page.screenshot({clip}) capture-path bug
  // documented on captureCroppedRegion() below (that one needed a different
  // fix - software cropping - not a paint-timing nudge).
  if (stillBlank.length > 0) {
    await page.evaluate(() => window.dispatchEvent(new Event('resize')));
    await new Promise((r) => setTimeout(r, gapMs * 2));
    stillBlank = await findBlankCanvases(page, CANVAS_SELECTOR);
  }

  return { stillBlank };
}

// Quick non-blank sanity check: count distinct pixel colors by sampling a
// grid (cheap, no imagemagick dependency). A screenshot that is one solid
// color (blank panel, unrendered canvas) is almost certainly broken.
function countDistinctColorsPNG(buf) {
  // Minimal, dependency-free PNG sniff is not worth it here; instead sample
  // the raw PNG bytes themselves as a coarse proxy: real chart PNGs have
  // high byte-level entropy (many distinct byte values in the compressed
  // stream), a blank/solid-fill PNG compresses to a tiny, low-entropy blob.
  // This is intentionally crude (see acceptance-run notes for why) - it is
  // a smoke check, not a replacement for eyeballing output.
  const sampleLen = Math.min(buf.length, 200000);
  const seen = new Set();
  for (let i = 0; i < sampleLen; i++) seen.add(buf[i]);
  return seen.size;
}

async function main() {
  const specPath = process.argv[2];
  if (!specPath) fail('usage: node capture.js <spec.json>');
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  if (spec.spec_version !== 1) fail(`unsupported spec_version ${spec.spec_version}, expected 1`);

  const startWall = Date.now();
  const consoleErrors = [];
  const warnings = [];

  // ---- Step 1: internal shell fetch (uuid + sanity) ----
  log('fetching internal capture shell for bot identity...');
  const shellHtml = await fetchInternalShell();
  const uuid = extractUserId(shellHtml);
  if (!uuid) fail('could not extract window.current_user_id from internal capture route response');
  const ltk = extractGlobal(shellHtml, 'ltk');
  const tier = extractGlobal(shellHtml, 'tw2_user_tier');
  if (!ltk) fail('window.ltk missing from capture shell - capture-bot user may be misconfigured');
  if (tier !== 'strategist') warnings.push(`expected capture-bot tier "strategist", got "${JSON.stringify(tier)}"`);
  log(`bot uuid=${uuid} tier=${tier}`);

  // ---- Step 2: build deep link + storage/cookie seeds ----
  const deepLink = buildDeepLink(spec);
  const lsSeed = buildLocalStorageSeed(uuid, spec);
  const cookieSeed = buildCookieSeed(spec, deepLink);

  const overlayCookies = [
    { name: 'terms_accepted', value: uuid, url: `${APP_ORIGIN}/` },
    { name: 'first1', value: '1', url: `${APP_ORIGIN}/` },
    { name: `tw_onboard_dismissed_${uuid}`, value: '1', url: `${APP_ORIGIN}/` },
    { name: `tw_conversion_shown_${uuid}`, value: '1', url: `${APP_ORIGIN}/` },
  ];
  const allCookies = [...cookieSeed, ...overlayCookies];

  // ---- Step 3: launch Chrome ----
  const scale = spec.scale || 2;
  const viewport = spec.viewport || { width: 1920, height: 1080 };
  log(`launching Chrome, viewport=${viewport.width}x${viewport.height} scale=${scale}`);
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb'],
  });

  let exitCode = 0;
  try {
    const page = await browser.newPage();
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push('pageerror: ' + err.message));

    await page.setViewport({ width: viewport.width, height: viewport.height, deviceScaleFactor: scale });

    // Seed localStorage before ANY page script runs. evaluateOnNewDocument
    // needs to run in the page's own origin context, which is why this can't
    // happen before goto() via some other mechanism - Puppeteer injects this
    // script to run at document-start on every subsequent navigation.
    await page.evaluateOnNewDocument((uuid, theme, lsSeed) => {
      try {
        localStorage.setItem('UITheme', theme); // unscoped, raw string - NOT JSON-encoded
        // tw_notifybell_seen: ALSO unscoped/raw (SeasonalBarChart.js:1657-1659
        // reads it via plain window.localStorage.getItem, not the userScopedKey
        // helper - inconsistent with the rest of the app but that's what's
        // there). Gates the "Remind me" bell's one-time attention pulse
        // (.tw-notify-pulse, App.css: `animation: twNotifyPulse 2s ease-in-out
        // infinite`). Discovered empirically 2026-07-09: an INFINITE CSS
        // animation can never produce two byte-identical screenshots, so it
        // was silently defeating the visual-stability gate (looked like
        // "chart never settles" but was actually a permanently-pulsing bell
        // icon in the top control bar). Any non-empty value suppresses it.
        localStorage.setItem('tw_notifybell_seen', '1');
        // tw_symbolbox_seen: same "one-time first-visit pulse" pattern as the
        // notify bell above, same unscoped/raw key style, same infinite CSS
        // animation problem (.tw-symbol-pulse -> twSymbolPulse 2s infinite,
        // TextBox.js:9,24-26 SYMBOL_SEEN_KEY). Gates the pulse on the AAPL/
        // symbol input pill in the top control bar. Found the same way as
        // notifybell: it was the last remaining region defeating the
        // stability gate after the other two fixes.
        localStorage.setItem('tw_symbolbox_seen', '1');
        for (const [k, v] of Object.entries(lsSeed)) {
          localStorage.setItem(uuid + ':' + k, JSON.stringify(v));
        }
      } catch (e) { /* localStorage may be unavailable pre-navigation in edge cases; ignore */ }
    }, uuid, spec.theme || 'dark', lsSeed);

    // Cookies must be set via page.setCookie (evaluateOnNewDocument cookies
    // would need document.cookie writes, which can't run before navigation
    // reliably either) - setCookie works pre-navigation because it talks to
    // the CDP Network domain directly, not page JS.
    await page.setCookie(...allCookies);

    // ---- Step 4: request interception for the auth bypass ----
    // Anonymous requests to http://127.0.0.1/app/ redirect to WorkOS login.
    // We intercept ONLY the main document request and fulfill it with the
    // server-side-fetched capture-shell HTML (re-fetched fresh per capture,
    // not the Step-1 copy, in case ltk/globals are time-sensitive). All other
    // requests (JS/CSS/XHR/etc.) continue() untouched so the app's own asset
    // loading and API calls behave exactly as in a real browser session.
    await page.setRequestInterception(true);
    page.on('request', async (req) => {
      const isMainDoc = req.isNavigationRequest() && req.frame() === page.mainFrame();
      const url = req.url();
      if (isMainDoc && (url === `${APP_ORIGIN}${APP_PATH}` || url.startsWith(`${APP_ORIGIN}${APP_PATH}?`))) {
        try {
          const html = await fetchInternalShell();
          req.respond({ status: 200, contentType: 'text/html; charset=utf-8', body: html });
        } catch (e) {
          req.abort('failed');
        }
        return;
      }
      req.continue();
    });

    // ---- Step 5: navigate ----
    // Browser URL stays on the REAL origin (127.0.0.1/app/) so React reads
    // location.search normally; only the document BODY is swapped server-side
    // via interception above.
    //
    // Querystring choice: if spec.pattern is set, use ?o=<b64> (deep link).
    // If not, use ?set=on - this is the ONE querystring value App.js
    // special-cases (App.js:2421) to NOT trigger the "any non-set=on
    // querystring forces slide 2" behavior (App.js:454-459) and to NOT
    // attempt ?o= base64 decoding. Using no querystring at all also avoids
    // the slide-2 force, but ?set=on is what the app's own settings-deep-link
    // convention uses, so we prefer it for consistency / documentation value.
    const qs = deepLink ? `?o=${deepLink.b64}` : '?set=on';
    const targetUrl = `${APP_ORIGIN}${APP_PATH}${qs}`;
    log(`navigating to ${targetUrl}${deepLink ? ` (decoded: ${deepLink.paramStr})` : ' (no pattern in spec)'}`);
    await page.goto(targetUrl, { waitUntil: 'networkidle2', timeout: 60000 });

    // ---- Step 6: wait for opp table data, then deep-link application ----
    log('waiting for __twCapture.ready.oppTable...');
    await page.waitForFunction(
      () => window.__twCapture && window.__twCapture.ready && window.__twCapture.ready.oppTable === true,
      { timeout: 60000 }
    ).catch(() => fail('timed out waiting for __twCapture.ready.oppTable - opp table never rendered non-empty data. Console errors: ' + JSON.stringify(consoleErrors)));

    if (deepLink) {
      log(`waiting for deep link to apply (meta.seasonal.symbol === "${spec.symbol}")...`);
      await page.waitForFunction(
        (sym) => window.__twCapture && window.__twCapture.meta && window.__twCapture.meta.seasonal && window.__twCapture.meta.seasonal.symbol === sym,
        { timeout: 60000 },
        spec.symbol
      ).catch(() => fail(`timed out waiting for deep link to apply for symbol "${spec.symbol}". Console errors: ` + JSON.stringify(consoleErrors)));
    }

    // ---- Step 7: select the requested semantic panel ----
    // AI Scores is inserted only for eligible U.S. stock/ETF markets, so Price
    // Chart can be numeric index 2 or 3. Use the visible labeled tab instead of
    // encoding either index in capture automation.
    await selectBottomPanel(page, DISPLAY_BOTTOM_PANEL[spec.display].label, consoleErrors);

    // Wait for the target display's own ready flag (may already be true).
    const readyFlagName = spec.display; // 'seasonal' | 'tradeDetail' | 'price'
    log(`waiting for __twCapture.ready.${readyFlagName}...`);
    await page.waitForFunction(
      (name) => window.__twCapture && window.__twCapture.ready && window.__twCapture.ready[name] === true,
      { timeout: 60000 },
      readyFlagName
    ).catch(() => fail(`timed out waiting for __twCapture.ready.${readyFlagName} after slide switch. Console errors: ` + JSON.stringify(consoleErrors)));

    // Slide 0 (seasonal) renders TWO independently-fetched things: the bar
    // chart itself ('seasonal', waited above) and the lower trend-line chart
    // ('trendChart', a separate fetch in SeasonalBarChart.js that feeds
    // SeasonalChart.js). 'seasonal' going true does NOT guarantee the trend
    // chart has painted - on a cold/slow load this previously let a blank
    // trend-chart pane slip through as a "stable" capture. Wait on it too,
    // generous timeout since cold deep-window fetches are slow.
    if (spec.display === 'seasonal') {
      log('waiting for __twCapture.ready.trendChart...');
      await page.waitForFunction(
        () => window.__twCapture && window.__twCapture.ready && window.__twCapture.ready.trendChart === true,
        { timeout: 60000 }
      ).catch(() => fail('timed out waiting for __twCapture.ready.trendChart after slide switch. Console errors: ' + JSON.stringify(consoleErrors)));
    }

    // ---- Step 7.5: canvas-paint gate ----
    // Discovered empirically 2026-07-09 while building the crop feature below:
    // Chart.js canvases (BarChart.js/SeasonalChart.js/StockLineChart.js's
    // LineChart, all react-chartjs-2) can go through their whole ready-flag
    // lifecycle (markCaptureReady fires with a real, non-zero `points`/`rows`
    // count - the DATA is genuinely there) while the <canvas> ITSELF still
    // paints fully blank - a real, reproducible headless-Chrome/Chart.js race
    // that is INDEPENDENT of the ready-flags and stability gate below (two
    // blank frames 600ms apart byte-compare as "stable" just fine). This is
    // NOT a clip-vs-full-screenshot artifact - it reproduces identically in
    // full-page screenshots taken the normal way, so it predates and is
    // unrelated to the crop feature; it's just far MORE consequential now
    // that a crop like "waveViewer" can be ~100% canvas with none of the
    // surrounding UI chrome that used to dilute the old byte-entropy sanity
    // check (Step 10) enough to mask a blank chart.
    //
    // Fix: before the stability gate, read real pixel data (getImageData) out
    // of every <canvas> currently laid out on the page and confirm each one
    // isn't a single flat color (an empty/never-painted canvas, or one that's
    // painted only its own background fill). Retry with a short wait; if
    // still blank, nudge Chart.js's own resize-triggered redraw path via a
    // synthetic window 'resize' event (Chart.js redraws synchronously on
    // resize) and wait once more. This is a real, verified mitigation - see
    // docs/UI_CAPTURE_PIPELINE.md's crop section for the empirical A/B that
    // found it (a plain extra rAF/timeout wait alone did NOT fix it; the
    // resize nudge did).
    log('waiting for chart canvases to actually paint (not just report ready)...');
    const canvasPaint = await waitForCanvasesPainted(page);
    if (canvasPaint.stillBlank.length > 0) {
      warnings.push(`${canvasPaint.stillBlank.length} canvas(es) still blank after paint-gate retries (resize nudge did not help): ${canvasPaint.stillBlank.join(', ')} - crops covering this region may capture an empty chart`);
    }

    // ---- Step 8: stability gate ----
    log('waiting for visual stability (chart entry animations to settle)...');
    const stable = await waitForVisualStability(page);
    if (!stable) warnings.push('visual stability gate did not converge after max tries; capturing anyway (chart may still be mid-animation)');

    // ---- Step 9: capture crops ----
    const outPrefix = spec.out || 'out/capture';
    const outDir = path.dirname(outPrefix);
    fs.mkdirSync(outDir, { recursive: true });

    const crops = spec.crops && spec.crops.length ? spec.crops : ['full'];
    const written = [];
    for (const crop of crops) {
      const outPath = `${outPrefix}.${crop}.png`;
      if (crop === 'full') {
        // Full-page crop keeps #main-header (the 1% case where the banner is
        // wanted) - this is the one crop that intentionally does NOT exclude it.
        await page.screenshot({ path: outPath });
        const buf = fs.readFileSync(outPath);
        written.push({ crop, path: outPath, bytes: buf.length });
        continue;
      }

      const cropRows = (crop === 'oppTable' && spec.oppTable && Number.isInteger(spec.oppTable.cropRows))
        ? spec.oppTable.cropRows
        : null;

      const result = await computeCropRect(page, crop, cropRows, viewport);
      if (result.error) fail(result.error);
      if (result.clip.width <= 0 || result.clip.height <= 0) {
        fail(`crop "${crop}" resolved to a zero-size clip rect (${JSON.stringify(result.clip)}) - selector matched but the element is not visible/laid-out, or is fully clamped outside the viewport`);
      }

      // Canvas-paint check + retry BEFORE capturing, so we don't waste a
      // capture attempt on a chart that's still mid-remount. See the long
      // comment on captureCroppedRegion() below for why the capture itself
      // is done via software crop rather than page.screenshot({clip}), and
      // docs/UI_CAPTURE_PIPELINE.md for the full empirical story of both
      // bugs this section works around.
      const CANVAS_RETRY_MAX = 5;
      const CANVAS_RETRY_GAP_MS = 800;
      let blank = await findBlankCanvases(page, CANVAS_SELECTOR, result.clip);
      for (let attempt = 1; attempt <= CANVAS_RETRY_MAX && blank.length > 0; attempt++) {
        log(`crop "${crop}" attempt ${attempt}/${CANVAS_RETRY_MAX}: ${blank.length} canvas(es) blank before capture (${blank.join(', ')}) - waiting and retrying...`);
        await new Promise((r) => setTimeout(r, CANVAS_RETRY_GAP_MS));
        blank = await findBlankCanvases(page, CANVAS_SELECTOR, result.clip);
      }
      if (blank.length > 0) {
        fail(`crop "${crop}" still has ${blank.length} blank canvas(es) after ${CANVAS_RETRY_MAX} retries (${blank.join(', ')}) - this is the known Chart.js remount race (a component re-fetches and remounts its <canvas> after its own ready flag already fired once; see docs/UI_CAPTURE_PIPELINE.md); re-running the whole capture is the normal remedy`);
      }

      await captureCroppedRegion(page, outPath, result.clip, scale);

      const buf = fs.readFileSync(outPath);
      written.push({
        crop,
        path: outPath,
        bytes: buf.length,
        clip: result.clip,
        ...(result.actualRows !== undefined ? { actualRows: result.actualRows } : {}),
      });

    }

    // ---- Step 10: sanity checks (fail fast, no silent fallback) ----
    log('running sanity checks...');
    const twCapture = await page.evaluate(() => window.__twCapture || null);
    if (!twCapture) fail('window.__twCapture missing at capture time');

    for (const flag of ['oppTable', 'seasonal', 'price', 'tradeDetail', 'trendChart']) {
      if (twCapture.ready[flag] !== true) {
        warnings.push(`ready.${flag} is not true at capture time (${JSON.stringify(twCapture.ready[flag])}) - only expected for slides never visited`);
      }
    }
    if (!twCapture.meta.oppTable || !(twCapture.meta.oppTable.rows > 0)) {
      fail(`sanity check failed: meta.oppTable.rows is not > 0 (got ${JSON.stringify(twCapture.meta.oppTable)})`);
    }

    for (const w of written) {
      if (w.bytes <= 20000) {
        fail(`sanity check failed: ${w.path} is only ${w.bytes} bytes (<=20KB threshold - likely blank/broken render)`);
      }
      const buf = fs.readFileSync(w.path);
      const distinctBytes = countDistinctColorsPNG(buf);
      if (distinctBytes < 20) {
        fail(`sanity check failed: ${w.path} has suspiciously low byte-value entropy (${distinctBytes} distinct byte values sampled) - likely a solid-color/blank image`);
      }
    }

    const fullWritten = written.find((w) => w.crop === 'full');
    if (fullWritten) {
      const dims = await getPNGDimensions(fullWritten.path);
      const expectedW = viewport.width * scale;
      const expectedH = viewport.height * scale;
      if (dims.width !== expectedW || dims.height !== expectedH) {
        fail(`sanity check failed: full screenshot is ${dims.width}x${dims.height}, expected ${expectedW}x${expectedH} (viewport ${viewport.width}x${viewport.height} * scale ${scale})`);
      }
    }

    // ---- Step 11: metadata sidecar ----
    const bundleHash = await page.evaluate(() => {
      const scripts = Array.from(document.querySelectorAll('script[src*="/app/static/js/main."]'));
      if (scripts.length === 0) return null;
      const m = scripts[0].src.match(/main\.([a-f0-9]+)\.js/);
      return m ? m[1] : null;
    });

    const metaOut = {
      spec,
      resolved: {
        deep_link_o: deepLink ? deepLink.b64 : null,
        deep_link_decoded: deepLink ? deepLink.paramStr : null,
        querystring_used: qs,
      },
      bot_uuid: uuid,
      bundle_hash: bundleHash,
      capture_meta_snapshot: twCapture.meta,
      files: written,
      warnings,
      console_errors: consoleErrors,
      wall_time_ms: Date.now() - startWall,
      captured_at: new Date().toISOString(),
    };
    fs.writeFileSync(`${outPrefix}.meta.json`, JSON.stringify(metaOut, null, 2));
    log(`wrote ${outPrefix}.meta.json`);

    if (warnings.length) {
      log('WARNINGS:', warnings.join(' | '));
    }
    log(`done in ${metaOut.wall_time_ms}ms - ${written.length} crop(s) written`);
  } catch (e) {
    console.error('[capture] FAIL:', e.message);
    exitCode = 1;
  } finally {
    await browser.close();
  }
  process.exit(exitCode);
}

// -----------------------------------------------------------------------
// Programmatically switch the lower-display Swiper slide.
//
// The swiper instance itself is NOT exposed on window (props.setSwiper only
// stores it in React state - see App.js:82,1381 and DesktopLayout.js:1505).
// So we drive it the same way a real user would: click the Swiper nav
// arrows. Swiper 6 (package.json pins "swiper": "^6.7.0") with
// navigation={true} (DesktopLayout.js:1506) renders standard
// .swiper-button-next / .swiper-button-prev elements inside the swiper
// container - these are the stable, version-guaranteed click targets.
// -----------------------------------------------------------------------
async function switchSlide(page, fromIdx, toIdx, consoleErrors) {
  const delta = toIdx - fromIdx;
  const selector = delta > 0 ? '.stock-linechart-parent .swiper-button-next' : '.stock-linechart-parent .swiper-button-prev';
  const clicks = Math.abs(delta);
  for (let i = 0; i < clicks; i++) {
    const btn = await page.$(selector);
    if (!btn) fail(`swiper nav button "${selector}" not found - cannot switch slide (Swiper markup may have changed)`);
    await btn.click();
    await new Promise((r) => setTimeout(r, 300)); // let the slide transition animate before the next click registers correctly
  }
  const flagForIdx = SLIDE_INDEX_DISPLAY[toIdx];
  await page.waitForFunction(
    (name) => window.__twCapture && window.__twCapture.ready && window.__twCapture.ready[name] === true,
    { timeout: 30000 },
    flagForIdx
  ).catch(() => fail(`switched swiper to slide ${toIdx} but ready.${flagForIdx} never went true. Console errors: ` + JSON.stringify(consoleErrors)));

  // Slide 0 (seasonal) also needs its separately-fetched trend chart ready -
  // see the matching comment at the main post-slide-switch wait above.
  if (flagForIdx === 'seasonal') {
    await page.waitForFunction(
      () => window.__twCapture && window.__twCapture.ready && window.__twCapture.ready.trendChart === true,
      { timeout: 30000 }
    ).catch(() => fail(`switched swiper to slide ${toIdx} but ready.trendChart never went true. Console errors: ` + JSON.stringify(consoleErrors)));
  }
}

async function selectBottomPanel(page, label, consoleErrors) {
  const clicked = await page.evaluate((targetLabel) => {
    const tabs = Array.from(document.querySelectorAll('.bottom-panel-tabs [role="tab"]'));
    const tab = tabs.find(item => item.textContent.trim() === targetLabel);
    if (!tab) return false;
    tab.click();
    return true;
  }, label);
  if (!clicked) fail(`bottom panel tab "${label}" not found - lower navigation may have changed`);
  await page.waitForFunction(
    (targetLabel) => Array.from(document.querySelectorAll('.bottom-panel-tabs [role="tab"]'))
      .some(item => item.textContent.trim() === targetLabel && item.getAttribute('aria-selected') === 'true'),
    { timeout: 30000 },
    label
  ).catch(() => fail(`bottom panel "${label}" did not become active. Console errors: ` + JSON.stringify(consoleErrors)));
  await new Promise((resolve) => setTimeout(resolve, 300));
}

// -----------------------------------------------------------------------
// Crop-rect computation (spec_version 1, additive).
//
// All crops below except 'full' are computed as an explicit clip rect (CSS
// px, viewport-relative) via page.evaluate() DOM measurement, then captured
// with page.screenshot({clip}) - NOT element.screenshot(). This matters for
// composite regions (waveViewer, viewerPlusDisplay, appNoBanner) that need
// to EXCLUDE a sibling (#main-header) that sits outside the element's own
// box in the DOM tree; element.screenshot() always captures that element's
// own full box and offers no way to carve a sub-region out of it, whereas an
// explicit clip rect can start anywhere the DOM says to. Using clip rects
// uniformly (even for the simple single-element crops) keeps one code path
// instead of two, and makes the oppTable cropRows math (which inherently
// needs a computed height, not a whole element) fall out naturally.
//
// IMPORTANT: getBoundingClientRect() returns CSS px in VIEWPORT coordinates
// (i.e. already relative to the current scroll position, and NOT scaled by
// deviceScaleFactor). page.screenshot({clip}) also takes CSS px in viewport
// coordinates - Puppeteer/Chrome multiplies by deviceScaleFactor internally
// to produce the final PNG pixel dimensions. So clip math here must stay in
// plain CSS px throughout; do not manually multiply by `scale` anywhere in
// this function - that would double-scale and produce a wrong crop.
//
// Selectors depended on (see docs/UI_CAPTURE_PIPELINE.md "Change Management"
// - if any of these rename, this function and that doc must be updated
// together):
//   #main-header                    - App.js / web/app.py capture_app() shell (site banner, excluded from every crop below)
//   #right-content                  - DesktopLayout.js right-column wrapper (parent of the two panes below)
//   .seasonal-barchart-parent       - DesktopLayout.js wave-viewer pane (SeasonalBarChart's chart + its own control header)
//   .stock-linechart-parent         - DesktopLayout.js lower-display swiper pane (seasonal/tradeDetail/price)
//   .opp_table_div                  - DesktopLayout.js opp-table + chatbot outer pane
//   .opp-container .opp-table-controls   - OppTable.js PE/month/day/years controls row (top of the oppTable crop)
//   .opp-container .opp-table table.table-striped tbody tr  - OppTable.js -> TableBox.js data rows
async function computeCropRect(page, crop, cropRows, viewport) {
  return page.evaluate((cropName, cropRowsArg, vw, vh) => {
    // Clamp a rect to the viewport (0,0)-(vw,vh) - never emit a negative-size
    // or off-viewport clip, which Chrome's page.screenshot({clip}) rejects.
    const clamp = (r) => {
      const left = Math.max(0, r.left);
      const top = Math.max(0, r.top);
      const right = Math.min(vw, r.left + r.width);
      const bottom = Math.min(vh, r.top + r.height);
      return { x: Math.round(left), y: Math.round(top), width: Math.round(Math.max(0, right - left)), height: Math.round(Math.max(0, bottom - top)) };
    };
    const rectOf = (el) => {
      const r = el.getBoundingClientRect();
      return { left: r.left, top: r.top, width: r.width, height: r.height };
    };
    const byClass = (sel) => document.querySelector(sel);

    if (cropName === 'waveViewer') {
      const el = byClass('.seasonal-barchart-parent');
      if (!el) return { error: 'crop "waveViewer" requested but .seasonal-barchart-parent not found in DOM' };
      return { clip: clamp(rectOf(el)) };
    }

    if (cropName === 'viewerPlusDisplay') {
      const el = document.getElementById('right-content');
      if (!el) return { error: 'crop "viewerPlusDisplay" requested but #right-content not found in DOM' };
      return { clip: clamp(rectOf(el)) };
    }

    if (cropName === 'appNoBanner') {
      // #root is the real React mount point in the raw HTML shell
      // (web-react/public/index.html) - #main-header is a SIBLING of #root,
      // not an ancestor/descendant, so #root's own box is already
      // "everything below the banner" with no further math needed.
      const el = document.getElementById('root');
      if (!el) return { error: 'crop "appNoBanner" requested but #root not found in DOM' };
      return { clip: clamp(rectOf(el)) };
    }

    if (cropName === 'display') {
      const el = byClass('.stock-linechart-parent');
      if (!el) return { error: 'crop "display" requested but .stock-linechart-parent not found in DOM' };
      return { clip: clamp(rectOf(el)) };
    }

    if (cropName === 'oppTable') {
      // Controls row: OppTable.js <div className='opp-table-controls'> - the
      // PE/month/day/years row is the top of this crop (matches the owner's
      // request; NOT .opp_table_div's own top, which would include nothing
      // extra here since opp-table-controls IS the first child, but we
      // measure it explicitly rather than assume DOM order stays that way).
      const controlsEl = byClass('.opp-container .opp-table-controls');
      if (!controlsEl) return { error: 'crop "oppTable" requested but .opp-container .opp-table-controls not found in DOM' };

      // Data rows: OppTable.js -> TableBox.js <table class="table-striped"><tbody><tr>.
      // The rows live inside .opp-table, a fixed-height (oppTableHeight)
      // overflow-y:auto scroll pane (OppTable.css) - this is the root cause
      // of the old bug (a 1-row table still produced a full pane-height PNG,
      // since element.screenshot() captured .opp_table_div's whole fixed box
      // regardless of content). We instead measure real row boxes and size
      // the crop to their actual bottom edge.
      const rows = Array.from(document.querySelectorAll('.opp-container .opp-table table.table-striped tbody tr'));
      if (rows.length === 0) return { error: 'crop "oppTable" requested but no rows found in .opp-container .opp-table table.table-striped tbody' };

      const wantRows = (cropRowsArg && cropRowsArg > 0) ? Math.min(cropRowsArg, rows.length) : rows.length;
      const lastRow = rows[wantRows - 1];

      const top = rectOf(controlsEl).top;
      const controlsLeft = rectOf(controlsEl).left;
      const controlsRight = controlsLeft + rectOf(controlsEl).width;
      const lastRowRect = rectOf(lastRow);

      // Bottom is clamped to the scroll pane's OWN visible viewport
      // (.opp-table's clientRect), not just the row's raw bottom - if the
      // requested row lies past what's currently scrolled into view, the row
      // itself isn't actually on screen to capture. The harness always
      // starts a fresh, unscrolled render, so in practice the pane is
      // scrolled to top and this only matters if a future spec ever seeds a
      // non-zero scroll position.
      const paneEl = byClass('.opp-container .opp-table');
      const paneRect = paneEl ? rectOf(paneEl) : null;
      let bottom = lastRowRect.top + lastRowRect.height;
      if (paneRect) bottom = Math.min(bottom, paneRect.top + paneRect.height);

      // Width: span the controls row's own width (same left/right edges the
      // pane itself uses), not just the table's (which can be narrower than
      // its container, or wider with horizontal scroll - overflow-x:auto).
      const left = controlsLeft;
      const width = controlsRight - controlsLeft;

      return {
        clip: clamp({ left, top, width, height: Math.max(0, bottom - top) }),
        actualRows: wantRows,
      };
    }

    return { error: `unknown crop "${cropName}" - expected one of: full, waveViewer, viewerPlusDisplay, appNoBanner, display, oppTable` };
  }, crop, cropRows, viewport.width, viewport.height);
}

// -----------------------------------------------------------------------
// Software crop: take a full-page (unclipped) screenshot, then crop it to
// the requested rect INSIDE the page via an offscreen <canvas> (drawImage +
// toDataURL), instead of using Puppeteer's page.screenshot({clip}).
//
// Why not page.screenshot({clip}) - a real, empirically-verified Puppeteer/
// Chrome bug in THIS environment, not a theoretical concern: page.screenshot
// with a clip rect over a region containing a Chart.js <canvas> can silently
// write a PNG with BLANK canvas content, even at the exact moment
// getImageData() on that same canvas (read directly, no screenshot involved)
// proves the canvas's own backing store has real, fully-painted pixels. This
// was isolated with a controlled A/B: same page state, same instant -
// page.screenshot({clip}) -> blank chart; software-crop-the-full-page ->
// correct chart, every time. It reproduces across different specs/patterns
// and is NOT a timing/animation-settle issue (the stability gate and a
// canvas-paint gate both already ran and reported everything settled/
// painted before this was tried) - it is specifically the clip-screenshot
// capture path that desyncs from the GPU-composited canvas content at 2x/4x
// deviceScaleFactor. A plain full-page page.screenshot() (used for the
// "full" crop, and used as the source image here) does NOT exhibit this bug.
//
// clip is CSS px (viewport coords, same shape computeCropRect produces);
// scale is deviceScaleFactor - the source screenshot and the crop math both
// need it to end up with correctly-sized final PNG pixels, matching exactly
// what page.screenshot({clip}) would have produced dimensionally.
// -----------------------------------------------------------------------
async function captureCroppedRegion(page, outPath, clip, scale) {
  const fullB64 = await page.screenshot({ encoding: 'base64' });
  const croppedB64 = await page.evaluate(async (fullB64, clip, scale) => {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error('offscreen crop <img> failed to load the full-page screenshot data URL'));
      img.src = 'data:image/png;base64,' + fullB64;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(clip.width * scale);
    canvas.height = Math.round(clip.height * scale);
    const ctx = canvas.getContext('2d');
    ctx.drawImage(
      img,
      Math.round(clip.x * scale), Math.round(clip.y * scale), Math.round(clip.width * scale), Math.round(clip.height * scale),
      0, 0, Math.round(clip.width * scale), Math.round(clip.height * scale)
    );
    return canvas.toDataURL('image/png').replace(/^data:image\/png;base64,/, '');
  }, fullB64, clip, scale);
  fs.writeFileSync(outPath, Buffer.from(croppedB64, 'base64'));
}

// Minimal PNG dimension reader (IHDR chunk is always the first chunk,
// width/height are big-endian uint32 at fixed offsets) - avoids pulling in
// an image-parsing dependency for one field.
async function getPNGDimensions(filePath) {
  const buf = fs.readFileSync(filePath);
  // PNG signature (8 bytes) + IHDR chunk length(4) + type(4) = offset 16 for width
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  return { width, height };
}

main().catch((e) => {
  console.error('[capture] FAIL (uncaught):', e.stack || e.message);
  process.exit(1);
});
