const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},draw=new Proxy({}, {get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
function el(id){return nodes[id]||(nodes[id]={value:'',textContent:'',className:'',style:{},files:[],options:[],disabled:false,addEventListener(n,f){this[n]=f},setAttribute(){},replaceChildren(){this.options=[]},add(o){this.options.push(o)}})}
el('pitch').getContext=()=>draw;el('pitch').width=1100;el('pitch').height=750;
el('monitorMode').value='live';el('monitorSpeed').value='1';
const ctx={document:{getElementById:el,querySelector:()=>el('track'),querySelectorAll:()=>[]},window:{addEventListener(){}},location:{protocol:'https:',origin:'https://test'},URL,AbortController,console,Option:function(t,v){this.text=t;this.value=v},setTimeout,clearTimeout};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/index.html','utf8').split('<script>')[1].split('</script>')[0],ctx);
const rcg='ULG5\n(server_param (simulator_step 100))\n(team 0 Blue Orange 0 0)\n(show 1 (pm 3) ((b) 1 2 0 0) ((l 1) 0 9 -40 0 0 0 90) ((r 9) 0 1 20 10 0 0 0))\n(team 6000 Blue Orange 2 1)\n(show 6000 ((b) 0 0 0 0) ((l 1) 0 9 -40 0 0 0 90))\n(playmode 6000 time_over)\n';
(async()=>{
 for(const header of ['ULG4','ULG5','ULG6','\ufeffULG6']){const data=await ctx.parseLocalRCG(rcg.replace('ULG5',header));assert.equal(data.frames[0].players.length,2);assert.equal(data.final_score.join(':'),'2:1');}
 const parsed=await ctx.parseLocalRCG(rcg.replace('ULG5','ULG6'));assert.equal(parsed.frames.length,2);assert.equal(parsed.frames[0].players.length,2);assert.equal(parsed.frames[0].players[0][5],true);assert.equal(parsed.final_score.join(':'),'2:1');
 await assert.rejects(ctx.parseLocalRCG('ULG3\n'),/ULG4/);
 await assert.rejects(ctx.parseLocalRCG('ULG5\n'),/داده/);
 el('monitorSource').value='file';el('monitorSource').change();
 el('monitorFile').files=[{name:'match.rcg',size:rcg.length,text:async()=>rcg.replace('ULG5','ULG6')}];await el('monitorFile').change();
 assert.equal(el('monitorScore').textContent,'0 : 0');assert.equal(el('monitorSeek').max,1);
 vm.runInContext("report={id:'server',status:'running',matches:[],config:{},total:1};updateMonitor()",ctx);
 assert.equal(el('monitorScore').textContent,'0 : 0','Server updates must not replace a local replay');
 el('monitorSeek').value='1';el('monitorSeek').input();assert.equal(el('monitorScore').textContent,'2 : 1');assert.match(el('monitorInfo').textContent,/match.rcg/);
 el('monitorPlay').click();assert.equal(el('monitorPlay').textContent,'توقف موقت ❚❚');el('monitorPlay').click();
 el('monitorFile').files=[{name:'bad.rcg',size:5,text:async()=>'ULG3'}];await el('monitorFile').change();assert.equal(el('monitorBadge').textContent,'خطای فایل RCG');
 vm.runInContext('report=null',ctx);el('monitorSource').value='server';el('monitorSource').change();assert.equal(el('monitorBadge').textContent,'منتظر انتخاب تست');
 console.log('PASS: local RCG parsing, upload, playback, seeking, invalid files and server isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
