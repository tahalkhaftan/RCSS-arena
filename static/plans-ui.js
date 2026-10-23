'use strict';
(() => {
 const el=id=>document.getElementById(id),query=new URLSearchParams(location.search);
 let selected=query.get('plan')==='pro'?'pro':'plus',account=null,busy=false;
 const names={plus:'پلاس',pro:'پرو'},prices={plus:30000,pro:50000};
 const number=value=>Number(value).toLocaleString('fa-IR');
 function message(text,status=''){el('billingMessage').hidden=false;el('billingMessage').textContent=text;el('billingMessage').dataset.status=status;}
 function render(){
  for(const plan of ['plus','pro']){el(plan+'Card').dataset.selected=String(selected===plan);el('select'+(plan==='plus'?'Plus':'Pro')).setAttribute('aria-pressed',String(selected===plan));}
  el('checkoutTitle').textContent='اشتراک یک‌ماههٔ '+names[selected];el('checkoutSummary').textContent=number(prices[selected])+' تومان · فعال‌سازی خودکار پس از پرداخت';
  if(!account)return;
  el('plansAccount').textContent=account.guest?'با حساب گوگل وارد شو و پلنت را انتخاب کن.':account.owner?'مالک سایت · دسترسی کامل':account.email;
  el('freePlanLink').textContent=account.guest?'شروع با گوگل':'بازگشت به آرنا';el('freePlanLink').href=account.guest?'/signup':'/';
  el('checkoutButton').disabled=busy||account.owner||(!account.guest&&!account.billing_ready)||(account.tier==='pro'&&selected==='plus');
  el('checkoutButton').textContent=busy?'در حال اتصال به درگاه…':account.owner?'دسترسی کامل داری':account.guest?'ورود با گوگل و ادامه':!account.billing_ready?'خرید آنلاین به‌زودی':account.tier===selected?'تمدید '+names[selected]:'خرید '+names[selected];
  el('checkoutHint').textContent=account.billing_ready?'پرداخت امن از طریق درگاه بانکی':'درگاه هنوز فعال نشده است؛ فعلاً می‌توانی رایگان بازی کنی.';
  el('renewalNote').textContent=account.tier==='plus'&&selected==='pro'?'روزهای باقی‌ماندهٔ اشتراکت حفظ می‌شود.':account.tier===selected?'یک ماه به اعتبار فعلی اضافه می‌شود.':account.tier==='pro'&&selected==='plus'?'اشتراک پرو فعال داری.':'';
 }
 for(const button of document.querySelectorAll('[data-plan]'))button.addEventListener('click',()=>{selected=button.dataset.plan;history.replaceState(null,'','/plans?plan='+selected);render();});
 el('checkoutButton').addEventListener('click',async()=>{
  if(!account||busy)return;
  if(account.guest){location.assign('/signup?next='+encodeURIComponent('/plans?plan='+selected));return;}
  if(account.owner||!account.billing_ready)return;
  busy=true;render();
  try{const response=await fetch('/api/billing/checkout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:selected})});const data=await response.json();if(!response.ok)throw Error(data.error||'ساخت پرداخت انجام نشد.');const url=new URL(data.url);if(url.origin!=='https://payment.zarinpal.com'||!url.pathname.startsWith('/pg/StartPay/'))throw Error('آدرس پرداخت معتبر نیست.');location.assign(url.href);}catch(error){message(error.message);busy=false;render();}
 });
 async function load(){try{const response=await fetch('/api/account',{credentials:'same-origin'});if(!response.ok)throw Error('دریافت حساب انجام نشد.');account=await response.json();render();const id=query.get('order');if(id&&/^[a-f0-9]{32}$/.test(id)){const r=await fetch('/api/billing/orders/'+id,{credentials:'same-origin'});if(r.ok){const order=await r.json();message(order.status==='paid'?'پرداخت موفق بود؛ اشتراکت فعال شد.':order.status==='cancelled'?'پرداخت لغو شد.':'پرداخت هنوز تأیید نشده است.',order.status);}}else if(query.has('payment'))message('پرداخت تأیید نشد. اگر وجه کسر شده، از لینک بازگشت درگاه دوباره تلاش کن.');}catch(error){message(error.message);}}
 render();load();
})();
