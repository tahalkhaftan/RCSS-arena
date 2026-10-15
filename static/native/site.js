/* The visible monitor is an original Qt desktop, not a canvas reimplementation. */
(()=>{
const byId=id=>document.getElementById(id),status=byId('nativeStatus');
let opened=false;
async function api(path,body){const r=await fetch('/native/'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data;}
function message(text){status.textContent=text;}
async function start(){if(opened)return;message('در حال راه‌اندازی SoccerWindow2…');await api('start');byId('nativeFrame').src='/native/viewer.html';byId('nativeFrame').hidden=false;opened=true;message('SoccerWindow2 — نسخهٔ اصلی');}
async function task(fn){try{await fn();}catch(e){message(e.message);}}
byId('nativeStart').onclick=()=>task(start);
byId('nativeConnect').onclick=()=>task(async()=>{if(!job?.id)throw Error('ابتدا یک تست را شروع یا بازیابی کن.');await start();await api('connect',{id:(String(job.api||'').replace(/\/$/,'').endsWith('/personal')?'personal:':'')+job.id});message('اتصال به سرور مسابقه؛ ممکن است تأخیر داشته باشد.');});
byId('nativeCloseTool').onclick=()=>task(()=>api('close-tool'));
byId('nativeStop').onclick=()=>task(async()=>{byId('nativeFrame').src='about:blank';byId('nativeFrame').hidden=true;opened=false;await api('stop');message('مانیتور بسته شد؛ مسابقه ادامه دارد.');});
byId('nativeFull').onclick=()=>byId('nativeFrame').requestFullscreen?.();
byId('nativeUpload').onchange=()=>task(async()=>{
 const files=Array.from(byId('nativeUpload').files||[]);if(!files.length)return;await start();
 for(const f of files){message('در حال ارسال: '+f.name);const open=files.length===1&&/\.rcg(?:\.gz)?$/i.test(f.name);const r=await fetch('/native/upload?name='+encodeURIComponent(f.name)+(open?'&open=1':''),{method:'POST',credentials:'same-origin',body:f});const data=await r.json();if(!r.ok)throw Error(data.error||'Upload failed');}
 message('فایل‌ها آماده‌اند؛ مسیر در برنامه: /tmp/arena-desktop/files');await listFiles();byId('nativeUpload').value='';
});
async function listFiles(){const r=await fetch('/native/files',{credentials:'same-origin'});const data=await r.json();if(!r.ok)throw Error(data.error);const target=byId('nativeFiles');target.replaceChildren();for(const name of data){const a=document.createElement('a');a.textContent=name;a.href='/native/download/'+encodeURIComponent(name);a.download=name;target.append(a);}}
byId('nativeRefreshFiles').onclick=()=>task(listFiles);
window.addEventListener('message',e=>{if(e.origin===location.origin&&e.source===byId('nativeFrame').contentWindow&&e.data?.type==='native-connected')message('SoccerWindow2 — نسخهٔ اصلی');});
// User-entered team names, results JSON, file names and native Qt text are never translated.
const words={
'شخصی‌سازی ▾':'Customize ▾','رنگ':'Color','زبان':'Language','تم روشن':'Light','تم مشکی':'Dark',
'تست مسابقه دو تیم':'Two-team match tests','تیم سمت چپ':'Left team','تیم سمت راست':'Right team','نام تیم':'Team name',
'آپلود باینری':'Upload binary','آپلود سورس و بیلد':'Upload source & build','پوشهٔ اجرا بعد از استخراج':'Working folder after extraction','دستور شروع':'Start command',
'آپلود فایل تیم چپ':'Upload left team ZIP','آپلود فایل تیم راست':'Upload right team ZIP','انتخاب تیم آماده':'Choose preset team',
'تنظیمات تست':'Test settings','تعداد دورهای تست':'Rounds','تعداد بازی در هر دور':'Games per round','حالت مسابقه':'Match speed',
'شروع تست':'Start test','توقف تست':'Stop test','بازیابی آخرین تست':'Restore latest test','تعداد کل مسابقات:':'Total matches:',
'گزارش تست':'Test report','عملکرد تیم‌ها':'Team performance','دانلود ZIP لاگ‌ها':'Download logs ZIP','کپی JSON':'Copy JSON','دانلود JSON':'Download JSON',
'بازی کامل‌شده':'Completed','برد تیم چپ':'Left wins','برد تیم راست':'Right wins','مساوی':'Draws','گل تیم چپ':'Left goals','گل تیم راست':'Right goals',
'میانگین مالکیت چپ ٪':'Average left possession %','میانگین مالکیت راست ٪':'Average right possession %','میانگین توپ آزاد ٪':'Average free ball %','میانگین کنترل مشترک ٪':'Average shared control %',
'شوت در چارچوب':'Shots on target','شوت خارج از چارچوب':'Shots off target','شوت مسدودشده':'Blocked shots','مهار ثبت‌شدهٔ شوت':'Recorded saves','پاس ناموفق':'Unsuccessful passes','پاس صحیح':'Completed passes','دقت پاس':'Pass accuracy','آفساید':'Offsides','کرنر':'Corners','شوت':'Shots','پاس':'Passes',
'بیلد':'Build','خطای بیلد':'Build error','اجرای مسابقات':'Match execution','سرور شخصی اوبونتو':'Personal Ubuntu server',
'اجرای SoccerWindow2':'Open SoccerWindow2','اتصال به مسابقه':'Connect to match','بستن پنجرهٔ ابزار ×':'Close tool window ×','تمام‌صفحه':'Full screen','بستن مانیتور':'Close monitor',
'فایل RCG، دیباگ یا فرمیشن':'RCG, debug or formation files','فایل‌های محیط مانیتور':'Desktop files','تازه‌سازی':'Refresh',
'نمایش اصلی SoccerWindow2':'Original SoccerWindow2','هنوز راه‌اندازی نشده':'Not started',
'نسخهٔ اصلی Qt روی سرور اجرا می‌شود. فایل‌ها برای بازشدن در برنامه به فضای موقت مانیتور ارسال می‌شوند.':'The original Qt app runs on the server. Uploaded files are stored in the temporary monitor workspace.',
'پنجره‌های ویرایشگر ضربدر خودشان را دارند. برای خروج از ابزار فعال از × هم می‌توانی استفاده کنی.':'Editor windows have their own close buttons. You can also use × to close the active tool.',
'محیط بین کاربران مجاز مشترک است؛ منوهای برنامهٔ اصلی انگلیسی هستند.':'Authorized users share this desktop; the original application menus are in English.',
'پس از بستن صفحه، برای دیدن نتیجهٔ تست قبلی از این دکمه استفاده کن.':'Use this button to restore the previous test after reopening the page.',
'پس از شروع، آمار و JSON نتایج اینجا نمایش داده می‌شوند.':'Statistics and results JSON appear here after a test starts.',
'ZIP لاگ‌های واقعی بعد از پایان تست و اتصال سرویس قابل دانلود است.':'The logs ZIP becomes available after the test finishes and publication completes.',
'بازی زنده':'Live match','بدون داده':'No data','تست کامل شد':'Test completed',
'در حال راه‌اندازی SoccerWindow2…':'Starting SoccerWindow2…','اتصال به سرور مسابقه؛ ممکن است تأخیر داشته باشد.':'Connecting to match server; delay is possible.',
'مانیتور بسته شد؛ مسابقه ادامه دارد.':'Monitor closed; the match continues.','ابتدا یک تست را شروع یا بازیابی کن.':'Start or restore a test first.',
'دریافت لاگ آفلاین بازیکن‌ها و دیتاست CSV':'Collect offline player logs and CSV dataset','دریافت لاگ دیباگ تیم‌ها':'Collect team debug logs'
};
Object.assign(words,{"تست مسابقهٔ دو تیم": "Two-team match tests", "تیم‌ها را انتخاب کن؛ تنظیم کن و تست را شروع کن.": "Choose teams, configure, and start your test.", "سرویس واقعی": "Live service", "حالت اجرا و اتصال به سرویس": "Execution mode and service connection", "حالت اجرا": "Execution mode", "آزمایشی (نتایج ساختگی)": "Demo (synthetic results)", "اجرای ابری — GitHub Actions": "Cloud — GitHub Actions", "اجرای روی Ubuntu شخصی": "Personal Ubuntu worker", "آدرس سرویس": "Service URL", "اتصال Ubuntu شخصی": "Connect Ubuntu worker", "Worker هنوز متصل نیست": "Worker is not connected", "راهنمای نصب روی Ubuntu": "Ubuntu setup guide", "آپلود تیم شخصی": "Upload your team", "فایل ZIP شامل باینری، اسکریپت و فایل‌های لازم": "ZIP containing binaries, scripts and required files", "نوع بیس": "Base type", "دانش‌آموزی": "School base", "دانشجویی": "University base", "پوشهٔ اصلی سورس داخل ZIP": "Source root in ZIP", "ارور ▾": "Errors ▾", "دریافت خروجی کامل": "Get full build output", "سریع — synch_mode": "Fast — synch_mode", "معمولی": "Normal", "دریافت لاگ آفلاین (.ocl) و CSV آموزشی": "Collect offline logs (.ocl) and training CSV", "دریافت و نمایش دیباگ تیم‌ها (.log / .dcl)": "Collect and display team debug (.log / .dcl)", "برای تیم‌های سازگار؛ فقط اطلاعاتی نمایش داده می‌شود که کد تیم ثبت می‌کند.": "Compatible clients only; displays records emitted by the team code.", "اگر اسکریپت پورت می‌گیرد:": "For scripts that take a port:", "؛ پورت مربی آنلاین:": "; online coach port:", ". دستور باید تمام ۱۱ بازیکن را اجرا کند.": ". The command must start all 11 players.", "آمادهٔ شروع": "Ready", "پیشرفت مسابقه پس از اتصال تیم‌ها نمایش داده می‌شود.": "Progress appears after the teams connect.", "ارور تیم چپ ▾": "Left team errors ▾", "ارور تیم راست ▾": "Right team errors ▾", "دریافت دوبارهٔ خروجی کامل": "Reload full output", "گل": "Goals", "مالکیت توپ": "Ball possession", "در حالت واقعی، فایل‌ها به سرویس انتخاب‌شده ارسال می‌شوند. این سایت به‌تنهایی سرور RCSS را اجرا نمی‌کند.": "In live mode, files are sent to the selected service. Matches run on the configured worker.", "Worker باید روی Ubuntu روشن بماند. سرور، تیم‌ها و فایل‌ها روی سیستم خودت اجرا و ذخیره می‌شوند. مانیتور محلی: 127.0.0.1:6000": "Keep the Ubuntu worker running. The server, teams and logs stay on your machine. Local monitor: 127.0.0.1:6000", "مسابقه‌ها روی GitHub Actions اجرا می‌شوند؛ فایل تیم‌ها و نتایج در مخزن خصوصیِ مدیر این سایت ذخیره می‌شوند. فقط تیم‌های مورد اعتماد را اجرا کن. سقف درخواست: ۵۰۰ بازی.": "Matches run on GitHub Actions. Team uploads and results are stored in the site administrator’s private repository. Run trusted teams only. Maximum: 500 games.", "در حالت سریع، تعداد سایکل‌ها تغییر نمی‌کند؛ اجرای آن به پشتیبانی دو تیم از synch_mode وابسته است.": "Fast mode preserves the match cycle count and requires synch_mode support from both teams.", "≈ برآورد از رویدادهای تشخیص‌داده‌شده؛ آمار زنده ممکن است ناقص باشد. «—» یعنی دادهٔ کافی نداریم. مهار دروازه‌بان از تفاضل شوت و گل محاسبه نمی‌شود.": "≈ Estimated from detected events; live statistics may be incomplete. “—” means insufficient data. Saves are not calculated by subtracting goals from shots."});
let language='fa';const originals=new WeakMap(),skip='script,style,pre,textarea,#nativeFiles,#nativeLegacy,input,.score-team';
function translateText(node){if(node.parentElement?.closest(skip))return;const text=node.nodeValue;if(!text.trim())return;let entry=originals.get(node);if(!entry||text!==entry.output&&text!==entry.original)entry={original:text};const trim=entry.original.trim();entry.output=language==='en'&&words[trim]?entry.original.replace(trim,words[trim]):entry.original;if(node.nodeValue!==entry.output)node.nodeValue=entry.output;originals.set(node,entry);}
function translate(){const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode())translateText(n);}
function setLanguage(value){language=value==='en'?'en':'fa';document.documentElement.lang=language;document.documentElement.dir=language==='en'?'ltr':'rtl';byId('languageFa').setAttribute('aria-pressed',String(language==='fa'));byId('languageEn').setAttribute('aria-pressed',String(language==='en'));try{localStorage.setItem('arena-language',language);}catch{}translate();}
byId('languageFa').onclick=()=>setLanguage('fa');byId('languageEn').onclick=()=>setLanguage('en');
let scheduled=false;new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;translate();});}).observe(document.body,{childList:true,characterData:true,subtree:true});
let saved='fa';try{saved=localStorage.getItem('arena-language')||'fa';}catch{}setLanguage(saved);window.setArenaLanguage=setLanguage;
})();
