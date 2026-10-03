const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const modulePath=path.join(__dirname,'../supplement-runs.js');
const Runs=fs.existsSync(modulePath)?require(modulePath):null;
const runId='a'.repeat(24), body={kind:'material',text:'合同原文',title:'合同',scenario:null};
function storage(){const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};}
const complete={run_id:runId,status:'complete',case_id:'c',version:2,events:[{type:'complete',case_id:'c',version:2}],next:1};
const saved={id:'c',current:3,versions:[{no:1},{no:2},{no:3}]};
function client(api,store=storage(),extra={}){assert.ok(Runs,'durable supplement client must exist');return Runs.create({api,storage:store,randomUUID:()=> 'request-key',wait:async()=>{},...extra});}

test('refresh resumes a recorded run with GET only and opens its version even if a newer version exists',async()=>{
 const store=storage(),calls=[];
 const first=client(async(url,opts)=>{calls.push([url,opts]);if(opts?.method==='POST')return {run_id:runId};throw Error('offline')},store);
 const record=first.prepare('c',body);await assert.rejects(first.follow(record),/offline/);
 const second=client(async(url,opts)=>{calls.push([url,opts]);return url.startsWith('/api/runs/')?complete:saved},store);
 const result=await second.follow(second.pending('c'));
 assert.equal(calls.filter(([,o])=>o?.method==='POST').length,1);
 assert.equal(result.version,2);assert.equal(result.case.current,3);
 assert.ok(second.pending('c'),'retain completion until report actually opens');
 second.clear(second.pending('c'));assert.equal(second.pending('c'),null);
});
test('lost POST response retries the same body and key after reload',async()=>{
 const store=storage(),calls=[];
 const api=async(url,opts)=>{if(opts?.method==='POST'){calls.push(opts);if(calls.length===1)throw Error('response lost');return {run_id:runId}}return url.startsWith('/api/runs/')?complete:saved};
 const first=client(api,store);await assert.rejects(first.follow(first.prepare('c',body)),/response lost/);
 const second=client(api,store);await second.follow(second.pending('c'));
 assert.equal(calls.length,2);assert.deepEqual(calls[0].body,calls[1].body);
 assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);
});
test('pending preparation does not overwrite an uncertain submission with changed material',()=>{
 const c=client(async()=>{});const first=c.prepare('c',body);
 assert.deepEqual(c.prepare('c',{...body,text:'different'}),first);
 assert.equal(c.pending('other'),null);
});
test('poll cursors advance and replay progress, without treating queued or heartbeat as UI events',async()=>{
 const calls=[],events=[];
 const c=client(async(url,opts)=>{calls.push(url);if(opts?.method==='POST')return {run_id:runId};if(url.endsWith('after=0'))return {run_id:runId,status:'running',events:[{type:'queued'},{type:'begin',steps:[]},{type:'heartbeat'}],next:3};return url.includes('/runs/')?{...complete,next:4}:saved});
 await c.follow(c.prepare('c',body),{onEvent:e=>events.push(e.type)});
 assert.deepEqual(events,['begin']);assert.ok(calls.includes(`/api/runs/${runId}?after=3`));
});
for(const status of ['error','interrupted'])test(`${status} is terminal, preserves original material and never starts another run`,async()=>{
 const c=client(async(url,opts)=>opts?.method==='POST'?{run_id:runId}:{run_id:runId,status,events:[],next:0});
 await assert.rejects(c.follow(c.prepare('c',body)),e=>e.terminal===true);
 assert.deepEqual(c.pending('c').body,body);
});
test('failed saved-case read can be recovered without POST',async()=>{
 let offline=true,posts=0;
 const c=client(async(url,opts)=>{if(opts?.method==='POST'){posts++;return {run_id:runId}}if(url.includes('/runs/'))return complete;if(offline)throw Error('read failed');return saved});
 await assert.rejects(c.follow(c.prepare('c',body)),/read failed/);offline=false;
 await c.follow(c.pending('c'));assert.equal(posts,1);
});
for(const page of [{...complete,case_id:'other'},{...complete,version:99},{...complete,run_id:'b'.repeat(24)},{...complete,input:{kind:'supplement',case_id:'other'}}])test('mismatched run/case/version never opens a report',async()=>{
 const c=client(async(url,opts)=>opts?.method==='POST'?{run_id:runId}:url.includes('/runs/')?page:saved);
 await assert.rejects(c.follow(c.prepare('c',body)),/校验|版本/);assert.ok(c.pending('c'));
});
test('storage failure prevents sending an unrecoverable request',()=>{
 let calls=0;const c=client(async()=>{calls++},{getItem:()=>null,setItem:()=>{throw Error('quota')},removeItem(){}});
 assert.throws(()=>c.prepare('c',body),/保存|存储/);assert.equal(calls,0);
});
test('aborted watcher retains record and never submits',async()=>{
 let calls=0;const c=client(async()=>{calls++}),record=c.prepare('c',body),controller=new AbortController();controller.abort();
 await assert.rejects(c.follow(record,{signal:controller.signal}));assert.equal(calls,0);assert.ok(c.pending('c'));
});
test('rejected input permits explicit editing while an ambiguous server error stays recoverable',async()=>{
 for(const status of [422,503]){
  const c=client(async()=>{throw Object.assign(Error('request rejected'),{status})});
  await assert.rejects(c.follow(c.prepare('c',body)),e=>Boolean(e.terminal)===(status===422));
  assert.ok(c.pending('c'));
 }
});

test('quota rejection is terminal rather than pretending a disconnected analysis is running',async()=>{
 const c=client(async()=>{throw Object.assign(new Error('今日配额已用完'),{status:429})});
 const record=c.prepare('c',body);
 await assert.rejects(c.follow(record),error=>error.terminal&&/配额/.test(error.message));
 assert.ok(c.pending('c'),'retain submitted text for an explicit later retry');
});
