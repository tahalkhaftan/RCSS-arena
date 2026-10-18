const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const harness=fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame={')[0];
eval('(()=>{'+harness.replace("const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');",'')+';globalThis.offlineHarness={context,el};})()');
const {context,el}=globalThis.offlineHarness;
el('offlineLogging').checked=false;assert.equal(context.settings().offline_logging,false);
el('offlineLogging').checked=true;assert.equal(context.settings().offline_logging,true);
assert.match(fs.readFileSync('static/index.html','utf8'),/id="offlineLogging" type="checkbox"/);
console.log('PASS: offline logging checkbox defaults off and travels with match configuration');
