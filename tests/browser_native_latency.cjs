const {chromium}=require('playwright'),assert=require('node:assert/strict');let browser;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1024,height:720},httpCredentials:{username:'latency-test',password:'latency-test-only'}}),page=await context.newPage();
 const base='http://127.0.0.1:18080';let ready=false;
 for(let i=0;i<80;i++){try{const r=await context.request.get(base+'/healthz',{timeout:1000});if(r.ok()){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,250));}assert.ok(ready,'native test server unavailable');
 const started=await context.request.post(base+'/native/start',{data:{},timeout:60000});assert.ok(started.ok(),await started.text());
 await page.goto(base+'/native/viewer.html');await page.waitForFunction(()=>document.getElementById('status').textContent===''&&document.querySelector('#desktop canvas')?.width>0,{timeout:30000});
 const canvas=page.locator('#desktop canvas');await canvas.click({position:{x:500,y:300}});
 // A pointer click on the native File menu must produce a visible framebuffer change.
 const pixels=()=>page.evaluate(()=>{const c=document.querySelector('#desktop canvas'),p=c.getContext('2d').getImageData(0,28,180,230).data;let sum=0;for(let i=0;i<p.length;i+=4)sum=(sum+p[i]*3+p[i+1]*5+p[i+2]*7)>>>0;return sum;});
 const before=await pixels(),box=await canvas.boundingBox();let now=Date.now();await page.mouse.click(box.x+18/1024*box.width,box.y+35/720*box.height);
 await page.waitForFunction(prior=>{const c=document.querySelector('#desktop canvas'),p=c.getContext('2d').getImageData(0,28,180,230).data;let sum=0;for(let i=0;i<p.length;i+=4)sum=(sum+p[i]*3+p[i+1]*5+p[i+2]*7)>>>0;return sum!==prior;},before,{timeout:5000,polling:50});
 const pointerMs=Date.now()-now;assert.ok(pointerMs<3000,`Native pointer feedback took ${pointerMs}ms`);await page.keyboard.press('Escape');
 const initial=(await(await context.request.get(base+'/native-test/windows')).json()).windows.length;now=Date.now();await page.keyboard.press('Control+Alt+f');
 let opened=false;for(let i=0;i<35;i++){const state=await(await context.request.get(base+'/native-test/windows')).json();if(state.windows.length>initial){opened=true;break;}await new Promise(r=>setTimeout(r,50));}
 const keyboardMs=Date.now()-now;assert.ok(opened,'Original formation editor never opened over RFB');assert.ok(keyboardMs<3000,`Native keyboard response took ${keyboardMs}ms`);
 await page.screenshot({path:'/tmp/native-latency.png'});console.log(JSON.stringify({cpu:0.1,memoryMiB:512,pointerMs,keyboardMs}));
 await context.request.post(base+'/native/close-tool',{data:{}});await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});
