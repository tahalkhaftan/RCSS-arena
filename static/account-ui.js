'use strict';
(() => {
 const el=id=>document.getElementById(id),dialog=el('settingsDialog');
 let account=null,refreshing=false;
 const fa=value=>Number(value).toLocaleString('fa-IR');
 const planName=tier=>({free:'رایگان',plus:'پلاس',pro:'پرو',owner:'مالک سایت'}[tier]||'رایگان');
 async function api(path,body){const response=await fetch(path,{credentials:'same-origin',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const result=await response.json();if(!response.ok)throw Error(result.error||'ارتباط برقرار نشد');return result;}
 const tabs=Array.from(document.querySelectorAll('[data-settings-tab]'));
 function tab(name){for(const button of tabs){const active=button.dataset.settingsTab===name;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;el(button.getAttribute('aria-controls')).hidden=!active;}}
 function open(name='usage'){tab(name);if(!dialog.open)dialog.showModal();}
 el('openSettings').addEventListener('click',()=>open());el('closeSettings').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',event=>{if(event.target===dialog){const b=dialog.getBoundingClientRect();if(event.clientX<b.left||event.clientX>b.right||event.clientY<b.top||event.clientY>b.bottom)dialog.close();}});
 for(const button of tabs){button.addEventListener('click',()=>tab(button.dataset.settingsTab));button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=tabs.indexOf(button),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowLeft'?1:-1)+tabs.length)%tabs.length;tab(tabs[next].dataset.settingsTab);tabs[next].focus();});}
 function render(){
  const paid=['plus','pro','owner'].includes(account.tier),exhausted=!paid&&account.remaining_games===0;
  const next=account.tier==='plus'?'pro':'plus',name=planName(next),url='/plans?plan='+next;
  el('accountStatus').textContent=account.guest?'مهمان':account.email;
  el('accountTier').textContent=planName(account.tier);el('currentPlan').textContent=planName(account.tier);
  el('accountLogin').hidden=!account.guest;el('accountSignup').hidden=!account.guest;el('accountLogout').hidden=account.guest;
  el('accountQuota').textContent=paid?(account.owner?'دسترسی کامل و رایگان':'تعداد نوبت تست نامحدود'):fa(account.remaining_games)+' بازی باقی مانده';
  el('usageMeter').hidden=paid;el('usageWindow').textContent=paid?'':account.guest?'سهمیهٔ مهمان':'۲۴ ساعت اخیر';
  const limit=account.quota_limit||30,used=paid?0:Math.max(0,limit-account.remaining_games);
  el('usageFill').style.width=Math.min(100,used/limit*100)+'%';el('usageMeter').setAttribute('aria-valuemax',String(limit));el('usageMeter').setAttribute('aria-valuenow',String(used));
  el('usageCount').textContent=paid?'بدون سقف روزانه':fa(used)+' از '+fa(limit)+' بازی';
  el('usageReset').textContent=paid?(account.owner?'':`معتبر تا ${new Date(account.expires*1000).toLocaleDateString('fa-IR')}`):account.quota_reset_at?`آزادشدن سهمیه از ${new Date(account.quota_reset_at*1000).toLocaleString('fa-IR',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}`:account.guest?'با ورود به گوگل، ۳۰ بازی در هر ۲۴ ساعت داشته باش.':'بازی‌های مصرف‌شده پس از ۲۴ ساعت آزاد می‌شوند.';
  el('planDescription').textContent=account.owner?'همهٔ قابلیت‌ها، بدون خرید':account.tier==='pro'?'همهٔ خروجی‌ها · تعداد نوبت نامحدود':account.tier==='plus'?'تا ۱۰۰ بازی در هر درخواست · تعداد نوبت نامحدود':'۳۰ بازی در هر ۲۴ ساعت';
  el('quotaNotice').hidden=!exhausted;el('quotaUpgrade').href=account.guest?'/signup':url;el('quotaUpgrade').textContent=account.guest?'ادامه با حساب گوگل':'ارتقا به '+name;
  const suggest=!['pro','owner'].includes(account.tier);
  el('upgradeBanner').hidden=!suggest;el('topUpgrade').hidden=!suggest;
  el('topUpgrade').textContent='ارتقا به '+name;el('topUpgrade').href=url;el('upgradeLink').href=url;el('upgradeLink').textContent='مشاهدهٔ '+name+' ↗';
  el('upgradeTitle').textContent=exhausted?'سهمیه‌ات تکمیل شده؛ با پلاس ادامه بده':next==='pro'?'همهٔ خروجی‌ها را با پرو داشته باش':'برای تست‌های بیشتر، پلاس';
  el('upgradeCopy').textContent=next==='pro'?'CSV، لاگ آفلاین و دیباگ؛ ماهانه ۵۰٬۰۰۰ تومان.':'نوبت تست نامحدود و تا ۱۰۰ بازی در هر درخواست؛ ماهانه ۳۰٬۰۰۰ تومان.';
  el('upgradeBanner').setAttribute('data-exhausted',String(exhausted));
  for(const id of ['offlineLogging','debugLogging']){el(id).disabled=!['pro','owner'].includes(account.tier);if(el(id).disabled)el(id).checked=false;}
 }
 async function refresh(){if(refreshing)return;refreshing=true;try{account=await api('/api/account');render();if(account.owner){const setup=await api('/api/setup');el('ownerSetup').hidden=false;el('setupStatus').textContent=setup.google_ready&&setup.billing_ready?'ورود گوگل و پرداخت آماده‌اند.':'تنظیمات موردنیاز سرور: '+(setup.missing.join('، ')||'آدرس اصلی سایت یا شناسهٔ درگاه را بررسی کن.');}}catch(error){el('settingsMessage').textContent=error.message;}finally{refreshing=false;}}
 el('accountLogout').addEventListener('click',async()=>{try{await api('/api/auth/logout',{});location.reload();}catch(error){el('settingsMessage').textContent=error.message;open();}});
 el('form').addEventListener('submit',event=>{if(account&&account.tier==='free'&&el('mode').value!=='demo'){const count=Number(el('rounds').value)*Number(el('games').value);if(count>account.remaining_games){event.preventDefault();event.stopImmediatePropagation();el('settingsMessage').textContent='سهمیهٔ باقی‌مانده '+fa(account.remaining_games)+' بازی است. تعداد را کمتر کن یا پلنت را ارتقا بده.';open();return;}}setTimeout(refresh,2000);},true);
 window.addEventListener('focus',refresh);window.addEventListener('storage',event=>{if(event.key==='arena-theme'&&typeof setTheme==='function')setTheme(event.newValue);});
 setInterval(refresh,30000);refresh();
})();
