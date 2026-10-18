/* Observe actual browser X closure, not reload/pagehide. All requests stay same-origin. */
export function watch(onReopen){
 const views=new Map();let checking=false;
 window.addEventListener('message',e=>{
  if(e.origin!==location.origin||e.data?.type!=='arena-native-view'||!e.source)return;
  const {id,key}=e.data;if(!/^\d+$/.test(id)||!['formation','debug','window'].includes(key))return;
  views.set(id,{view:e.source,key});
 });
 setInterval(async()=>{
  if(checking)return;checking=true;
  try{for(const [id,item] of views){
   if(!item.view.closed)continue;views.delete(id);
   const response=await fetch('/native/window-close',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
   if(!response.ok)continue;
   // An unsaved editor can refuse closure. Keep its real confirmation reachable.
   setTimeout(async()=>{try{
    const r=await fetch('/native/windows',{credentials:'same-origin'}),state=await r.json();
    if(state.detached&&state.windows.some(w=>w.id===id))onReopen(id,item.key);
   }catch{}},1200);
  }}catch{}finally{checking=false;}
 },500);
}
export function announce(id,key){
 let target=window.opener;
 for(let depth=0;target&&depth<8;depth++){
  try{target.postMessage({type:'arena-native-view',id,key},location.origin);target=target.opener;}catch{break;}
 }
}
