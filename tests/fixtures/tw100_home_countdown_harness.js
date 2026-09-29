// TW-BUG-0023: drives the homepage 100-Year Pattern countdown script with a fixed clock.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function run(nowIso) {
  const el = () => ({ textContent: '', hidden: false, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } });
  const nodes = {}; ['[data-tw100-title]','[data-tw100-lede]','[data-tw100-basis]','[data-tw100-days-label]','[data-tw100-hours-label]','[data-tw100-minutes-label]'].forEach(k => nodes[k] = el());
  const units = { '[data-tw100-days]': el(), '[data-tw100-hours]': el(), '[data-tw100-minutes]': el() };
  const card = { querySelector: s => nodes[s] };
  const root = Object.assign(el(), { closest: () => card, querySelector: s => units[s] });
  const fixed = Date.parse(nowIso);
  const RealDate = Date;
  global.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [fixed])); } static now() { return fixed; } };
  global.Date.parse = RealDate.parse;
  global.document = { getElementById: () => root };
  global.window = { setTimeout() {}, setInterval() {} };
  new Function(src)();
  global.Date = RealDate;
  return [nowIso, nodes['[data-tw100-title]'].textContent || '(countdown title unchanged)', units['[data-tw100-days]'].textContent, nodes['[data-tw100-days-label]'].textContent, units['[data-tw100-hours]'].textContent, nodes['[data-tw100-hours-label]'].textContent, 'hidden=' + root.hidden].join(' | ');
}
const cases = JSON.parse(process.argv[3]);
for (const t of cases) console.log(run(t));
