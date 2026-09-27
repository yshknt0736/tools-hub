// Run with `node tests/iec-voltage-flow.js`; no browser dependencies required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../tools/iec-voltage-flow/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert(script, 'calculator script exists');

const values = {
  Urp: '500', Kc: '1.10', Ks: '1.05', H: '2000', m: '1', base: '0',
  insulation: 'external', basis: 'standard', correctionSpecified: false,
  testClause: '', Ubase: '', tD: '20', hD: '', series: 'impulse',
  HL: '0', pLMeasured: '', tL: '20', hL: '', mTest: '1', wTest: '0'
};
const nodes = new Map();
for (const [id, value] of Object.entries(values)) {
  nodes.set(id, {
    value: String(value), checked: value === true,
    addEventListener() {}, classList: { toggle() {} },
    querySelectorAll() { return []; }, style: {}, dataset: {}
  });
}
nodes.set('assessment', {
  innerHTML: '', classList: { toggle() {} }
});
for (const id of ['prev', 'next', 'reset', 'play', 'dots', 'exampleBase',
  'UrpUnit', 'seriesNote', 'view', 'ctrl']) {
  nodes.set(id, { onclick: null, textContent: '', addEventListener() {} });
}
for (const id of ['seriesNote', 'view', 'ctrl']) {
  Object.assign(nodes.get(id), {
    innerHTML: '', style: {}, classList: { toggle() {} }, querySelectorAll: () => []
  });
}
const document = {
  getElementById: id => nodes.get(id),
  querySelectorAll: () => [],
  addEventListener() {}
};
const context = vm.createContext({
  document, clearInterval() {}, setInterval() {}, requestAnimationFrame: callback => callback()
});
vm.runInContext(script.replace(/\brender\(\);\s*$/, ''), context);
const compute = () => vm.runInContext('compute()', context);
const near = (actual, expected, tolerance=0.02) =>
  assert(Math.abs(actual-expected) < tolerance, `${actual} is not near ${expected}`);
const set = (id, value) => { nodes.get(id).value = String(value); };

let c = compute();
near(c.Urw, 738.12059);
assert.equal(c.Uw.v, 750);
near(c.UtA, 750);
assert(Number.isNaN(c.UtB), 'IEC 62927 result needs a test base');
vm.runInContext('render()', context);
assert(nodes.get('view').innerHTML.includes('750.0'), 'initial candidate renders');
vm.runInContext("path = 'b'; render()", context);
assert(nodes.get('view').innerHTML.includes('—'), 'missing IEC 62927 base renders as missing');
vm.runInContext("path = 'c'; render()", context);
assert(nodes.get('view').innerHTML.includes('同じ仕様の代替試験電圧ではありません'),
  'comparison states that the results are not interchangeable');
vm.runInContext("path = 'a'", context);

set('Ubase', '577.5');
c = compute();
near(c.UtB, 652.88946);
assert.equal(c.readyB, false, 'an illustrative number is not a confirmed test');

set('H', '1000');
c = compute();
near(c.pr, 1);
near(c.UtB, 577.5);

set('H', '2000');
set('basis', 'nonstandard');
c = compute();
near(c.pr, Math.exp(-2000/8150));
near(c.UtB, 738.12059);

set('basis', 'standard');
set('insulation', 'internal');
set('Ks', '1.15');
c = compute();
near(c.Ka, 1);
near(c.Urw, 632.5);

set('insulation', 'external');
set('Ks', '1.05');
set('pLMeasured', '90');
c = compute();
near(c.pL, 90);
near(c.KL, 90/101.3, 1e-8);

set('pLMeasured', '101.3');
set('hD', '11');
set('hL', '11');
set('wTest', '1');
c = compute();
near(c.kL, 1);
assert(c.kS > 1, 'site humidity factor is applied');
assert(c.UtB < 652.88946, 'humidity changes the illustrative result');

set('H', '4000');
vm.runInContext("path = 'b'", context);
vm.runInContext('renderAssessment(compute())', context);
assert(nodes.get('assessment').innerHTML.includes('信頼範囲'), 'out-of-range density warns');

console.log('iec-voltage-flow: OK');
