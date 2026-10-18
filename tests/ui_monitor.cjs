const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},draw=new Proxy({}, {get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
function el(id){return nodes[id]||(nodes[id]={value:'',textContent:'',style:{},options:[],files:[],disabled:false,addEventListener(name,fn){this[name]=fn;},setAttribute(){},replaceChildren(){this.options=[];},add(option){this.options.push(option);}});}
el('pitch').getContext=()=>draw;el('pitch').width=1100;el('pitch').height=750;
el('monitorMode').value='live';el('monitorSpeed').value='1';
const context={document:{getElementById:el,querySelector:()=>el('track'),querySelectorAll:()=>[]},window:{addEventListener(){}},location:{protocol:'https:',origin:'https://arena.test'},URL,AbortController,console,Option:function(text,value){this.text=text;this.value=value;},setTimeout:()=>1,clearTimeout(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/index.html','utf8').split('<script>')[1].split('</script>')[0],context);
const frame={cycle:123,mode:'3',names:['A','B'],score:[3,1],ball:[0,0],players:[['l',1,-40,0,90,true]]};
const state={id:'7',total:2,status:'running',config:{rounds:1,games_per_round:2},matches:[{round:1,game:1,status:'completed',left_score:2,right_score:1}],progress:{round:1,game:2,frame,left_score:3,right_score:1}};
context.fixture=state;
vm.runInContext("job={id:'7',api:'https://arena.test'};report=fixture;render()",context);
assert.equal(el('monitorMatch').options.length,2);assert.equal(el('monitorMatch').value,'1/2');assert.equal(el('monitorScore').textContent,'3 : 1');
(async()=>{
 let resolve;context.fetch=()=>new Promise(r=>resolve=r);
 el('monitorMatch').value='1/1';el('monitorMatch').change();
 el('monitorMatch').value='1/2';el('monitorMatch').change();
 resolve({ok:true,json:async()=>({frames:[frame],step_ms:100,final_score:[2,1]})});
 for(let i=0;i<8;i++)await Promise.resolve();
 assert.equal(el('monitorScore').textContent,'3 : 1','A late replay must not replace the selected live game');
 context.fetch=async()=>({ok:true,json:async()=>({frames:[{...frame,score:[0,0]},{...frame,score:[2,1],cycle:6000}],step_ms:100,final_score:[2,1]})});
 el('monitorMatch').value='1/1';el('monitorMatch').change();
 for(let i=0;i<8;i++)await Promise.resolve();
 assert.equal(el('monitorScore').textContent,'0 : 0');assert.equal(el('monitorSeek').max,1);
 el('monitorSeek').value='1';el('monitorSeek').input();assert.equal(el('monitorScore').textContent,'2 : 1');
 assert.equal(state.matches[0].left_score,2,'Monitor must not change recorded results');
 // Direct stream updates the monitor independently of ten-second report polling.
 const streams=[];context.EventSource=function(url){this.url=url;this.close=()=>this.closed=true;streams.push(this);};
 el('monitorMatch').value='1/2';el('monitorMatch').change();
 vm.runInContext('updateMonitor()',context);
 assert.equal(streams.length,1);
 streams[0].onmessage({data:JSON.stringify({frames:[{round:1,game:2,frame:{...frame,cycle:999,score:[4,1]},captured_at:Date.now()/1000}]})});
 assert.equal(el('monitorScore').textContent,'4 : 1');assert.equal(el('monitorBadge').textContent,'پخش مستقیم');
 vm.runInContext('updateMonitor()',context);
 assert.equal(streams.length,1,'Report polls must not reconnect the live stream');
 assert.equal(el('monitorScore').textContent,'4 : 1','A stale periodic report must not overwrite the live score');
 vm.runInContext("report.status='completed';updateMonitor()",context);
 assert.equal(streams[0].closed,true);
 console.log('Monitor selection, replay, direct live frames and fallback isolation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
