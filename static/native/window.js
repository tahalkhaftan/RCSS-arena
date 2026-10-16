/* Browser windows are views of top-level widgets in ONE server-side Qt process. */
(()=>{
const $=id=>document.getElementById(id),query=new URLSearchParams(location.search),seen=new Set();let ident=null,own=null,busy=false,closed=false;
async function json(path,body){const r=await fetch('/native/'+path,body===undefined?{credentials:'same-origin'}:{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw Error(value.error||r.statusText);return value;}
function open(url,name){const popup=window.open(url,'arena-native-'+name,'popup=yes,width=1060,height=780,resizable=yes,scrollbars=no');if(!popup){$('status').textContent='مرورگر پنجرهٔ جدید را مسدود کرد؛ روی لینک ابزار بزن یا Popup این سایت را مجاز کن.';const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='بازکردن پنجرهٔ مستقل';$('fallback').replaceChildren(a);}return popup;}
for(const b of document.querySelectorAll('[data-tool]'))b.onclick=()=>open('/native/window.html?tool='+b.dataset.tool,b.dataset.tool);
function connect(record){ident=record.id;own=record;document.title=record.title+' — RCSS Arena';$('title').textContent=record.title;$('frame').src='/native/viewer.html?window='+encodeURIComponent(ident);$('frame').hidden=false;$('status').textContent='';}
function render(state){
 if(!state.detached){$('frame').src='about:blank';$('frame').hidden=true;$('status').textContent='نمایش مستقل بسته شد یا به سایت برگشت؛ مسابقه متوقف نشده است.';closed=true;return;}
 const current=state.windows.find(w=>w.id===ident);
 if(!current){$('frame').src='about:blank';$('frame').hidden=true;$('status').textContent='این پنجره در برنامه بسته شده است؛ ابزار را دوباره از دکمهٔ بالا باز کن.';return;}
 if($('frame').hidden)connect(current);
 for(const id of seen)if(!state.windows.some(w=>w.id===id))seen.delete(id);
 const links=[];
 for(const w of state.windows){const a=document.createElement('a');a.href='/native/window.html?id='+w.id;const name=['main','formation','debug'].includes(w.key)?w.key:w.id;a.target='arena-native-'+name;a.textContent=w.title;a.onclick=e=>{e.preventDefault();open(a.href,name);};links.push(a);
  if(w.id!==ident&&!seen.has(w.id)&&(w.owner===ident||(own.key==='main'&&!w.modal&&['formation','debug'].includes(w.key))))open(a.href,name);
  seen.add(w.id);
 }
 $('windows').replaceChildren(...links);
}
async function poll(){if(busy||closed||document.hidden)return;busy=true;try{render(await json('windows'));}catch(e){$('status').textContent=e.message;}finally{busy=false;}}
(async()=>{try{
 if(query.has('id')){const state=await json('windows');const record=state.windows.find(w=>w.id===query.get('id'));if(!record||!state.detached)throw Error('پنجرهٔ انتخاب‌شده بسته است؛ از دکمهٔ ابزار استفاده کن.');connect(record);}
 else connect(await json('window-tool',{tool:query.get('tool')||'main'}));
 seen.add(ident);await poll();
}catch(e){$('status').textContent=e.message;}})();setInterval(poll,1200);
window.addEventListener('pagehide',()=>{closed=true;$('frame').src='about:blank';});
})();
