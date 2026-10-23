'use strict';
(() => {
 const el=id=>document.getElementById(id);
 let account=null;
 async function api(path,body){const response=await fetch(path,{credentials:'same-origin',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const result=await response.json();if(!response.ok)throw Error(result.error||'ارتباط برقرار نشد');return result;}
 const fa=value=>Number(value).toLocaleString('fa-IR');
 async function refresh(){
  try{
   account=await api('/api/account');
   el('accountStatus').textContent=account.owner?'مالک سایت · دسترسی کامل و رایگان':account.guest?'حالت مهمان':account.email;
   el('accountQuota').textContent=['pro','plus','owner'].includes(account.tier)?(account.owner?'بدون نیاز به خرید اشتراک':`${account.tier==='pro'?'پرو':'پلاس'} · معتبر تا ${new Date(account.expires*1000).toLocaleDateString('fa-IR')} · تعداد نوبت نامحدود`):`${fa(account.remaining_runs)} نوبت و ${fa(account.remaining_games)} بازی رایگان باقی مانده`;
   el('accountLogin').hidden=!account.guest;el('accountLogout').hidden=account.guest;
   el('paymentForm').hidden=account.owner;el('adminPayments').hidden=!account.owner;
   for(const id of ['offlineLogging','debugLogging']){el(id).disabled=!['pro','owner'].includes(account.tier);if(el(id).disabled)el(id).checked=false;}
   if(account.owner)await loadPending();
   else if(!account.guest){const rows=await api('/api/payments');el('paymentHistory').replaceChildren();for(const row of rows){const p=document.createElement('p');p.textContent=`${row.plan==='pro'?'پرو':'پلاس'} · ${row.reference} · ${{pending:'در انتظار بررسی',approved:'تأیید شده',rejected:'رد شده'}[row.status]}`;el('paymentHistory').append(p);}}
  }catch(error){el('accountStatus').textContent=error.message;}
 }
 async function loadPending(){
  const rows=await api('/api/admin/payments');el('pendingPayments').replaceChildren();
  if(!rows.length)el('pendingPayments').textContent='پرداختی در انتظار بررسی نیست.';
  for(const row of rows){const box=document.createElement('div');box.className='note';const text=document.createElement('p');text.textContent=`${row.email} · ${row.plan==='pro'?'پرو':'پلاس'} · ${fa(row.amount)} تومان · پیگیری: ${row.reference}`;box.append(text);
   for(const [action,label] of [['approve','تأیید واریز و فعال‌سازی'],['reject','رد درخواست']]){const button=document.createElement('button');button.type='button';button.className='btn';button.textContent=label;button.addEventListener('click',async()=>{button.disabled=true;try{await api(`/api/admin/payments/${row.id}/${action}`,{});await loadPending();}catch(error){el('paymentMessage').textContent=error.message;button.disabled=false;}});box.append(button);}el('pendingPayments').append(box);
  }
 }
 el('accountLogout').addEventListener('click',async()=>{try{await api('/api/auth/logout',{});location.reload();}catch(error){el('paymentMessage').textContent=error.message;}});
 el('paymentForm').addEventListener('submit',async event=>{event.preventDefault();const button=el('submitPayment');button.disabled=true;try{if(!account||account.guest){location.assign('/login');return;}const result=await api('/api/payments',{plan:el('paymentPlan').value,reference:el('paymentReference').value.trim()});el('paymentMessage').textContent=result.message;el('paymentReference').value='';await refresh();}catch(error){el('paymentMessage').textContent=error.message;}finally{button.disabled=false;}});
 el('refreshPayments').addEventListener('click',()=>refresh());
 el('form').addEventListener('submit',()=>setTimeout(refresh,2000));
 window.addEventListener('focus',refresh);
 refresh();
})();
