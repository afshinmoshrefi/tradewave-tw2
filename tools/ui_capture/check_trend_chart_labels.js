#!/usr/bin/env node
'use strict';

// Real Chromium + Chart.js regression for successive responses on one mounted
// SeasonalChart. Run: node tools/ui_capture/check_trend_chart_labels.js
// Requires the existing web-react and tools/ui_capture npm dependencies only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const puppeteer = require('puppeteer');

const repo = path.resolve(__dirname, '../..');
const reactRequire = createRequire(path.join(repo, 'web-react/package.json'));
const babel = reactRequire('@babel/core');
const components = path.join(repo, 'web-react/src/components');
const fixture = require('./fixtures/trend-chart-responses.json');

function compileComponent(name) {
  return babel.transformSync(fs.readFileSync(path.join(components, name + '.js'), 'utf8'), {
    babelrc: false,
    configFile: false,
    presets: [reactRequire.resolve('@babel/preset-react')],
    plugins: [reactRequire.resolve('@babel/plugin-transform-modules-commonjs')],
  }).code;
}

async function loadModule(page, name, content) {
  await page.addScriptTag({ content: `(() => {
    const module = { exports: {} };
    const exports = module.exports;
    const require = window.testRequire;
    ${content}
    window.testModules[${JSON.stringify(name)}] = module.exports;
  })();` });
}

