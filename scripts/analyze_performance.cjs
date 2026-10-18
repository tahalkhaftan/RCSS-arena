'use strict';
// Share the monitor's trusted, pure classifier instead of maintaining a second set of rules.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'..','static','index.html'),'utf8');
const start=html.indexOf('const performanceSnapshots='),end=html.indexOf('const performanceRows=',start);
if(start<0||end<0)throw Error('Performance classifier boundary missing');
const core=vm.runInNewContext(html.slice(start,end)+';({newPerformance,recordPerformance,exportPerformance})',{}, {timeout:1000});
const replay=JSON.parse(fs.readFileSync(0,'utf8')),stats=core.newPerformance();
for(const frame of replay.frames)core.recordPerformance(stats,frame);
const last=replay.frames.at(-1);const result=core.exportPerformance(stats,{source:'full_rcg',names:replay.team_names,naturalEnd:['2','time_over'].includes(String(last?.mode))});
// Final team records may arrive after the last show frame; score is authoritative.
if(Array.isArray(replay.final_score)){result.left.goals=replay.final_score[0];result.right.goals=replay.final_score[1];}
result.quality.goals_without_detected_on_target=[result.left,result.right].map(team=>Math.max(0,(team.goals||0)-(team.shots.on_target||0)));
process.stdout.write(JSON.stringify(result));
