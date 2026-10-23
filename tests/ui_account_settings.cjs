const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
async function setup(tier='free',remaining=0){
 const nodes={};const el=id=>nodes[id]||(nodes[id]={textContent:'',hidden:false,value:'',style:{},attributes:{},dataset:{},listeners:{},setAttribute(k,v){this.attributes[k]=v;},getAttribute(k){return this.attributes[k];},addEventListener(k,fn){this.listeners[k]=fn;},focus(){this.focused=true;},showModal(){this.open=true;},close(){this.open=false;}});
 const tabs=['usage','plan','appearance'].map(name=>{const button=el(name+'Tab');button.dataset.settingsTab=name;button.attributes['aria-controls']='settings'+name[0].toUpperCase()+name.slice(1);return button;});
 el('mode').value='server';el('rounds').value='1';el('games').value='5';
 const account={tier,owner:false,guest:false,email:'fixture@gmail.com',remaining_games:remaining,quota_limit:30,expires:1900000000};
 const events={};const context={document:{getElementById:el,querySelectorAll:()=>tabs},window:{addEventListener:(k,fn)=>events[k]=fn},fetch:async()=>({ok:true,json:async()=>account}),setTimeout(){},setInterval(){},location:{reload(){}},console};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/account-ui.js','utf8'),context);for(let i=0;i<10;i++)await Promise.resolve();return {el,events,account};
}
(async()=>{
 const {el}=await setup();
 assert.equal(el('quotaNotice').hidden,false);assert.equal(el('usageFill').style.width,'100%');
 assert.equal(el('upgradeLink').href,'/plans?plan=plus');
 el('openSettings').listeners.click();assert.equal(el('settingsDialog').open,true);
 el('appearanceTab').listeners.click();assert.equal(el('settingsAppearance').hidden,false);assert.equal(el('settingsUsage').hidden,true);
 el('closeSettings').listeners.click();assert.equal(el('settingsDialog').open,false);
 let blocked=false;el('form').listeners.submit({preventDefault(){blocked=true;},stopImmediatePropagation(){}});
 assert.equal(blocked,true);assert.equal(el('settingsDialog').open,true);assert.equal(el('settingsUsage').hidden,false);
 const plus=await setup('plus',null);assert.equal(plus.el('upgradeLink').href,'/plans?plan=pro');assert.equal(plus.el('usageMeter').hidden,true);
 const pro=await setup('pro',null);assert.equal(pro.el('upgradeBanner').hidden,true);
 // The same stored preference applies to auth and purchase pages before paint.
 const attributes={};const storageEvents={};const themeContext={document:{documentElement:{setAttribute:(k,v)=>attributes[k]=v}},localStorage:{getItem:()=> 'light'},window:{addEventListener:(k,fn)=>storageEvents[k]=fn}};
 vm.createContext(themeContext);vm.runInContext(fs.readFileSync('static/theme.js','utf8'),themeContext);assert.equal(attributes['data-theme'],'light');storageEvents.storage({key:'arena-theme',newValue:'dark'});assert.equal(attributes['data-theme'],'dark');
 console.log('PASS: usage settings, exhausted quota guard, Plus/Pro suggestions and shared theme');
})().catch(error=>{console.error(error);process.exitCode=1;});
