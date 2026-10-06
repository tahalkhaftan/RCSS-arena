const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={};function el(id){return nodes[id]||(nodes[id]={value:'1',textContent:'',style:{},disabled:false,addEventListener(){},setAttribute(){},files:[]});}
const events={};
const context={window:{addEventListener:(name,fn)=>events[name]=fn},document:{getElementById:el,querySelector:()=>el('track'),querySelectorAll:()=>[]},location:{protocol:'https:',origin:'https://example.test'},URL,AbortController,console,setTimeout:fn=>fn()};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/index.html','utf8').split('<script>')[1].split('</script>')[0],context);
vm.runInContext(`report={status:'running',total:1,matches:[],progress:{cycle:3000,expected_cycles:6000,percent:50,match_index:1,left_score:2,right_score:1}};render();`,context);
assert.equal(el('bar').style.width,'50%');
assert.ok(el('liveProgress').textContent.includes('3000'));
const final={status:'completed',id:'7',total:1,matches:[{round:1,game:1,status:'completed',left_score:13,right_score:2}],archive_ready:true,publication_pending:false};
let count=0;context.fetch=async()=>{
 count++;
 if(count===1)throw new TypeError('network offline');
 if(count===2)return {ok:false,status:502,json:async()=>({error:'temporary gateway failure'})};
 return {ok:true,json:async()=>count===3?{...final,archive_ready:false,publication_pending:true}:final};
};
vm.runInContext(`job={id:'7',api:'https://example.test'};running=true;watchJob()`,context).then(async()=>{
 assert.equal(count,4,'Polling must recover, then await ZIP publication');
 assert.equal(el('zip').disabled,false);
 assert.equal(JSON.parse(el('json').textContent).status,'completed');
 assert.equal(el('leftGoals').textContent,13);
 assert.equal(el('error').textContent,'');
 context.fetch=async url=>({ok:true,json:async()=>url.endsWith('/api/tests')?[{id:'7',started_at:'2026-10-06'}]:final});
 el('mode').value='server';
 vm.runInContext('report=null;job=null;running=false;',context);
 await events.DOMContentLoaded();
 assert.equal(JSON.parse(el('json').textContent).id,'7');
 assert.equal(el('zip').disabled,false);
 assert.equal(el('leftGoals').textContent,13);
 assert.equal(el('recent').disabled,false);
 console.log('Live polling and automatic recovery of saved results and ZIP passed.');
}).catch(error=>{console.error(error);process.exitCode=1;});
