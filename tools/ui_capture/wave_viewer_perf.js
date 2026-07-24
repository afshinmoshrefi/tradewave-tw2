#!/usr/bin/env node

const fs = require('fs')
const http = require('http')
const path = require('path')
const puppeteer = require('puppeteer')

const INTERNAL_CAPTURE_URL = 'http://127.0.0.1:5500/internal/capture/app'
const APP_ORIGIN = 'http://127.0.0.1'
const APP_PATH = '/app/'
const TARGETS = ['UNH', 'PCAR', 'FAST', 'EQR', 'AAPL']
const OVERRIDE_BUNDLE_PATH = process.argv[3] || null

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function fetchInternalShell() {
  return new Promise((resolve, reject) => {
    http.get(INTERNAL_CAPTURE_URL, response => {
      if (response.statusCode !== 200) {
        reject(new Error(`capture shell returned HTTP ${response.statusCode}`))
        response.resume()
        return
      }
      let body = ''
      response.on('data', chunk => { body += chunk })
      response.on('end', () => resolve(body))
    }).on('error', reject)
  })
}

function extractUserId(html) {
  const match = html.match(/window\.current_user_id=("(?:[^"\\]|\\.)*")/)
  return match ? JSON.parse(match[1]) : null
}

function chartRequestDetails(url) {
  const match = new URL(url).pathname.match(/\/ChartData4\/([^/]+)\/([^/]+)\/([^/]+)\/([^/]+)\/([^/]+)/)
  return match ? {
    marketId: decodeURIComponent(match[1]),
    startDate: decodeURIComponent(match[2]),
    symbol: decodeURIComponent(match[3]).toUpperCase(),
    days: decodeURIComponent(match[4]),
    years: decodeURIComponent(match[5]),
  } : null
}

async function waitUntil(predicate, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const result = await predicate()
    if (result) return result
    await sleep(50)
  }
  throw new Error(`timed out waiting for ${label}`)
}

async function canvasSignature(page) {
  return page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll('.seasonal-barchart-parent canvas'))
      .filter(canvas => {
        const rect = canvas.getBoundingClientRect()
        return rect.width > 50 && rect.height > 50 && canvas.width > 0 && canvas.height > 0
      })
      .sort((left, right) => (right.width * right.height) - (left.width * left.height))
    const canvas = candidates[0]
    if (!canvas) return null
    const context = canvas.getContext('2d')
    if (!context) return null
    const sampleCanvas = document.createElement('canvas')
    sampleCanvas.width = 16
    sampleCanvas.height = 12
    const sampleContext = sampleCanvas.getContext('2d', { willReadFrequently: true })
    if (!sampleContext) return null
    sampleContext.drawImage(canvas, 0, 0, sampleCanvas.width, sampleCanvas.height)
    const sampled = sampleContext.getImageData(
      0,
      0,
      sampleCanvas.width,
      sampleCanvas.height,
    ).data
    const colors = new Set()
    let hash = 2166136261
    for (let index = 0; index < sampled.length; index += 4) {
      const pixel = `${sampled[index]},${sampled[index + 1]},${sampled[index + 2]},${sampled[index + 3]}`
      colors.add(pixel)
      for (let offset = 0; offset < 4; offset += 1) {
        hash ^= sampled[index + offset]
        hash = Math.imul(hash, 16777619)
      }
    }
    // A valid all-positive or all-negative chart can legitimately contain only
    // the background and one bar color (UNH is a live example).
    if (colors.size <= 1) return null
    return `${canvas.width}x${canvas.height}:${colors.size}:${hash >>> 0}`
  })
}

async function waitForStableCanvas(page, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  let previous = null
  let stableCount = 0
  let firstAt = null
  let stableStartAt = null
  const recent = []
  while (Date.now() < deadline) {
    const signature = await canvasSignature(page)
    if (signature && firstAt === null) firstAt = Date.now()
    recent.push(signature)
    if (recent.length > 20) recent.shift()
    if (signature && signature === previous) {
      stableCount += 1
      // Chart animation is disabled in the repaired bundle; two consecutive
      // identical samples prove the committed canvas is no longer changing.
      if (stableCount >= 1) {
        return {
          at: stableStartAt,
          verifiedAt: Date.now(),
          firstAt,
          signature,
        }
      }
    } else {
      previous = signature
      stableStartAt = signature ? Date.now() : null
      stableCount = 0
    }
    await sleep(50)
  }
  throw new Error(`timed out waiting for stable seasonal bar-chart canvas; recent=${JSON.stringify(recent)}`)
}

async function findOpportunityRow(page, symbol) {
  return page.evaluate(target => {
    const rows = Array.from(document.querySelectorAll('.opp-container .opp-table tbody tr'))
    for (const row of rows) {
      const hasTarget = Array.from(row.querySelectorAll('td'))
        .some(cell => cell.textContent.trim().toUpperCase() === target)
      if (hasTarget) {
        return row.getAttribute('id')
      }
    }
    return null
  }, symbol)
}

