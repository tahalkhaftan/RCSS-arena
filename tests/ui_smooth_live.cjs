const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},pending=new Map(),streams=[];let counter=0,clock=100000;
function el(id){return nodes[id]||(nodes[id]={value:'',textContent:'',style:{},options:[],files:[],addEventListener(n,f){this[n]=f},setAttribute(){},replaceChildren(){this.options=[]},add(o){this.options.push(o)}})}
el('pitch').getContext=()=>new Proxy({},{get:()=>()=>{}});el('monitorMode').value='live';
const ctx={document:{getElementById:el,querySelector:()=>el('track'),querySelectorAll:()=>[]},window:{addEventListener(){}},location:{protocol:'https:',origin:'https://test'},URL,AbortController,console,Option:function(t,v){this.text=t;this.value=v},Date:class extends Date{static now(){return clock}},setTimeout:()=>1,clearTimeout(){},requestAnimationFrame:f=>{pending.set(++counter,f);return counter},cancelAnimationFrame:id=>pending.delete(id),EventSource:function(){streams.push(this);this.close=()=>{}},drawn:[]};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/index.html','utf8').split('<script>')[1].split('</script>')[0],ctx);
vm.runInContext("drawPitch=f=>drawn.push(f);job={id:'7',api:'https://test'};report={id:'7',status:'running',total:1,matches:[],config:{rounds:1,games_per_round:1},progress:{round:1,game:1}};render()",ctx);
const a={cycle:100,mode:'3',names:['A','B'],score:[0,0],ball:[0,0],players:[['l',1,0,0,179,false]]},b={...a,cycle:105,ball:[10,0],players:[['l',1,10,0,-179,false]]};
const mid=ctx.blendLiveFrames(a,b,.5);assert.equal(mid.ball[0],5);assert.equal(mid.players[0][2],5);assert.equal(mid.players[0][4],180);
assert.equal(ctx.blendLiveFrames(a,{...b,mode:'goal_l',score:[1,0]},.5),a,'Goals must not interpolate teleporting positions');
assert.equal(ctx.smoothFrame([{stamp:0,frame:a},{stamp:2000,frame:b}],1000),a,'No invented movement across an outage');
streams[0].onmessage({data:JSON.stringify({frames:[{round:1,game:1,frame:a,captured_at:99.5},{round:1,game:1,frame:b,captured_at:100}]})});
assert.equal(el('monitorBadge').textContent,'پخش مستقیم');assert.equal(pending.size,1);
let [id,tick]=pending.entries().next().value;pending.delete(id);tick();assert.equal(ctx.drawn.at(-1).ball[0],5,'RAF draws between the two real received frames');
clock+=100;[id,tick]=pending.entries().next().value;pending.delete(id);tick();assert.equal(ctx.drawn.at(-1).ball[0],7);
el('monitorSource').value='file';el('monitorSource').change();assert.equal(pending.size,0,'File playback cancels live animation');
console.log('PASS: buffered live animation, intermediate positions, short angle turns, goal boundaries, outages and source switching');
