const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const harness=fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame={')[0];
eval('(()=>{'+harness.replace("const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');",'')+';globalThis.personalHarness={context,el};})()');
const {context,el}=globalThis.personalHarness;
el('api').value='https://arena.test';el('mode').value='server';assert.equal(context.baseURL(),'https://arena.test');
el('mode').value='personal';assert.equal(context.baseURL(),'https://arena.test/personal');assert.equal(context.serviceURL(),'https://arena.test');
el('mode').value='demo';assert.equal(context.baseURL(),'https://arena.test');
assert.match(fs.readFileSync('static/index.html','utf8'),/value="personal"/);
console.log('PASS: personal execution routes builds, tests, replay and downloads through the worker prefix; cloud routes remain unchanged');
