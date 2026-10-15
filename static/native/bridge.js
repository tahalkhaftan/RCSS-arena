/* Native files and live editor state exposed as ordinary site controls. */
(()=>{
const $=id=>document.getElementById(id),status=$('nativeStatus');let history=new Map(),saved=null,lastGames='',lastFormation='',polling=false;
const text=(fa,en)=>document.documentElement.lang==='en'?en:fa;
async function post(path,body={}){const r=await fetch('/native/'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw Error(value.error||r.statusText);return value;}
async function read(url){const r=await fetch(url,{credentials:'include'});const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data;}
async function ready(){await window.arenaNative.start();}
async function task(button,fn){button.disabled=true;try{await fn();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}}
function current(){return saved|| (job&&report?{id:job.id,api:job.api,state:report}:null);}
function games(){
 const context=current(),select=$('nativeGameChoice');if(!context){if(select.options.length!==1||select.options[0].value)select.replaceChildren(new Option(text('ابتدا تستی را شروع یا بازیابی کن','Start or restore a test first'),''));return;}
 const state=context.state,rounds=Number(state.config?.rounds||1),count=Number(state.config?.games_per_round||state.total||1),rows=[];
 for(let r=1;r<=rounds&&rows.length<500;r++)for(let g=1;g<=count&&rows.length<500;g++){
  const m=(state.matches||[]).find(m=>m.round===r&&m.game===g),live=state.status==='running'&&state.progress?.round===r&&state.progress?.game===g;
  rows.push({key:r+'/'+g,label:text('دور ','Round ')+r+text(' — بازی ',' — Game ')+g+' · '+(m?m.left_team+' '+(m.left_score??'—')+' : '+(m.right_score??'—')+' '+m.right_team:live?text('زنده','Live'):text('در انتظار','Queued'))});
 }
 const signature=JSON.stringify([context.id,rows]);if(signature===lastGames)return;lastGames=signature;const previous=select.value;
 select.replaceChildren(...rows.map(row=>new Option(row.label,row.key)));
 const progressKey=state.progress?state.progress.round+'/'+state.progress.game:'';
 select.value=rows.some(row=>row.key===previous)?previous:rows.some(row=>row.key===progressKey)?progressKey:rows[0]?.key||'';
}
$('nativeLoadTests').onclick=()=>task($('nativeLoadTests'),async()=>{
 const api=serviceURL()+($('mode').value==='personal'?'/personal':'');const rows=await read(api+'/api/tests');history.clear();const select=$('nativeTestChoice');select.replaceChildren(new Option(text('تست فعلی','Current test'),'current'));
 saved=null;lastGames='';
 for(const row of rows){const key=String(row.id);history.set(key,{id:key,api});select.add(new Option((row.started_at||'')+' · '+key+' · '+row.status,key));}games();
});
$('nativeTestChoice').onchange=async()=>{
 const chosen=$('nativeTestChoice').value;if(chosen==='current'){saved=null;lastGames='';games();return;}
 const context=history.get(chosen);if(!context)return;
 try{const state=await read(context.api+'/api/tests/'+encodeURIComponent(context.id));if($('nativeTestChoice').value!==chosen)return;saved={...context,state};lastGames='';games();}catch(e){status.textContent=e.message;}
};
$('nativePlayGame').onclick=()=>task($('nativePlayGame'),async()=>{
 const context=current(),key=$('nativeGameChoice').value;if(!context||!key)throw Error(text('ابتدا یک بازی انتخاب کن.','Choose a game first.'));
 const [r,g]=key.split('/').map(Number),state=await read(context.api+'/api/tests/'+encodeURIComponent(context.id));context.state=state;
 const live=state.status==='running'&&state.progress?.round===r&&state.progress?.game===g;
 await ready();status.textContent=text('در حال بازکردن بازی انتخابی…','Opening selected game…');const personal=String(context.api).replace(/\/$/,'').endsWith('/personal');
 if(live)await post('connect',{id:(personal?'personal:':'')+context.id});
 else {if(!(state.matches||[]).some(m=>m.round===r&&m.game===g))throw Error(text('این بازی هنوز اجرا نشده است.','This game has not run yet.'));await post('open-game',{id:context.id,execution:personal?'personal':'cloud',round:r,game:g});}
 status.textContent=text('بازی انتخاب‌شده: ','Selected game: ')+key+(live?' · LIVE':' · RCG');await window.arenaNative.refreshFiles();
});
async function upload(input,kind){const file=input.files?.[0];if(!file)return;await ready();status.textContent=text('در حال ارسال: ','Uploading: ')+file.name;const r=await fetch('/native/upload?name='+encodeURIComponent(file.name),{method:'POST',credentials:'same-origin',body:file});const data=await r.json();if(!r.ok)throw Error(data.error);await post('open-file',{name:data.name,kind});status.textContent=file.name;input.value='';await window.arenaNative.refreshFiles();await preview();}
$('nativeReplayUpload').onchange=()=>task($('nativePlayGame'),()=>upload($('nativeReplayUpload'),'replay'));
$('nativeFormationUpload').onchange=()=>task($('nativeFormationNew'),()=>upload($('nativeFormationUpload'),'formation'));
$('nativeFormationNew').onclick=()=>task($('nativeFormationNew'),async()=>{await ready();await post('formation/new');await preview();});
$('nativeFormationExport').onclick=()=>task($('nativeFormationExport'),async()=>{
 await ready();const result=await post('formation/export',{name:$('nativeFormationName').value.trim()||'formation.conf'});
 const link=document.createElement('a');link.href='/native/download/'+encodeURIComponent(result.name);link.download=result.name;link.click();await window.arenaNative.refreshFiles();await preview();
});
function paint(data){
 $('nativeFormationExport').disabled=!data.available;
 $('nativeFormationNote').textContent=data.available?(data.file||text('فرمیشن جدید','New formation'))+' · '+data.samples+text(' نمونه',' samples')+(data.modified?text(' · تغییرات ذخیره‌نشده',' · Unsaved changes'):''):text('فرمیشن را ایجاد یا باز کن؛ چیدمان واقعی ویرایشگر اینجا ظاهر می‌شود.','Create or open a formation; the actual editor layout will appear here.');
 const c=$('nativeFormationCanvas'),ctx=c.getContext('2d'),W=c.width,H=c.height;ctx.clearRect(0,0,W,H);$('nativeFormationTable').replaceChildren();if(!data.available)return;
 const sx=(W-44)/105,sy=(H-36)/68,X=x=>22+(x+52.5)*sx,Y=y=>18+(y+34)*sy;
 ctx.fillStyle='#126c47';ctx.fillRect(0,0,W,H);ctx.strokeStyle='#e0f4e7';ctx.lineWidth=1;ctx.strokeRect(X(-52.5),Y(-34),105*sx,68*sy);ctx.beginPath();ctx.moveTo(X(0),Y(-34));ctx.lineTo(X(0),Y(34));ctx.stroke();ctx.beginPath();ctx.ellipse(X(0),Y(0),9.15*sx,9.15*sy,0,0,Math.PI*2);ctx.stroke();
 ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='bold 12px Arial';
 for(const p of data.players||[]){ctx.fillStyle='#ffd166';ctx.beginPath();ctx.arc(X(p.x),Y(p.y),10,0,Math.PI*2);ctx.fill();ctx.fillStyle='#172333';ctx.fillText(String(p.number),X(p.x),Y(p.y));const row=document.createElement('tr');for(const value of [p.number,p.role,Number(p.x).toFixed(2),Number(p.y).toFixed(2)]){const td=document.createElement('td');td.textContent=value;row.append(td);}$('nativeFormationTable').append(row);}
 if(data.ball){ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(X(data.ball[0]),Y(data.ball[1]),5,0,Math.PI*2);ctx.fill();}
}
async function preview(){if(polling||!window.arenaNative?.isOpen()||document.hidden)return;polling=true;try{const data=await read('/native/formation'),signature=JSON.stringify(data);if(signature!==lastFormation){lastFormation=signature;paint(data);}}catch{}finally{polling=false;}}
window.addEventListener('arena-report',games);window.addEventListener('arena-language',()=>{lastGames='';lastFormation='';games();preview();});setInterval(preview,1200);games();
})();
