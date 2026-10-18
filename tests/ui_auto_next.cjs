const fs=require('fs'),vm=require('vm');
const harness=fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame=')[0];
const checks=`
vm.runInContext("job={id:'7',api:'https://test'};report={id:'7',status:'running',total:4,config:{rounds:2,games_per_round:2},matches:[],progress:{round:1,game:1}};render()",context);
assert.equal(el('monitorMatch').value,'1/1');
vm.runInContext("report.matches=[{round:1,game:1,status:'completed',left_score:1,right_score:0}];render()",context);
assert.equal(el('monitorMatch').value,'1/1','Unchecked must retain selected game');
el('monitorAutoNext').checked=true;el('monitorAutoNext').change();assert.equal(el('monitorMatch').value,'1/2');
el('monitorMode').value='replay';vm.runInContext("report.matches.push({round:1,game:2,status:'completed'});updateMonitor()",context);assert.equal(el('monitorMatch').value,'1/2','Replay must not jump');
el('monitorMode').value='live';vm.runInContext('updateMonitor()',context);assert.equal(el('monitorMatch').value,'2/1','Must continue into the next round');
vm.runInContext("monitorSource='file';followNextGame('2/2')",context);assert.equal(el('monitorMatch').value,'2/1','Independent RCG must not jump');
vm.runInContext("monitorSource='server';followNextGame('2/2')",context);assert.equal(el('monitorMatch').value,'2/2','New live game frames trigger following');
vm.runInContext("report.status='completed';updateMonitor()",context);assert.equal(el('monitorMatch').value,'2/2','Last game must remain selected');
console.log('PASS: optional live auto-next, rounds, direct frames, replay isolation and final game');
`;
vm.runInNewContext(harness+checks,{require,console,URL,AbortController,setTimeout,clearTimeout});
