'use strict';
(() => {
 const el=id=>document.getElementById(id);
 const google=el('googleLogin');
 let ready=false,redirecting=false;
 function modeForPath(){return location.pathname==='/signup'?'signup':'signin';}
 function renderMode(mode){
  const signup=mode==='signup';
  document.title=(signup?'ثبت‌نام':'ورود')+' | RCSS Arena';
  el('authTitle').textContent=signup?'به زمین بازی خوش اومدی.':'خوش برگشتی.';
  el('authSubtitle').textContent=signup?'حسابت را بساز؛ اولین بازی را شروع کن.':'وارد شو؛ بازی بعدی منتظر توست.';
  el('googleLabel').textContent=signup?'ثبت‌نام با گوگل':'ورود با گوگل';
  el('signInTab').toggleAttribute('aria-current',!signup);
  el('signUpTab').toggleAttribute('aria-current',signup);
  (signup?el('signUpTab'):el('signInTab')).setAttribute('aria-current','page');
  el('switchText').textContent=signup?'قبلاً حساب ساختی؟':'هنوز حساب نداری؟';
  const link=el('switchLink');
  link.textContent=signup?'وارد شو':'ثبت‌نام کن';
  link.href=signup?'/login':'/signup';
  link.dataset.authMode=signup?'signin':'signup';
 }
 document.querySelectorAll('[data-auth-mode]').forEach(link=>link.addEventListener('click',event=>{
  if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||event.button>0)return;
  event.preventDefault();
  history.pushState(null,'',link.getAttribute('href'));
  renderMode(link.dataset.authMode);
 }));
 window.addEventListener('popstate',()=>renderMode(modeForPath()));
 renderMode(modeForPath());
 if(new URLSearchParams(location.search).has('cancelled'))el('message').textContent='ورود لغو شد. دوباره امتحان کن.';
 async function checkGoogle(){
  try{
   const response=await fetch('/api/account',{credentials:'same-origin'});
   if(!response.ok)throw Error('ارتباط برقرار نشد. دوباره امتحان کن.');
   const account=await response.json();
   ready=account.google_ready===true;
   google.disabled=!ready;
   if(!ready)el('message').textContent='ورود گوگل هنوز تنظیم نشده است.';
  }catch(error){el('message').textContent=error.message;google.disabled=true;}
 }
 google.addEventListener('click',()=>{
  if(!ready||redirecting)return;
  redirecting=true;google.disabled=true;google.classList.add('is-loading');
  google.setAttribute('aria-busy','true');el('googleLabel').textContent='در حال اتصال به گوگل…';
  location.assign('/auth/google');
 });
 window.addEventListener('pageshow',event=>{if(event.persisted){redirecting=false;google.classList.remove('is-loading');google.removeAttribute('aria-busy');renderMode(modeForPath());checkGoogle();}});
 el('ownerForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=el('ownerSubmit'),message=el('ownerMessage');
  button.disabled=true;button.textContent='در حال ورود…';message.textContent='';
  try{
   const response=await fetch('/api/auth/owner',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:el('email').value.trim(),password:el('password').value})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'ورود انجام نشد.');
   el('password').value='';location.assign('/');
  }catch(error){message.textContent=error.message;}
  finally{button.disabled=false;button.textContent='ورود به مدیریت';}
 });
 const scene=document.querySelector('.scene');
 if(scene&&window.matchMedia('(pointer:fine)').matches&&!window.matchMedia('(prefers-reduced-motion:reduce)').matches){
  let animation=null,x=0,y=0;
  const apply=()=>{scene.style.setProperty('--mx',x+'px');scene.style.setProperty('--my',y+'px');animation=null;};
  scene.addEventListener('pointermove',event=>{const bounds=scene.getBoundingClientRect();x=(event.clientX-bounds.left-bounds.width/2)/45;y=(event.clientY-bounds.top-bounds.height/2)/50;if(animation===null)animation=requestAnimationFrame(apply);});
  scene.addEventListener('pointerleave',()=>{x=0;y=0;if(animation===null)animation=requestAnimationFrame(apply);});
 }
 checkGoogle();
})();
