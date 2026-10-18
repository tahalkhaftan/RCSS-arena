const fs=require('fs'),vm=require('vm');
const harness=fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame=')[0];
const checks=`
function frame(cycle,owner='l',x=44,block=false){return {cycle,mode:'3',score:[0,0],ball:[x,0],players:[['l',1,-50,0,0,true],['r',1,50,0,0,true],[owner,2,x,0,0,false],...(block?[[owner==='l'?'r':'l',3,x>0?48:-48,0,0,false]]:[])]};}
const strong=context.newRatingStats(),far=context.newRatingStats(),blocked=context.newRatingStats(),balanced=context.newRatingStats();
for(let c=1;c<=40;c++){context.addRatingFrame(strong,frame(c));context.addRatingFrame(far,frame(c,'l',0));context.addRatingFrame(blocked,frame(c,'l',44,true));context.addRatingFrame(balanced,c%2?frame(c):frame(c,'r',-44));}
assert.equal(context.ratingValues(balanced).join(','),'5,5','Symmetric play must produce symmetric ratings');
assert.ok(context.ratingValues(strong)[0]>context.ratingValues(far)[0],'Danger near goal must increase rating');
assert.ok(strong.danger[0]>blocked.danger[0],'Blocking defenders reduce estimated danger');
const count=strong.count;context.addRatingFrame(strong,frame(40));assert.equal(strong.count,count,'Repeated cycles do not inflate ratings');
assert.equal(context.ratingValues(context.newRatingStats()),null,'No invented grade for missing data');
strong.score=[20,0];assert.ok(context.ratingValues(strong).every(n=>n>=0&&n<=10));

function actionFrame(cycle,id,side,x,y=0){return {cycle,mode:'3',score:[0,0],ball:[x,y],players:[['l',1,-50,0,0,true],['r',1,50,0,0,true],[side,id,x,y,0,false]]};}
const deep=context.newRatingStats(),lateral=context.newRatingStats(),lost=context.newRatingStats(),dribble=context.newRatingStats(),gap=context.newRatingStats();
for(const stats of [deep,lateral,lost,gap])context.addRatingFrame(stats,actionFrame(1,2,'l',0));
context.addRatingFrame(deep,actionFrame(5,3,'l',10));context.addRatingFrame(lateral,actionFrame(5,3,'l',0,10));context.addRatingFrame(lost,actionFrame(5,3,'r',10));context.addRatingFrame(gap,actionFrame(20,3,'l',10));
assert.equal(deep.passes[0],1);assert.equal(deep.deep[0],1);assert.ok(deep.actions[0]>lateral.actions[0]);assert.equal(lost.passes[0],0);assert.equal(gap.passes[0],0,'Missing live samples must not invent a pass');
for(let c=1;c<=5;c++)context.addRatingFrame(dribble,actionFrame(c,2,'l',c-1));assert.equal(dribble.dribbles[0],1);assert.ok(dribble.actions[0]>0);
vm.runInContext('monitorDisplay({cycle:42,names:["A","B"],score:[2,1],players:[],ball:[0,0]})',context);
assert.equal(el('monitorLeftGoals').textContent,2);assert.equal(el('monitorRightGoals').textContent,1);assert.equal(el('monitorCycle').textContent,'42');
console.log('PASS: goal layout, cycle display, symmetric ratings, attacking danger, blockers, deduplication and missing-data behavior');
`;
vm.runInNewContext(harness+checks,{require,console,URL,AbortController,setTimeout,clearTimeout});
