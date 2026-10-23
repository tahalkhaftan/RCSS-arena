const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
async function setup(path,ready=true){
 const nodes={};
 const el=id=>nodes[id]||(nodes[id]={textContent:'',disabled:false,value:'',dataset:{},attributes:{},classList:{add(){},remove(){}},addEventListener(name,fn){this[name]=fn;},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},toggleAttribute(k,on){if(on)this.attributes[k]='';else delete this.attributes[k];},getAttribute(k){return this[k];}});
 const signin=el('signInTab'),signup=el('signUpTab'),switcher=el('switchLink');
 signin.href='/login';signin.dataset.authMode='signin';signup.href='/signup';signup.dataset.authMode='signup';
 const events={},assigned=[];
 const context={document:{getElementById:el,querySelectorAll:()=>[signin,signup,switcher],querySelector:()=>null},location:{pathname:path,search:'',assign:p=>assigned.push(p)},history:{pushState:(_,__,path)=>context.location.pathname=path},window:{addEventListener:(name,fn)=>events[name]=fn},URLSearchParams,fetch:async()=>({ok:true,json:async()=>({google_ready:ready})})};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/auth-ui.js','utf8'),context);
 for(let i=0;i<8;i++)await Promise.resolve();
 return {context,el,events,assigned};
}
(async()=>{
 const {context,el,events,assigned}=await setup('/signup');
 assert.equal(el('googleLabel').textContent,'ثبت‌نام با گوگل');
 assert.equal(el('signUpTab').attributes['aria-current'],'page');
 assert.equal(el('googleLogin').disabled,false);
 const click={preventDefault(){},button:0};
 el('signInTab').click(click);
 assert.equal(context.location.pathname,'/login');
 assert.equal(el('googleLabel').textContent,'ورود با گوگل');
 assert.equal(el('signInTab').attributes['aria-current'],'page');
 assert.equal(el('signUpTab').attributes['aria-current'],undefined);
 el('switchLink').click(click);
 assert.equal(context.location.pathname,'/signup');
 context.location.pathname='/login';events.popstate();
 assert.equal(el('googleLabel').textContent,'ورود با گوگل');
 el('googleLogin').click();el('googleLogin').click();
 assert.deepEqual(assigned,['/auth/google'],'one real OAuth navigation, even with double click');
 assert.equal(el('googleLogin').attributes['aria-busy'],'true');
 const unavailable=await setup('/login',false);
 unavailable.el('googleLogin').click();
 assert.equal(unavailable.el('googleLogin').disabled,true);
 assert.deepEqual(unavailable.assigned,[],'unconfigured OAuth never pretends to log in');
 assert.match(unavailable.el('message').textContent,/دسترس نیست/);
 console.log('PASS: sign-in/sign-up navigation, back button, real Google redirect and unavailable OAuth state');
})().catch(error=>{console.error(error);process.exitCode=1;});
