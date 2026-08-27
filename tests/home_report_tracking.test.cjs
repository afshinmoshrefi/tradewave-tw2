// Hermetic event checks: no browser account, cookies, network or analytics writes.
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = readFileSync(path.join(__dirname, '../site/templates/index-dark-blue.html'), 'utf8');
const script = html.split('<script>\n/* conversion analytics:')[1].split('</script>')[0];

test('card impression fires once, at 50% visibility; campaign data is bounded', () => {
  let observe, disconnected = 0;
  const events = [], window = {IntersectionObserver: true};
  const heroLink = {href:'/signup', getAttribute(k){return k==='data-cta-id'?'homepage_hero_start_free':this.href;},setAttribute(k,v){if(k==='href') this.href=v;}};
  const card = {};
  const document = {getElementById:()=>card,querySelectorAll:selector=>selector==='a[href]'?[heroLink]:[]};
  class IntersectionObserver {
    constructor(cb, options){observe=cb;assert.equal(options.threshold.length,1);assert.equal(options.threshold[0],.5);}
    observe(el){assert.equal(el,card);}
    disconnect(){disconnected++;}
  }
  runInNewContext('/* conversion analytics:'+script,{window,document,IntersectionObserver,URL,URLSearchParams,
    location:{origin:'https://example.test',search:'?utm_source=youtube&utm_content=private%40example.com'},
    gtag:(...args)=>events.push(args)});
  observe([{isIntersecting:true,intersectionRatio:.49}]);
  assert.equal(events.length,0);
  observe([{isIntersecting:true,intersectionRatio:.5}]);
  observe([{isIntersecting:true,intersectionRatio:1}]);
  assert.equal(events.length,1);
  assert.equal(events[0][1],'free_report_view');
  assert.equal(events[0][2].source,'homepage_hero_report');
  assert.equal(disconnected,1);
  assert.equal(window.__twReportAttribution.utm_source,'youtube');
  assert.equal(window.__twReportAttribution.utm_content,undefined);
  assert.match(heroLink.href,/tw_cta=homepage_hero_start_free/);
});

test('no analytics or observer never blocks the page', () => {
  runInNewContext('/* conversion analytics:'+script,{window:{},document:{getElementById:()=>({}),querySelectorAll:()=>[]},
    location:{origin:'https://example.test',search:''},URL,URLSearchParams});
});

test('a throwing analytics adapter cannot block the report modal', () => {
  const openFunction = 'function openLM(source){' + html.split('  function openLM(source){')[1].split('\n  function closeLM')[0];
  let opened = false, focused = false;
  const document = {activeElement:{},body:{style:{}}}, lm = {}, window = {};
  runInNewContext(openFunction + "\nopenLM('hero');", {
    document, lm, window, prevFocus:null,
    ov:{classList:{add(value){opened=value==='open';}}},
    form:{querySelector(){return {focus(){focused=true;}}}},
    location:{hash:'#free-report'},localStorage:{getItem(){return null;}},
    setTimeout(fn){fn();},gtag(){throw new Error('analytics unavailable');}
  });
  assert.equal(opened,true);
  assert.equal(focused,true);
  assert.equal(lm.className,'lm state-form');
  assert.equal(window.__twLeadSource,'homepage_hero_report');
});
