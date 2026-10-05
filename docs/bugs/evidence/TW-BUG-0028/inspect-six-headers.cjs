// Read-only public browser audit. Headless process; no local desktop interaction.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const {chromium} = require('/opt/smn-playwright/node_modules/playwright');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const root = fs.mkdtempSync('/var/tmp/smn-readonly-headers-20261005-');
(async () => {
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext();
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    return ['GET','HEAD'].includes(request.method()) &&
      ['seasonalmarketnews.com','www.seasonalmarketnews.com'].includes(url.hostname)
      ? route.continue() : route.abort();
  });
  const pages = [], captures = [];
  for (const symbol of ['XLF','SI','SPY','QQQ','AMZN','NVDA']) {
    for (const [kind,width,height] of [['desktop',1440,1050],['mobile',390,844]]) {
      const page = await context.newPage();
      const errors = [], httpErrors = [];
      page.on('pageerror', e => errors.push(String(e)));
      page.on('response', r => { if (r.status() >= 400) httpErrors.push({url:r.url(),status:r.status()}); });
      await page.setViewportSize({width,height});
      const url = `https://seasonalmarketnews.com/editions/2026-10-05/${symbol}/article.html`;
      const response = await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
      const html = await response.body();
      const htmlFile = `${symbol}-${kind}.html`;
      fs.writeFileSync(path.join(root,htmlFile),html);
      await page.evaluate(() => { for (const image of document.images) image.loading='eager'; });
      await page.waitForFunction(() => [...document.images].every(i=>i.complete),{timeout:6000}).catch(()=>{});
      const data = await page.evaluate(() => {
        const rect = e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
        const visible = e => {const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden';};
        const article = document.querySelector('article');
        const articleTop = article?.getBoundingClientRect().top ?? Infinity;
        return {
          title:document.title,
          masthead:[...document.querySelectorAll('body > header')].map(e=>({class:e.className,text:e.innerText,rect:rect(e),visible:visible(e)})),
          articleHeading:[...document.querySelectorAll('h1')].map(e=>({text:e.innerText,rect:rect(e),visible:visible(e)})),
          preArticleLinks:[...document.querySelectorAll('a')].filter(e=>e.getBoundingClientRect().top<articleTop).map(e=>({text:e.innerText,href:e.href,visible:visible(e)})),
          headerNavigationPresent:[...document.querySelectorAll('a')].some(e=>e.getBoundingClientRect().top<articleTop&&/^Home$/i.test(e.innerText.trim())),
          topTradeWaveLinkPresent:[...document.querySelectorAll('a')].some(e=>e.getBoundingClientRect().top<articleTop&&/tradewave\.ai/.test(e.href)),
          topMarkup:[...document.body.children].filter(e=>e.getBoundingClientRect().top<articleTop&&e.tagName!=='SCRIPT').map(e=>({tag:e.tagName,id:e.id,classes:e.className})),
          viewport:{width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth},
          bodyRoles:[...document.querySelectorAll('section[data-role]')].map(e=>e.dataset.role),
          bodyText:document.querySelector('.article-body')?.innerText ?? '',
          nativeCharts:[...document.querySelectorAll('[data-native-chart]')].map(e=>e.dataset.nativeChart),
          images:[...document.images].map(e=>({src:e.currentSrc||e.src,loaded:e.complete&&e.naturalWidth>0})),
          studyLinks:[...document.querySelectorAll('a')].filter(e=>/tradewave\.ai/.test(e.href)).map(e=>e.href),
          sources:[...document.querySelectorAll('.source-list a')].map(e=>({text:e.innerText,href:e.href}))
        };
      });
      data.bodyTextSha256 = sha(Buffer.from(data.bodyText)); delete data.bodyText;
      const name = `${symbol}-${kind}-header.png`;
      await page.screenshot({path:path.join(root,name)});
      captures.push({name,sha256:sha(fs.readFileSync(path.join(root,name)))});
      pages.push({symbol,kind,url,status:response.status(),response_sha256:sha(html),htmlFile,...data,pageErrors:errors,httpErrors});
      await page.close();
    }
  }
  const report = {checked_utc:new Date().toISOString(),root,method:'Headless Chromium; public GET only; third-party hosts blocked; no visible desktop',pages,captures};
  fs.writeFileSync(path.join(root,'inspection.json'),JSON.stringify(report,null,2));
  await browser.close();
  console.log(JSON.stringify({root,checked_utc:report.checked_utc,captures:captures.length,pages:pages.map(p=>({symbol:p.symbol,kind:p.kind,status:p.status,headerNavigationPresent:p.headerNavigationPresent,topTradeWaveLinkPresent:p.topTradeWaveLinkPresent,h1Visible:p.articleHeading.length===1&&p.articleHeading[0].visible,bodyRoles:p.bodyRoles,nativeCharts:p.nativeCharts.length,imagesLoaded:p.images.every(i=>i.loaded),sources:p.sources.length,overflow:p.viewport.scrollWidth>p.viewport.width,pageErrors:p.pageErrors,httpErrors:p.httpErrors}))},null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
