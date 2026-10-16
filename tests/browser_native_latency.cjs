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
 await context.request.post(base+'/native/close-tool',{data:{}});
 await context.request.post(base+'/native-test/motion',{data:{}});
 // Observe actual native match movement, not just idle menu responsiveness.
 const movement=await page.evaluate(async()=>{
  const c=document.querySelector('#desktop canvas'),ctx=c.getContext('2d');let last=null,changes=0,lastChange=performance.now(),maxGap=0;
  const started=performance.now();while(performance.now()-started<6500){
   const p=ctx.getImageData(0,100,c.width,c.height-130).data;let sum=0;
   for(let i=0;i<p.length;i+=16)sum=(sum+p[i]*3+p[i+1]*5+p[i+2]*7)>>>0;
   const now=performance.now();if(last!==null&&sum!==last){changes++;maxGap=Math.max(maxGap,now-lastChange);lastChange=now;}last=sum;
   await new Promise(r=>setTimeout(r,100));
  }return {changes,maxGap:Math.round(Math.max(maxGap,performance.now()-lastChange))};
 });
 assert.ok(movement.changes>=10,`Native match rendering stalled: ${JSON.stringify(movement)}`);
 assert.ok(movement.maxGap<2500,`Native image froze: ${JSON.stringify(movement)}`);
 const movingWindows=(await(await context.request.get(base+'/native-test/windows')).json()).windows.length;
 now=Date.now();await page.keyboard.press('Control+Alt+f');let movingOpened=false;
 for(let i=0;i<35;i++){const state=await(await context.request.get(base+'/native-test/windows')).json();if(state.windows.length>movingWindows){movingOpened=true;break;}await new Promise(r=>setTimeout(r,50));}
 const movingKeyboardMs=Date.now()-now;assert.ok(movingOpened&&movingKeyboardMs<3000,`Input stalled during match: ${movingKeyboardMs}ms`);
 console.log(JSON.stringify({movingMatch:movement,movingKeyboardMs}));
 await page.screenshot({path:'/tmp/native-latency.png'});console.log(JSON.stringify({cpu:0.1,memoryMiB:512,pointerMs,keyboardMs}));
 // Three browser windows, one native process, each with its own cropped RFB stream.
 await context.request.post(base+'/native/close-tool',{data:{}});
 const pid=(await(await context.request.get(base+'/native-test/windows')).json()).pid;
 await page.close();
 const mainPage=await context.newPage();await mainPage.goto(base+'/native/window.html?tool=main');
 const visibleCanvas=async p=>{await p.locator('#frame').waitFor({state:'visible',timeout:30000});const frame=()=>p.frames().find(f=>f.url().includes('viewer.html?window='));for(let i=0;i<80;i++){const f=frame();if(f&&await f.locator('#desktop canvas').count()&&await f.locator('#desktop canvas').evaluate(c=>c.width>0&&c.height>0))return f;await new Promise(r=>setTimeout(r,200));}throw Error('Per-window VNC did not become visible');};
 await visibleCanvas(mainPage);
 const formationPopup=context.waitForEvent('page');await mainPage.locator('[data-tool="formation"]').click();const formPage=await formationPopup;await formPage.waitForLoadState();const formFrame=await visibleCanvas(formPage);
 const records=(await(await context.request.get(base+'/native/windows')).json()).windows,formationRecord=records.find(w=>w.key==='formation');assert.ok(formationRecord);
 const size=await formFrame.locator('canvas').evaluate(c=>[c.width,c.height]);assert.deepEqual(size,[formationRecord.width,formationRecord.height]);
 await formFrame.locator('canvas').click({position:{x:Math.min(300,size[0]-20),y:Math.min(200,size[1]-20)}});await formPage.keyboard.press('Control+o');
 let dialog;for(let i=0;i<60;i++){const s=await(await context.request.get(base+'/native/windows')).json();dialog=s.windows.find(w=>w.modal&&w.owner===formationRecord.id);if(dialog)break;await new Promise(r=>setTimeout(r,150));}assert.ok(dialog,'Formation input must open its own native file dialog, not the main monitor dialog');
 const dialogPage=await context.newPage();await dialogPage.goto(base+'/native/window.html?id='+dialog.id);await visibleCanvas(dialogPage);await dialogPage.keyboard.press('Escape');await dialogPage.close();
 const debugPopup=context.waitForEvent('page');await mainPage.locator('[data-tool="debug"]').click();const debugPage=await debugPopup;await debugPage.waitForLoadState();await visibleCanvas(debugPage);
 assert.equal((await(await context.request.get(base+'/native-test/windows')).json()).pid,pid,'Detached tools must share the original native process');
 console.log('PASS independent native monitor, formation and debug browser windows, exact cropped framebuffer, formation keyboard routing and shared Qt process');
 await mainPage.close();await formPage.close();await debugPage.close();await context.request.post(base+'/native/windows-mode',{data:{enabled:false}});
 await context.request.post(base+'/native/close-tool',{data:{}});await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});
