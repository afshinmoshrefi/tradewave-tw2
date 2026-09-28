const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('/home/flask/tools/ui_capture/node_modules/puppeteer');

const build = '/home/flask/web-react/releases/build-79fcba0be29af546cfd2ac01b1042b8405382b60';
const output = '/tmp/toolbar-nowrap-final';
fs.mkdirSync(output, { recursive: true });
const fetchShell = () => new Promise((resolve, reject) => http.get('http://127.0.0.1:5500/internal/capture/app', res => {
  let html = '';
  res.on('data', chunk => html += chunk);
  res.on('end', () => res.statusCode === 200 ? resolve(html) : reject(new Error(`shell ${res.statusCode}`)));
}).on('error', reject));

(async () => {
  const js = fs.readdirSync(path.join(build, 'static/js')).find(name => /^main\..*\.js$/.test(name));
  const css = fs.readdirSync(path.join(build, 'static/css')).find(name => /^main\..*\.css$/.test(name));
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const baseline = await fetchShell();
    const user = JSON.parse(baseline.match(/window\.current_user_id=("(?:[^"\\]|\\.)*")/)[1]);
    const widths = [1046];
    for (const titlesOn of [true]) {
      if (!titlesOn) widths.splice(0, widths.length, 1300, 1280);
      for (const width of widths) {
        const page = await browser.newPage();
        await page.setViewport({ width, height: 545, deviceScaleFactor: 1 });
        await page.evaluateOnNewDocument((uid, on) => {
          localStorage.setItem('UITheme', 'dark');
          localStorage.setItem('tw_notifybell_seen', '1');
          localStorage.setItem('tw_symbolbox_seen', '1');
          localStorage.setItem('leftNavWidthPct', '40');
          localStorage.setItem(uid + ':tw_show_toolbar_titles', JSON.stringify(on));
        }, user, titlesOn);
        await page.setCookie(
          { name: 'terms_accepted', value: user, url: 'http://127.0.0.1/' },
          { name: 'first1', value: '1', url: 'http://127.0.0.1/' },
          { name: `tw_onboard_dismissed_${user}`, value: '1', url: 'http://127.0.0.1/' },
          { name: `tw_conversion_shown_${user}`, value: '1', url: 'http://127.0.0.1/' },
        );
        await page.setRequestInterception(true);
        page.on('request', async req => {
          const url = new URL(req.url());
          if (req.isNavigationRequest() && req.frame() === page.mainFrame() && url.pathname === '/app/') {
            const shell = process.env.LIVE ? await fetchShell() : (await fetchShell()).replace(/\/app\/static\/js\/main\.[^" ]+\.js/, '/app/static/js/' + js).replace(/\/app\/static\/css\/main\.[^" ]+\.css/, '/app/static/css/' + css);
            return req.respond({ status: 200, contentType: 'text/html', body: shell });
          }
          if (!process.env.LIVE && url.pathname.startsWith('/app/static/')) {
            const file = path.join(build, url.pathname.slice('/app/'.length));
            if (fs.existsSync(file)) return req.respond({ status: 200, contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'application/octet-stream', body: fs.readFileSync(file) });
          }
          return req.continue();
        });
        const deep = Buffer.from('2|HLT|2026-09-28|141|10').toString('base64');
        await page.goto('http://127.0.0.1/app/?o=' + encodeURIComponent(deep), { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('.barchart-controls .tw-toolbar-title', { timeout: 60000 }).catch(() => {});
        await new Promise(resolve => setTimeout(resolve, 3500));
        await page.evaluate(() => [...document.querySelectorAll('button')].find(button => button.textContent.includes('Go to Wave Viewer'))?.click());
        await new Promise(resolve => setTimeout(resolve, 300));

        if(process.env.PREVIEW_CSS)await page.addStyleTag({content:fs.readFileSync('/home/tradewave-worktrees/toolbar-single-row-20260928/web-react/src/components/styles/SeasonalBarChart.css','utf8')});
        const states=[];
        for(const pct of [40,39,38,37,36,35,34,33,32,31,30,29,28,27,26,25,24.726,24,23,22,21,20]){
          const divider=await page.$('[aria-label="Resize opportunity panel"]');
          const dr=await divider.boundingBox();
          await page.mouse.move(dr.x+dr.width/2,dr.y+100);await page.mouse.down();
          await page.mouse.move(1046*pct/100,dr.y+100);await page.mouse.up();
          await new Promise(r=>setTimeout(r,100));
          const result=await page.evaluate(()=>{
            const bar=document.querySelector('.barchart-controls'), br=bar.getBoundingClientRect();
            const visible=e=>e.getBoundingClientRect().width>0&&getComputedStyle(e).display!=='none';
            const headers=[...bar.querySelectorAll('.tw-toolbar-title')].filter(visible).map(e=>{
              const r=e.getBoundingClientRect(),c=document.createElement('canvas').getContext('2d');c.font=getComputedStyle(e).font;
              return {text:e.textContent,x:r.x,y:r.y,right:r.right,width:r.width,textWidth:c.measureText(e.textContent).width};
            });
            const inputs=[...bar.querySelectorAll('input,select,.tw-select-compact-label')].filter(visible).map(e=>{
              const r=e.getBoundingClientRect(),s=getComputedStyle(e),c=document.createElement('canvas').getContext('2d');c.font=s.font;
              const text=e.matches('select')?e.selectedOptions[0]?.textContent.trim():e.matches('input')?e.value:e.textContent;
              return {id:e.id||e.className,value:text,width:r.width,x:r.x,right:r.right,font:s.fontSize,title:e.title,aria:e.getAttribute('aria-label'),textWidth:c.measureText(text||'').width};
            });
            return {width:br.width,height:br.height,left:br.x,right:br.right,rows:[...new Set(headers.map(h=>Math.round(h.y)))],headers,inputs,canvas:!!document.querySelector('.seasonal-barchart-parent canvas')};
          });
          result.pct=pct;
          result.overflow=result.inputs.filter(e=>e.x<result.left-1||e.right>result.right+1);
          result.labelOverflow=result.headers.filter(e=>e.textWidth>e.width+0.1);
          result.clippedValues=result.inputs.filter(e=>(e.id==='date'||e.id==='symbol'||e.id==='tw-select-compact-label')&&e.textWidth>e.width-2);
          states.push(result);
          if([40,24.726,20].includes(pct))await page.screenshot({path:path.join(output,'toolbar-'+pct+'.png')});
        }
        fs.writeFileSync(path.join(output,'sweep.json'),JSON.stringify(states,null,2));
        console.log(JSON.stringify(states.map(({pct,width,height,rows,overflow,labelOverflow,clippedValues})=>({pct,width,height,rows,overflow,labelOverflow,clippedValues}))));

        const bad=states.filter(r=>r.rows.length!==1||r.overflow.length||r.labelOverflow.length||r.clippedValues.length);
        if(bad.length)throw new Error('Layout failure at '+bad.map(r=>r.width).join(','));
        await page.select('.barchart-controls select#daysout','140');
        await new Promise(r=>setTimeout(r,800));
        const days=await page.$eval('.barchart-controls select#daysout',e=>({value:e.value,full:e.selectedOptions[0].textContent.trim(),caption:e.parentElement.querySelector('.tw-select-compact-label').textContent,title:e.title}));
        if(days.value!=='140'||days.caption!=='140'||!days.full.includes('days'))throw new Error('Days selection failed '+JSON.stringify(days));
        const best=await page.$eval('#oppBySymbol',e=>[...e.options].filter(o=>!o.disabled&&!o.hidden&&o.value!==e.value).map(o=>({value:o.value,label:o.textContent.trim()})));
        if(best.length){await page.select('#oppBySymbol',best[0].value);await new Promise(r=>setTimeout(r,800));}
        const selected=await page.$eval('#oppBySymbol',e=>({value:e.value,full:e.selectedOptions[0]?.textContent.trim(),title:e.title,caption:e.parentElement.querySelector('.tw-select-compact-label').textContent}));
        const before=await page.$eval('input[value=MFE]',e=>e.checked);await page.click('input[value=MFE]');const after=await page.$eval('input[value=MFE]',e=>e.checked);
        if(before===after)throw new Error('MFE toggle failed');
        const report={days,bestOption:best[0],selected,mfeToggled:before!==after,bundle:await page.evaluate(()=>performance.getEntriesByType('resource').map(x=>x.name).find(x=>/main\.[^/]+\.js/.test(x)))};
        console.log('INTERACTIONS '+JSON.stringify(report));fs.writeFileSync(path.join(output,'interactions.json'),JSON.stringify(report,null,2));
        await page.close();
      }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exit(1); });