async function run() {
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.emulateTimezone('America/New_York');
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Give real Common cookie helpers a normal origin, without network access.
    await page.setRequestInterception(true);
    page.on('request', request => request.respond({
      status: 200, contentType: 'text/html',
      body: '<html><body style="margin:0"><div id="test"></div></body></html>',
    }));
    await page.goto('http://trend-chart.test/');
    for (const asset of [
      'react/umd/react.development.js',
      'react-dom/umd/react-dom.development.js',
      'chart.js/dist/chart.js',
      'chartjs-plugin-annotation/dist/chartjs-plugin-annotation.js',
    ]) {
      await page.addScriptTag({ path: reactRequire.resolve(asset) });
    }
    await page.evaluate(() => {
      window.testContext = React.createContext({});
      // Only adjacent UI is stubbed. The component, Common/date helpers, React
      // wrapper, Chart.js parser, scales and annotation plugin are real.
      window.testModules = {
        react: React,
        'react-dom': ReactDOM,
        'chart.js': Chart,
        'chart.js/auto': Chart,
        './UserContext': { UserContext: window.testContext },
        'chartjs-plugin-annotation': {},
        'jwt-decode': () => { throw new Error('Authentication is outside this render test'); },
        '@tippyjs/react': { __esModule: true, default: ({ children }) => children },
        './SeasonalChartStats': { __esModule: true, default: () => null },
        './CheckBox': { __esModule: true, default: () => null },
      };
      window.testRequire = name => {
        if (name.startsWith('react-icons/')) return new Proxy({}, { get: () => () => null });
        if (name.endsWith('.css')) return {};
        if (!(name in window.testModules)) throw new Error('Unmapped module: ' + name);
        return window.testModules[name];
      };
    });
    await loadModule(page, 'react-chartjs-2', fs.readFileSync(reactRequire.resolve('react-chartjs-2'), 'utf8'));
    for (const name of ['Common', 'startDateNudge', 'viewerCycleState', 'trendChartResizeTooltips', 'trendRightResize', 'SeasonalChart']) {
      await loadModule(page, './' + name, compileComponent(name));
    }
    assert.deepEqual(errors, [], 'The component and real library modules must load');

    await page.evaluate(() => {
      window.renderTrend = async (record, layout, empty = false) => {
        const data = empty ? [] : record.cons_seas_chart;
        const root = document.getElementById('test');
        root.style.width = layout.width + 'px';
        root.style.height = layout.height + 'px';
        const context = {
          browserH: layout.height, browserW: layout.width,
          rdd: { isMobile: layout.mobile, isTablet: false },
          infoTextSize: 12, globalTextSize: 12, loggedinUser: 'render-test',
          wpUserLevels: ['6'], token: '',
        };
        const props = {
          chartData: data, consolidatedSeasonalData: data,
          // Deliberately no chartLabels: this is the desktop/mobile caller contract.
          chartTitle: 'Seasonal Chart', startDate: record.request.opp_start_date,
          daysOut: 44, seasonalYears: record.request.sy, symbol: record.request.symbol,
          company: 'Apple', PEselected: 'cons',
          janDecDateRange: record.request.chart_start_date.endsWith('01-01'),
          seasonalBarChartData: [{}], securityTypeList2: [], UITheme: 'dark',
          tooltipSW: false, swiper: { enabled: true }, chartTo: () => {},
        };
        ReactDOM.render(React.createElement(window.testContext.Provider, { value: context },
          React.createElement(window.testModules['./SeasonalChart'].default, props)), root);
        // Let React effects, ResizeObserver and the wrapper's update finish.
        // Do not wait for the label assertions themselves: stale labels must fail.
        for (let frame = 0; frame < 40; frame += 1) {
          await new Promise(resolve => setTimeout(resolve, 25));
          const current = Object.values(Chart.instances)[0];
          if (empty ? !current : current?.data.datasets[1].data === data
            && current.getDatasetMeta(1)._parsed.length === data.length
            && current.width > 0 && current.height > 0) break;
        }
        const chart = Object.values(Chart.instances)[0];
        if (!chart) return null;
        const annotation = chart.options.plugins.annotation.annotations.box1;
        const dates = data.map(row => row[0]);
        const end = window.testModules['./Common'].incrementDate(props.startDate, props.daysOut - 1);
        return {
          id: chart.id, labels: chart.data.labels.slice(),
          points: chart.getDatasetMeta(1)._parsed.map(point => ({ x: point.x, y: point.y })),
          min: chart.scales.x.min, max: chart.scales.x.max,
          annotation: [annotation.xMin, annotation.xMax],
          expectedAnnotation: [dates.indexOf(props.startDate), dates.indexOf(end)],
          size: [chart.width, chart.height],
        };
      };
      window.unmountTrend = () => ReactDOM.unmountComponentAtNode(document.getElementById('test'));
    });

    const checks = [];
    const layouts = [
      { name: 'desktop', width: 1200, height: 700, mobile: false },
      { name: 'mobile portrait', width: 390, height: 844, mobile: true },
      { name: 'mobile landscape', width: 844, height: 390, mobile: true },
    ];
    for (const layout of layouts) {
      await page.setViewport({ width: layout.width, height: layout.height });
      await page.evaluate(() => window.unmountTrend());
      let mountedId;
      // Forward windows grow the old category list. Backward replacements must
      // remove old dates too, even when those dates were seen earlier.
      for (const name of ['rolling', 'forward', 'largeForward', 'forward', 'rolling', 'janDec']) {
        const record = fixture.responses[name];
        const actual = await page.evaluate((r, l) => window.renderTrend(r, l), record, layout);
        assert.deepEqual(errors, [], 'The component must render without browser errors');
        if (mountedId === undefined) mountedId = actual.id;
        assert.equal(actual.id, mountedId, 'The response replacement must keep one chart mounted');
        assert.deepEqual(actual.labels, record.cons_seas_chart.map(row => row[0]), layout.name + ': exact current date order/count');
        assert.deepEqual(actual.points.map(point => point.x), record.cons_seas_chart.map((_, index) => index), layout.name + ': parsed X positions');
        assert.deepEqual(actual.points.map(point => point.y), record.cons_seas_chart.map(row => row[1]), layout.name + ': engine numerical fidelity');
        assert.equal(actual.min, 0);
        assert.equal(actual.max, record.cons_seas_chart.length - 1);
        assert(actual.expectedAnnotation.every(index => index >= 0), 'Fixture opportunity must fit inside its curve');
        assert.deepEqual(actual.annotation, actual.expectedAnnotation, layout.name + ': highlight follows the same response');
        assert(actual.size.every(value => value > 0), 'Chart must have visible dimensions');
      }
      const record = fixture.responses.janDec;
      assert.equal(await page.evaluate((r, l) => window.renderTrend(r, l, true), record, layout), null);
      const restored = await page.evaluate((r, l) => window.renderTrend(r, l), record, layout);
      assert.notEqual(restored.id, mountedId, 'Clearing for Jan-Dec replaces the chart');
      assert.deepEqual(restored.labels, record.cons_seas_chart.map(row => row[0]));
      checks.push({ layout: layout.name, mountedTransitions: 6, clearAndReload: true });
    }
    assert.deepEqual(errors, [], 'No browser errors during regression');
    console.log(JSON.stringify({ passed: true, checks, fixtureSource: fixture.source }, null, 2));
  } finally {
    await browser.close();
  }
}

run().catch(error => { console.error(error.stack); process.exitCode = 1; });