async function main() {
  const outputPath = process.argv[2] || 'out/wave_viewer_perf.json'
  const shell = await fetchInternalShell()
  const uuid = extractUserId(shell)
  if (!uuid) throw new Error('could not extract capture-bot UUID')

  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb'],
  })
  const results = {
    captured_at: new Date().toISOString(),
    cold: null,
    warm: [],
    console_errors: [],
    missing_targets: [],
  }

  try {
    const page = await browser.newPage()
    await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 })
    page.on('console', message => {
      if (message.type() === 'error') results.console_errors.push(message.text())
    })
    page.on('pageerror', error => results.console_errors.push(`pageerror: ${error.message}`))

    await page.evaluateOnNewDocument(userId => {
      localStorage.setItem('UITheme', 'dark')
      localStorage.setItem('tw_notifybell_seen', '1')
      localStorage.setItem('tw_symbolbox_seen', '1')
      const scoped = {
        tw_last_welcomed_tier: { tier: 'strategist', wasTrial: false },
        tw_lesson_enrolled: '1',
        tw_lesson_lastopened: 7,
      }
      for (const [key, value] of Object.entries(scoped)) {
        localStorage.setItem(`${userId}:${key}`, JSON.stringify(value))
      }
    }, uuid)

    const cookies = [
      { name: 'WindowNumber', value: '0', url: `${APP_ORIGIN}/` },
      { name: 'selectedSecurity', value: 'S&P 500 STOCKS', url: `${APP_ORIGIN}/` },
      { name: 'showPEOpps', value: 'false', url: `${APP_ORIGIN}/` },
      { name: 'oppYearsPerGroup', value: JSON.stringify({ 'S&P 500 STOCKS': [10, 8] }), url: `${APP_ORIGIN}/` },
      { name: 'terms_accepted', value: uuid, url: `${APP_ORIGIN}/` },
      { name: 'first1', value: '1', url: `${APP_ORIGIN}/` },
      { name: `tw_onboard_dismissed_${uuid}`, value: '1', url: `${APP_ORIGIN}/` },
      { name: `tw_conversion_shown_${uuid}`, value: '1', url: `${APP_ORIGIN}/` },
    ]
    await page.setCookie(...cookies)

    await page.setRequestInterception(true)
    page.on('request', async request => {
      const isMainDocument = request.isNavigationRequest() && request.frame() === page.mainFrame()
      const url = request.url()
      if (OVERRIDE_BUNDLE_PATH && /\/app\/static\/js\/main\.[a-f0-9]+\.js(?:\?|$)/.test(url)) {
        request.respond({
          status: 200,
          contentType: 'application/javascript; charset=utf-8',
          body: fs.readFileSync(OVERRIDE_BUNDLE_PATH),
        })
        return
      }
      if (isMainDocument && (url === `${APP_ORIGIN}${APP_PATH}` || url.startsWith(`${APP_ORIGIN}${APP_PATH}?`))) {
        try {
          request.respond({
            status: 200,
            contentType: 'text/html; charset=utf-8',
            body: await fetchInternalShell(),
          })
        } catch {
          request.abort('failed')
        }
        return
      }
      request.continue()
    })

    const chartRequests = []
    page.on('request', request => {
      const details = chartRequestDetails(request.url())
      if (!details) return
      chartRequests.push({ request, ...details, start_at: Date.now(), end_at: null, failed: false })
    })
    page.on('requestfinished', request => {
      const record = chartRequests.find(item => item.request === request)
      if (record) record.end_at = Date.now()
    })
    page.on('requestfailed', request => {
      const record = chartRequests.find(item => item.request === request)
      if (record) {
        record.end_at = Date.now()
        record.failed = true
      }
    })

    const coldSelectionAt = Date.now()
    const deepLink = Buffer.from('2|AAPL|2026-01-15|15|10', 'utf8').toString('base64')
    await page.goto(`${APP_ORIGIN}${APP_PATH}?o=${deepLink}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    })
    const coldRequest = await waitUntil(
      () => chartRequests.find(item =>
        item.symbol === 'AAPL' &&
        item.startDate === '2026-01-15' &&
        item.start_at >= coldSelectionAt
      ),
      60000,
      'cold AAPL ChartData4 request',
    )
    await waitUntil(() => coldRequest.end_at, 60000, 'cold AAPL response completion')
    const coldCanvasPromise = waitForStableCanvas(page)
    await page.waitForFunction(
      start => window.__twCapture?.ready?.seasonal === true &&
        window.__twCapture?.meta?.seasonal?.symbol === 'AAPL' &&
        window.__twCapture?.meta?.seasonal?.ts >= start,
      { timeout: 60000 },
      coldSelectionAt,
    )
    const coldCaptureReadyAt = await page.evaluate(() => window.__twCapture?.meta?.seasonal?.ts || null)
    const coldCanvas = await coldCanvasPromise
    results.cold = {
      symbol: 'AAPL',
      selection_to_request_start_ms: coldRequest.start_at - coldSelectionAt,
      request_duration_ms: coldRequest.end_at - coldRequest.start_at,
      response_to_capture_ready_ms: coldCaptureReadyAt - coldRequest.end_at,
      response_to_first_canvas_ms: coldCanvas.firstAt - coldRequest.end_at,
      response_to_stable_canvas_ms: coldCanvas.at - coldRequest.end_at,
      selection_to_usable_chart_ms: coldCanvas.at - coldSelectionAt,
    }

    await page.waitForFunction(
      () => window.__twCapture?.ready?.oppTable === true &&
        Number(window.__twCapture?.meta?.oppTable?.rows || 0) > 0,
      { timeout: 60000 },
    )

    for (const symbol of TARGETS) {
      process.stderr.write(`measuring warm ${symbol}\n`)
      const rowId = await findOpportunityRow(page, symbol)
      if (rowId === null) {
        results.missing_targets.push(symbol)
        continue
      }
      const row = await page.$(`.opp-container .opp-table tbody tr[id="${rowId}"]`)
      if (!row) {
        results.missing_targets.push(symbol)
        continue
      }
      const selectedStartDate = await row.$eval('td', cell => cell.textContent.trim())
      const selectedAt = Date.now()
      await row.click()
      const requestRecord = await waitUntil(
        () => chartRequests.find(item =>
          item.symbol === symbol &&
          item.startDate === selectedStartDate &&
          item.start_at >= selectedAt
        ),
        30000,
        `${symbol} ChartData4 request`,
      )
      await waitUntil(() => requestRecord.end_at, 60000, `${symbol} response completion`)
      const canvasPromise = waitForStableCanvas(page)
      await page.waitForFunction(
        ({ target, start }) => window.__twCapture?.ready?.seasonal === true &&
          window.__twCapture?.meta?.seasonal?.symbol === target &&
          window.__twCapture?.meta?.seasonal?.ts >= start,
        { timeout: 60000 },
        { target: symbol, start: selectedAt },
      )
      const captureReadyAt = await page.evaluate(() => window.__twCapture?.meta?.seasonal?.ts || null)
      const canvas = await canvasPromise.catch(error => {
        return page.evaluate(() => Array.from(document.querySelectorAll('canvas')).map(node => {
          const rect = node.getBoundingClientRect()
          return {
            parentClass: node.parentElement?.className || '',
            width: node.width,
            height: node.height,
            rectWidth: rect.width,
            rectHeight: rect.height,
            display: getComputedStyle(node).display,
          }
        })).then(async canvases => {
          const screenshotPath = outputPath.replace(/\.json$/i, `-${symbol}-failure.png`)
          fs.mkdirSync(path.dirname(screenshotPath), { recursive: true })
          await page.screenshot({ path: screenshotPath, fullPage: true })
          throw new Error(`${symbol}: ${error.message}; canvases=${JSON.stringify(canvases)}; screenshot=${screenshotPath}`)
        })
      })
      results.warm.push({
        symbol,
        selection_to_request_start_ms: requestRecord.start_at - selectedAt,
        request_duration_ms: requestRecord.end_at - requestRecord.start_at,
        response_to_capture_ready_ms: captureReadyAt - requestRecord.end_at,
        response_to_first_canvas_ms: canvas.firstAt - requestRecord.end_at,
        response_to_stable_canvas_ms: canvas.at - requestRecord.end_at,
        selection_to_usable_chart_ms: canvas.at - selectedAt,
      })
    }

    const scripts = await page.$$eval('script[src*="/app/static/js/main."]', nodes => nodes.map(node => node.src))
    const bundleIdentity = OVERRIDE_BUNDLE_PATH || scripts.join('\n')
    const bundleMatch = bundleIdentity.match(/main\.([a-f0-9]+)\.js/)
    results.bundle_hash = bundleMatch ? bundleMatch[1] : null
    results.baseline = await page.evaluate(() => ({
      selected_security: document.querySelector('#securityTypeList')?.value || null,
      rows: window.__twCapture?.meta?.oppTable?.rows || null,
      seasonal_symbol: window.__twCapture?.meta?.seasonal?.symbol || null,
    }))
  } finally {
    await browser.close()
  }

  fs.mkdirSync(path.dirname(outputPath), { recursive: true })
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2))
  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`)
}

main().catch(error => {
  console.error(error.stack || error.message)
  process.exit(1)
})
