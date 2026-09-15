// Browser checks for TW-BUG-0001 (mobile rotation) and TW-BUG-0002 (right-edge resize).
// Based on Codex's audit harness (/var/tmp/trend-chart-audit-20260915/audit-*.cjs).
// Usage: node verify-bugs.cjs --mode rotate|landscape|resize --out DIR [--build BUILD_DIR]
// --build serves a candidate React build to this disposable browser only; without it the
// live dev bundle is exercised.
const fs = require('fs');
const path = require('path');
const http = require('http');
const puppeteer = require('/home/flask/tools/ui_capture/node_modules/puppeteer');

const arg = name => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : undefined; };
const mode = arg('--mode');
const out = arg('--out');
const build = arg('--build');
fs.mkdirSync(out, { recursive: true });

const get = url => new Promise((resolve, reject) => http.get(url, r => {
  let body = ''; r.on('data', d => body += d);
  r.on('end', () => r.statusCode === 200 ? resolve(body) : reject(Error('HTTP ' + r.statusCode)));
}).on('error', reject));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const redact = s => String(s).replace(/token=[^ &\s"]+/g, 'token=REDACTED');
const increment = (date, days) => { const v = new Date(date + 'T12:00:00Z'); v.setUTCDate(v.getUTCDate() + days); return v.toISOString().slice(0, 10); };
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.map': 'application/json', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.gif': 'image/gif', '.jpg': 'image/jpeg' };

(async () => {
  let html = await get('http://127.0.0.1:5500/internal/capture/app');
  const uuid = JSON.parse(html.match(/window\.current_user_id=("(?:[^"\\]|\\.)*")/)[1]);
  if (build) {
    const index = fs.readFileSync(path.join(build, 'index.html'), 'utf8');
    const js = index.match(/static\/js\/main\.[^"]+\.js/)[0];
    const css = index.match(/static\/css\/main\.[^"]+\.css/)[0];
    html = html.replace(/static\/js\/main\.[^"]+\.js/, js).replace(/static\/css\/main\.[^"]+\.css/, css);
  }
  const mobile = mode === 'rotate' || mode === 'landscape' || mode === 'touch';
  const landscapeStart = mode === 'landscape';
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const receipt = { mode, build: build || 'live dev', cases: [], errors: [], consoleErrors: [], responses: [], execution_complete: false };
  const save = () => fs.writeFileSync(path.join(out, 'receipt.json'), JSON.stringify(receipt, null, 2));
  try {
    const page = await browser.newPage();
    if (mobile) {
      await page.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1');
      await page.setViewport({ width: landscapeStart ? 844 : 390, height: landscapeStart ? 390 : 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    } else {
      await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
    }
    await page.emulateTimezone('America/New_York');
    page.on('console', m => { if (m.type() === 'error') receipt.consoleErrors.push(redact(m.text()).slice(0, 500)); });
    page.on('pageerror', e => receipt.errors.push(redact(e.message)));
    page.on('response', async response => {
      const pathname = new URL(response.url()).pathname;
      if (pathname.includes('/consolidated_seasonal_chart2/')) {
        try { receipt.responses.push({ status: response.status(), request: (await response.json()).request }); } catch {}
      }
    });
    await page.evaluateOnNewDocument(id => {
      localStorage.setItem('UITheme', 'dark');
      localStorage.setItem('tw_notifybell_seen', '1');
      localStorage.setItem('tw_symbolbox_seen', '1');
      for (const [k, v] of Object.entries({ tw_last_welcomed_tier: { tier: 'strategist', wasTrial: false }, tw_lesson_enrolled: '1', tw_lesson_lastopened: 7, tw_getting_started_video_seen_v2: true, showMaxProjection: false })) {
        localStorage.setItem(id + ':' + k, JSON.stringify(v));
      }
    }, uuid);
    await page.setCookie(...Object.entries({ terms_accepted: uuid, first1: '1', ['tw_onboard_dismissed_' + uuid]: '1', ['tw_conversion_shown_' + uuid]: '1', WindowNumber: '0', BottomWindowName: 'trend_chart', selectedSecurity: 'S&P 500 STOCKS', showPEOpps: 'false' }).map(([name, value]) => ({ name, value, url: 'http://127.0.0.1/' })));
    await page.setRequestInterception(true);
    page.on('request', request => {
      const url = new URL(request.url());
      if (request.isNavigationRequest() && request.frame() === page.mainFrame() && url.pathname === '/app/') return request.respond({ status: 200, contentType: 'text/html', body: html });
      if (build && url.hostname === '127.0.0.1' && url.pathname.startsWith('/app/static/')) {
        const file = path.join(build, url.pathname.slice('/app/'.length));
        if (file.startsWith(build) && fs.existsSync(file)) {
          return request.respond({ status: 200, contentType: TYPES[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file) });
        }
      }
      request.continue();
    });
    await page.goto('http://127.0.0.1/app/?o=' + Buffer.from(arg('--o') || '2|AAPL|2026-01-01|366|10').toString('base64'), { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForFunction(() => window.__twCapture?.ready?.trendChart, { timeout: 20000 }).catch(e => { receipt.initialWait = e.message; });
    await sleep(1500);

    await page.evaluate(() => {
      const root = () => document.getElementById('root')._reactRootContainer._internalRoot.current;
      const walk = test => { const stack = [root()]; while (stack.length) { const f = stack.pop(); if (test(f)) return f; if (f.child) stack.push(f.child); if (f.sibling) stack.push(f.sibling); } };
      window.findTrend = () => {
        const fiber = walk(f => f.memoizedProps?.chartTitle === 'Seasonal Chart' && f.memoizedProps?.SetJanDecDateRange);
        if (!fiber) return null;
        const hooks = []; let h = fiber.memoizedState; while (h) { hooks.push(h.memoizedState); h = h.next; }
        return { props: fiber.memoizedProps, chart: hooks.find(v => v?.current?.scales?.x)?.current };
      };
      window.findBoundary = name => walk(f => f.memoizedProps?.name === name && f.stateNode?.setState)?.stateNode;
      window.viewerState = () => {
        const t = window.findTrend();
        const errorPanels = [...document.querySelectorAll('body *')].filter(e => e.children.length === 0 && /encountered an error/i.test(e.textContent)).map(e => e.textContent.trim());
        const swiper = t?.props?.swiper;
        const base = {
          layout: document.querySelector('.app-container-l') ? 'MobileLayoutL' : document.querySelector('.app-container-p') ? 'MobileLayoutP' : 'desktop',
          viewport: [innerWidth, innerHeight], errorPanels,
          swiperLive: !!(swiper && !swiper.destroyed && swiper.params), swiperIndex: swiper?.activeIndex,
          barCanvas: [...document.querySelectorAll('.seasonal-barchart-parent canvas, .barchart canvas')].some(c => c.getBoundingClientRect().width > 0),
          bundle: Array.from(document.scripts).map(s => s.src).find(src => /main\.[^/]+\.js/.test(src)),
        };
        if (!t?.chart) return { ...base, trendChart: false };
        const c = t.chart, a = c.options.plugins.annotation.annotations.box1, p = t.props;
        return { ...base, trendChart: true, startDate: p.startDate, daysOut: Number(p.daysOut), janDec: p.janDecDateRange,
          first: c.data.labels[0], last: c.data.labels.at(-1), labels: c.data.labels.length, highlight: [a.xMin, a.xMax],
          ppd: c.scales.x.getPixelForValue(1) - c.scales.x.getPixelForValue(0) };
      };
    });
    const state = () => page.evaluate(() => window.viewerState());

    async function record(name, checks) {
      const s = await state();
      const issues = [];
      for (const [label, ok] of Object.entries(checks(s))) if (!ok) issues.push(label);
      receipt.cases.push({ name, pass: issues.length === 0, issues, state: s });
      save();
      await page.screenshot({ path: path.join(out, name + '.png') });
      console.log(JSON.stringify({ case: name, pass: issues.length === 0, issues, layout: s.layout, days: s.daysOut, start: s.startDate, highlight: s.highlight, window: [s.first, s.last], errors: s.errorPanels }));
      return s;
    }
    const noCrash = s => ({ 'no error panel': s.errorPanels.length === 0, 'Swiper instance is live': s.swiperLive, 'no speed exception': !receipt.consoleErrors.concat(receipt.errors).some(e => /reading 'speed'/.test(e)) });

    async function settle(expected) {
      await page.waitForFunction(expected => {
        const f = window.findTrend();
        if (!f?.chart || !f.props.chartData?.length || !window.__twCapture?.ready?.trendChart) return false;
        return Object.entries(expected).every(([k, v]) => String(f.props[k]) === String(v));
      }, { timeout: 15000 }, expected);
      await sleep(900);
    }
    async function revealTrend() {
      if (mobile) {
        await page.evaluate(() => {
          const f = window.findTrend(); const swiper = f.props.swiper;
          const i = [...swiper.slides].indexOf(f.chart.canvas.closest('.swiper-slide'));
          if (i < 0) throw Error('Trend slide not found'); swiper.slideTo(i);
        });
        await sleep(700);
        return;
      }
      for (let n = 0; n < 4; n += 1) {
        const ok = await page.evaluate(() => { const r = document.querySelector('.seasonal-chart-parent')?.getBoundingClientRect(); return r && r.x >= 0 && r.right <= innerWidth + 1; });
        if (ok) return;
        await page.click('.stock-linechart-parent .swiper-button-prev'); await sleep(350);
      }
    }
    async function rotate(toLandscape) {
      await page.setViewport({ width: toLandscape ? 844 : 390, height: toLandscape ? 390 : 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
      await sleep(3500);
    }
    // Hover (mouse) or tap (touch) the highlight so the resize overlay appears, then press
    // one edge, move by `days` category positions, and release.
    async function dragEdge(side, days, touch = false) {
      const s = await state();
      const hover = await page.evaluate(() => {
        const c = window.findTrend().chart, a = c.options.plugins.annotation.annotations.box1, r = c.canvas.getBoundingClientRect();
        return { x: r.x + c.scales.x.getPixelForValue((a.xMin + Math.min(a.xMax, c.scales.x.max)) / 2), y: r.y + c.chartArea.top + c.chartArea.height / 2 };
      });
      if (touch) { await page.touchscreen.touchStart(hover.x, hover.y); await page.touchscreen.touchEnd(); }
      else await page.mouse.move(hover.x, hover.y);
      await page.waitForFunction(side => document.querySelector('.seasonal-opp-' + side + '-resizer')?.getBoundingClientRect().height > 50, { timeout: 5000 }, side);
      const edge = await page.$eval('.seasonal-opp-' + side + '-resizer', (e, side) => { const r = e.getBoundingClientRect(); return { x: side === 'right' ? r.right - 2 : r.left + 2, y: r.y + r.height / 2 }; }, side);
      const steps = Math.max(8, Math.ceil(Math.abs(days) / 10));
      if (touch) {
        await page.touchscreen.touchStart(edge.x, edge.y);
        for (let i = 1; i <= steps && days !== 0; i += 1) await page.touchscreen.touchMove(edge.x + s.ppd * days * i / steps, edge.y);
        await page.touchscreen.touchEnd();
      } else {
        await page.mouse.move(edge.x, edge.y); await page.mouse.down();
        if (days !== 0) await page.mouse.move(edge.x + s.ppd * days, edge.y, { steps });
        await page.mouse.up();
      }
      return s;
    }
    const dragRight = (days, touch) => dragEdge('right', days, touch);
    const endIndexFor = s => s.highlight[0] + s.daysOut - 1; // consecutive engine dates in these non-leap windows
    const tryStep = async fn => { try { await fn(); return null; } catch (e) { return redact(e.message); } };
    const selectVisible = async (id, value) => {
      for (const el of await page.$$('.seasonal-barchart-container #' + id)) { const r = await el.boundingBox(); if (r && r.width > 0) return el.select(value); }
      throw Error('No visible #' + id);
    };

    if (mode === 'landscape') {
      await record('L01-fresh-landscape-load', s => ({ ...noCrash(s), 'landscape layout': s.layout === 'MobileLayoutL', 'bar chart canvas': s.barCanvas }));
    }

    if (mode === 'rotate') {
      await revealTrend();
      await record('R01-portrait-loaded', s => ({ ...noCrash(s), 'portrait layout': s.layout === 'MobileLayoutP', 'trend chart': s.trendChart }));
      for (let cycle = 1; cycle <= 3; cycle += 1) {
        await rotate(true);
        const l = await record(`R0${cycle}a-landscape`, s => ({ ...noCrash(s), 'landscape layout': s.layout === 'MobileLayoutL', 'trend chart mounted': s.trendChart }));
        if (l.swiperLive) { await revealTrend(); await record(`R0${cycle}b-landscape-trend-usable`, s => ({ ...noCrash(s), 'trend chart': s.trendChart, 'days preserved': s.daysOut === 366 })); }
        await rotate(false);
        await record(`R0${cycle}c-portrait`, s => ({ ...noCrash(s), 'portrait layout': s.layout === 'MobileLayoutP', 'trend chart mounted': s.trendChart }));
      }
      // Touch press on the right edge without movement, then rotate (TW-BUG-0002 touch + TW-BUG-0001 after a touch resize).
      await revealTrend();
      if ((await state()).janDec) await page.click('.seasonal-chart-parent input[type=checkbox]').catch(() => {});
      const offErr = await tryStep(() => settle({ janDecDateRange: false }));
      await revealTrend();
      const before = await state();
      const touchErr = await tryStep(() => dragRight(0, true));
      await sleep(2500);
      await record('R04-portrait-touch-right-edge-no-move', s => ({ ...noCrash(s), 'Jan-Dec off': !offErr, 'touch overlay reached': !touchErr, 'duration unchanged': s.daysOut === before.daysOut, 'start unchanged': s.startDate === before.startDate }));
      await rotate(true);
      await record('R05-landscape-after-touch', s => ({ ...noCrash(s), 'landscape layout': s.layout === 'MobileLayoutL' }));
      // Retry panel: force the landscape boundary into its error state so the layout
      // unmounts (destroying its Swiper), then press Retry panel as a user would.
      await page.evaluate(() => window.findBoundary('MobileLayoutL').setState({ hasError: true }));
      await sleep(1500);
      const retry = await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(e => e.textContent.trim() === 'Retry panel'); b?.click(); return !!b; });
      await sleep(3500);
      await record('R06-retry-panel-recovers', s => ({ ...noCrash(s), 'retry button was shown': retry, 'landscape layout': s.layout === 'MobileLayoutL', 'bar chart canvas': s.barCanvas }));
      await rotate(false);
      await record('R07-portrait-after-retry', s => ({ ...noCrash(s), 'portrait layout': s.layout === 'MobileLayoutP' }));
    }


    if (mode === 'touch') {
      await page.evaluate(() => {
        window.touchTrace = [];
        for (const type of ['touchstart','touchmove','touchend','touchcancel']) document.addEventListener(type,e => window.touchTrace.push({type,x:e.touches[0]?.clientX,target:String(e.target.className)}),{capture:true,passive:true});
      });
      await revealTrend();
      if ((await state()).janDec) await page.click('.seasonal-chart-parent input[type=checkbox]');
      await settle({ janDecDateRange: false });
      await revealTrend();
      const b = await record('T01-touch-start', s => ({...noCrash(s), '366 days': s.daysOut === 366}));
      let e = await tryStep(async () => { await dragRight(-30, true); await settle({daysOut:322}); });
      await record('T02-touch-left-30', s => ({...noCrash(s), 'settled':!e, '322 days':s.daysOut===322, 'end where released':s.highlight[1]===b.labels-30}));
      await revealTrend();
      const outside = await page.evaluate(() => {const c=window.findTrend().chart,r=c.canvas.getBoundingClientRect();return {x:r.x+c.chartArea.left+1,y:r.y+c.chartArea.top+10};});
      await page.touchscreen.tap(outside.x,outside.y);
      e = await tryStep(async () => { await dragRight(30, true); await settle({daysOut:352}); });
      receipt.touchMoveError = e;
      await record('T03-touch-right-30', s => ({...noCrash(s), 'settled':!e, '352 days':s.daysOut===352}));
      const beforeRotation = await state();
      await rotate(true);
      await record('T04-rotate-after-movement', s => ({...noCrash(s), 'landscape':s.layout==='MobileLayoutL','duration preserved':s.daysOut===beforeRotation.daysOut}));
      receipt.touchTrace = await page.evaluate(() => window.touchTrace);
    }
    if (mode === 'resize') {
      await page.select('#analysisActions', 'Buy & Hold');
      await settle({ startDate: '2026-01-01' }); await revealTrend();
      if ((await state()).janDec) await page.click('.seasonal-chart-parent input[type=checkbox]');
      await settle({ janDecDateRange: false });
      const b = await record('D01-buy-hold-rolling', s => ({ '366 days': s.daysOut === 366, 'Jan-Dec off': s.janDec === false }));
      const edgeMax = b.labels; // highlight end sits at the count when the end runs past the chart

      await dragRight(0); await sleep(2500);
      await record('D02-right-press-release-no-move', s => ({ 'duration stays 366': s.daysOut === 366, 'start unchanged': s.startDate === '2026-01-01', 'highlight unchanged': s.highlight[0] === b.highlight[0] && s.highlight[1] === b.highlight[1] }));

      await dragRight(5); await sleep(2500);
      await record('D03-clipped-edge-right-5', s => ({ 'rightward drag does not shorten': s.daysOut === 366 }));

      let e = await tryStep(async () => { await dragRight(-10); await settle({ daysOut: 342 }); });
      await record('D04-clipped-edge-left-10', s => ({ 'settled': !e, '342 days': s.daysOut === 342, 'end 2026-12-08': increment(s.startDate, s.daysOut - 1) === '2026-12-08', 'highlight end where released': s.highlight[1] === edgeMax - 10 }));

      e = await tryStep(async () => {
        const target = async sel => { for (const el of await page.$$(sel)) { const r = await el.boundingBox(); if (r && r.width > 0) return el; } throw Error('no ' + sel); };
        const d = await target('.seasonal-barchart-container #date');
        await d.click({ clickCount: 3 }); await page.keyboard.down('Control'); await page.keyboard.press('A'); await page.keyboard.up('Control');
        await page.keyboard.type('2026-05-01'); await page.keyboard.press('Enter');
        await settle({ startDate: '2026-05-01' });
        await selectVisible('daysout', '30');
        await settle({ daysOut: 30 });
      });
      await revealTrend();
      await record('D05-may1-30-days', s => ({ 'setup': !e, '30 days': s.daysOut === 30, 'fully visible': s.highlight[1] === endIndexFor(s) }));

      e = await tryStep(async () => { await dragRight(10); await settle({ daysOut: 40 }); });
      await record('D06-right-plus-10', s => ({ 'settled': !e, '40 days': s.daysOut === 40, 'end 2026-06-09': increment(s.startDate, s.daysOut - 1) === '2026-06-09', 'highlight end matches': s.highlight[1] === endIndexFor(s) }));

      e = await tryStep(async () => { await dragRight(-10); await settle({ daysOut: 30 }); });
      await record('D07-right-minus-10', s => ({ 'settled': !e, '30 days': s.daysOut === 30, 'start unchanged': s.startDate === '2026-05-01' }));

      e = await tryStep(async () => { await dragRight(1); await settle({ daysOut: 31 }); });
      await record('D08-right-plus-1', s => ({ 'settled': !e, '31 days': s.daysOut === 31 }));

      await dragRight(0); await sleep(2500);
      await record('D09-unclipped-no-move', s => ({ 'duration stays 31': s.daysOut === 31 }));

      e = await tryStep(async () => { await dragRight(-60); await settle({ daysOut: 2 }); });
      await record('D10-minimum-duration', s => ({ 'settled': !e, 'minimum 2 days': s.daysOut === 2 }));

      // Neighbouring left edge still works and keeps the loaded window (TW-BUG-0009 protection).
      e = await tryStep(async () => { await selectVisible('daysout', '60'); await settle({ daysOut: 60 }); });
      await revealTrend();
      const w = await record('D11-set-60-days', s => ({ 'setup': !e, '60 days': s.daysOut === 60 }));
      e = await tryStep(async () => { await dragEdge('left', 20); await settle({ startDate: '2026-05-21' }); });
      await record('D12-left-edge-forward-20', s => ({ 'settled': !e, 'start 2026-05-21': s.startDate === '2026-05-21', 'end kept 2026-06-29': increment(s.startDate, s.daysOut - 1) === '2026-06-29', 'window first kept': s.first === w.first, 'window last kept': s.last === w.last }));
      e = await tryStep(async () => { await dragRight(5); await settle({ daysOut: 45 }); });
      await record('D13-right-plus-5-after-left-drag', s => ({ 'settled': !e, '45 days': s.daysOut === 45, 'start kept': s.startDate === '2026-05-21' }));
    }
    receipt.execution_complete = true;
  } catch (error) {
    receipt.fatal = redact(error.stack || error.message);
    throw error;
  } finally {
    save();
    await browser.close();
  }
})().catch(error => { console.error(redact(error.message)); process.exitCode = 1; });
