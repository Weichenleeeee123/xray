const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const term = (values = {}) => ({id:'status',term:'存续',plain:'仍具有主体资格。',why:'不等于经营或偿付正常。',law:'本次解释法规',origin:'glossary',...values});
const message = (values = {}) => ({role:'assistant',version:1,answer_kind:'glossary',request_id:'req1',
  knowledge_terms:[term()],text:'名词解释',...values});
const entry = (values = {}) => ({id:'status',term:'存续',plain:'仍具有主体资格。',why:'不等于经营或偿付正常。',
  basis:'本次解释法规',origin:'glossary',savedAt:'2026-10-04T00:00:00Z',seen:[{caseId:'c1',version:1,company:'旧版公司'}],...values});

function harness({account = false, initial = [], brokenRead = false, brokenWrite = false} = {}) {
  let raw = typeof initial === 'string' ? initial : JSON.stringify(initial), owner = account ? 'a@example.com' : null;
  const dirty = new Map(), removed = new Map(), calls = [], writes = [], notices=[];
  const S = {session:{account:account ? {id:'a',email:'a@example.com'} : null},case:{id:'c1',current:2,
    case:{company_name:'旧版公司'},versions:[{no:1,sources:{registry:{name:'第一版来源'}},terms:[]},
      {no:2,sources:{registry:{name:'第二版来源不可用'}},terms:[term({plain:'不能借用的新解释'})]}],
    chat:[message()]},viewNo:2};
  let route = '#/case/c1/v/2', remote = [], onApi;
  const context = vm.createContext({console,AbortController});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../library-actions.js'),'utf8'),context);
  const api = context.LibraryActions;
  api.configure({getState:()=>S,route:()=>route,readRaw:()=>{if(brokenRead)throw Error('denied');return raw;},
    readOwner:()=>owner,writeOwner:value=>{owner=value;return !brokenWrite;},
    readPending:email=>dirty.get(email)===true,writePending:(email,value)=>{if(brokenWrite)return false;dirty.set(email,value);return true;},
    readDeleted:email=>removed.get(email)||[],writeDeleted:(email,value)=>{removed.set(email,value);return !brokenWrite;},
    write:list=>{if(brokenWrite)return false;raw=JSON.stringify(list);writes.push(raw);return true;},
    beforeWrite:()=>{},refresh:()=>{},notify:value=>notices.push(value),now:()=> '2026-10-04T00:00:00Z',
    api:async(url,opts={})=>{calls.push({url,...opts});if(onApi)return onApi(url,opts);if(opts.method==='PUT')remote=JSON.parse(JSON.stringify(opts.body));return remote;}});
  return {api,S,calls,writes,dirty,removed,notices,list:()=>JSON.parse(raw),setRaw:value=>raw=value,setOwner:value=>owner=value,getOwner:()=>owner,
    setRemote:value=>remote=value,setApi:value=>onApi=value,setRoute:value=>route=value};
}

test('rendering historical messages never saves; manual save uses exact message snapshot and version',async()=>{
  const h=harness();
  const html=h.api.html(h.S.case.chat[0],0);
  assert.match(html,/data-act="chat-lib-save" data-index="0" data-term="status"/);
  assert.match(html,/href="#\/library"/);
  assert.equal(h.writes.length,0);assert.equal(h.calls.length,0);
  assert.equal((await h.api.handle(0,'status')).status,'local');
  assert.equal(h.list()[0].plain,'仍具有主体资格。');
  assert.equal(h.list()[0].basis,'本次解释法规');
  assert.deepEqual(h.list()[0].seen,[{caseId:'c1',version:1,company:'旧版公司'}]);
  assert.doesNotMatch(h.api.html(h.S.case.chat[0],0),/不能借用的新解释/);
});

test('snapshot law takes priority and source basis resolves only against message version',async()=>{
  const h=harness();h.S.case.chat[0].knowledge_terms=[term({law:null,basis:'registry'})];
  await h.api.handle(0,'status');assert.equal(h.list()[0].basis,'第一版来源');
  const next=harness();next.S.case.chat[0].knowledge_terms=[term({law:'法规优先',basis:'registry',origin:'model'})];
  await next.api.handle(0,'status');assert.equal(next.list()[0].basis,'法规优先');assert.equal(next.list()[0].origin,'model');
});

test('repeated or simultaneous saves are idempotent and never toggle an existing entry off',async()=>{
  const h=harness();await Promise.all([h.api.handle(0,'status'),h.api.handle(0,'status')]);
  await h.api.handle(0,'status');assert.equal(h.list().length,1);assert.equal(h.list()[0].seen.length,1);
  assert.match(h.api.html(h.S.case.chat[0],0),/已收藏/);
  assert.equal(h.writes.length,1);
});

test('deleting a saved term re-enables its chat button instead of retaining a stale success state',async()=>{
  const h=harness();await h.api.handle(0,'status');h.setRaw('[]');
  assert.doesNotMatch(h.api.html(h.S.case.chat[0],0),/已收藏|已保存到此浏览器|disabled/);
});

test('historical report company name is used rather than the current case input',async()=>{
  const h=harness();h.S.case.versions[0].company={name:'该版登记名称'};
  await h.api.handle(0,'status');assert.equal(h.list()[0].seen[0].company,'该版登记名称');
});

test('same id with different explanation is preserved rather than silently overwritten',async()=>{
  const old=entry({plain:'原来收藏的定义'}),h=harness({initial:[old]});
  const before=JSON.stringify(h.list());assert.equal((await h.api.handle(0,'status')).status,'conflict');
  assert.equal(JSON.stringify(h.list()),before);assert.equal(h.writes.length,0);
  assert.match(h.api.html(h.S.case.chat[0],0),/已有不同解释/);
});

test('multiple candidate terms have individual buttons and saved provenance retains multiple versions',async()=>{
  const h=harness({initial:[entry({seen:[{caseId:'c1',version:2,company:'旧版公司'}]})]});
  h.S.case.chat[0]=message({answer_kind:'library_action',library_action:{operation:'save_terms',source_version:1,auto_save:false,
    terms:[term(),term({id:'judgment',term:'裁判文书',plain:'法院文书'})]}});
  assert.equal((h.api.html(h.S.case.chat[0],0).match(/data-act="chat-lib-save"/g)||[]).length,2);
  await h.api.handle(0,'status');assert.deepEqual(h.list()[0].seen.map(x=>x.version),[2,1]);
  assert.equal(h.list().length,1);
});

test('malformed or blocked storage never fabricates success or overwrites the library',async()=>{
  for(const opts of [{initial:'{broken'},{initial:'{}'},{initial:[{id:'incomplete'}]},{brokenRead:true},{brokenWrite:true}]){
    const h=harness(opts),result=await h.api.handle(0,'status');
    assert.ok(['corrupt','failed'].includes(result.status),result.status);
    assert.equal(h.writes.length,0);assert.equal(h.calls.length,0);
    assert.doesNotMatch(h.api.html(h.S.case.chat[0],0),/已保存并同步|已保存到此浏览器|>已收藏</);
  }
});

test('oversized explanations are rejected whole, never silently truncated to fit API',async()=>{
  const h=harness();h.S.case.chat[0].knowledge_terms=[term({plain:'长'.repeat(2001)})];
  assert.equal((await h.api.handle(0,'status')).status,'invalid');assert.equal(h.writes.length,0);
  const full=harness({initial:Array.from({length:500},(_,i)=>entry({id:'term'+i}))});
  assert.equal((await full.api.handle(0,'status')).status,'limit');assert.equal(full.list().length,500);
});

test('all candidate labels and ids are escaped',()=>{
  const h=harness();h.S.case.chat[0].knowledge_terms=[term({id:'"><img src=x>',term:'<script>bad()</script>'})];
  const html=h.api.html(h.S.case.chat[0],0);assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script/);
});

test('account saved state waits for successful PUT and preserves remote entries',async()=>{
  const h=harness({account:true});h.setRemote([entry({id:'remote',term:'其他设备收藏'})]);
  let finish;h.setApi(async(url,opts)=>opts.method==='PUT'?new Promise(resolve=>finish=()=>resolve(opts.body)):[entry({id:'remote',term:'其他设备收藏'})]);
  const pending=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  assert.match(h.api.html(h.S.case.chat[0],0),/正在保存/);assert.doesNotMatch(h.api.html(h.S.case.chat[0],0),/已保存并同步/);
  assert.equal(h.list().length,2);finish();assert.equal((await pending).status,'synced');
  assert.ok(h.calls.every(call=>call.headers['X-Xray-Library-Owner']==='a@example.com'));
  assert.equal(h.dirty.get('a@example.com'),false);
});

test('failed account PUT retains local snapshot, pending marker and truthful retry state',async()=>{
  const h=harness({account:true});h.setApi(async(url,opts)=>{if(opts.method==='PUT')throw Error('offline');return [];});
  assert.equal((await h.api.handle(0,'status')).status,'sync_failed');assert.equal(h.list().length,1);
  assert.equal(h.dirty.get('a@example.com'),true);assert.match(h.api.html(h.S.case.chat[0],0),/账号同步未完成/);
  assert.match(h.api.html(h.S.case.chat[0],0),/重试同步/);
  h.setApi(null);assert.equal((await h.api.handle(0,'status')).status,'synced');assert.equal(h.list().length,1);
});

test('server acceptance must retain the exact saved version provenance before claiming sync',async()=>{
  const h=harness({account:true});h.setApi(async(url,opts)=>opts.method==='PUT'?opts.body.map(e=>({...e,seen:[]})):[]);
  assert.equal((await h.api.handle(0,'status')).status,'sync_failed');assert.equal(h.api.hasPending(),true);
});

test('a separate local edit while PUT is in flight keeps the pending marker',async()=>{
  const h=harness({account:true});let finish;h.setApi(async(url,opts)=>opts.method==='PUT'?new Promise(resolve=>finish=()=>resolve(opts.body)):[]);
  const pending=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  h.setRaw(JSON.stringify([...h.list(),entry({id:'parallel-edit'})]));h.api.markPending();finish();
  assert.equal((await pending).status,'synced');assert.equal(h.api.hasPending(),true);
});

test('account, case, view, route or identity changes during lookup prevent local write and PUT',async()=>{
  for(const change of [h=>h.S.session={account:null},h=>h.S.case={...h.S.case,id:'other'},h=>h.S.viewNo=1,
    h=>h.setRoute('#/cases'),h=>h.api.invalidate(),h=>h.S.accountChanging=true]){
    const h=harness({account:true});let finish;h.setApi(()=>new Promise(resolve=>finish=resolve));
    const pending=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));change(h);finish([]);
    assert.equal((await pending).status,'changed');assert.equal(h.writes.length,0);
    assert.equal(h.calls.filter(x=>x.method==='PUT').length,0);
  }
});

test('identity change after PUT begins never writes returned data into another account cache',async()=>{
  const h=harness({account:true});let finish;h.setApi(async(url,opts)=>opts.method==='PUT'?new Promise(resolve=>finish=resolve):[]);
  const pending=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  const writes=h.writes.length;h.S.session={account:{id:'b',email:'b@example.com'}};h.api.invalidate();finish([entry()]);
  assert.equal((await pending).status,'changed');assert.equal(h.writes.length,writes);
});

test('auto-save executes only one live authorized request, not render, history or replay',async()=>{
  const h=harness();h.S.viewNo=1;
  const reply=message({answer_kind:'library_action',library_action:{operation:'save_terms',source_version:1,auto_save:true,terms:[term()]}});
  h.S.case.chat=[reply];
  const context=h.api.captureContext({requestId:'req1',autoEligible:true});
  h.api.html(reply,0);await h.api.receive(reply,h.api.captureContext());
  await h.api.receive(reply,{...context,autoEligible:false});await h.api.receive(reply,{...context,requestId:'different'});
  assert.equal(h.writes.length,0);
  assert.equal((await h.api.receive(reply,context))[0].status,'local');
  const count=h.writes.length;assert.equal((await h.api.receive(reply,context)).length,0);assert.equal(h.writes.length,count);
});

test('auto-save is cancelled if report or identity changed since its chat request',async()=>{
  const h=harness();h.S.viewNo=1;
  const reply=message({answer_kind:'library_action',library_action:{operation:'save_terms',source_version:1,auto_save:true,terms:[term()]}});
  h.S.case.chat=[reply];const context=h.api.captureContext({requestId:'req1',autoEligible:true});h.S.viewNo=2;
  assert.equal((await h.api.receive(reply,context)).length,0);assert.equal(h.writes.length,0);
});

test('initial account sync retries unsynced local snapshots instead of discarding them',async()=>{
  const h=harness({account:true,initial:[entry()]});h.dirty.set('a@example.com',true);
  assert.equal(await h.api.syncInitial(),true);assert.equal(h.list().length,1);
  assert.equal(h.calls.filter(x=>x.method==='PUT').length,1);assert.equal(h.dirty.get('a@example.com'),false);
});

test('initial sync respects remote deletion unless dirty and never merges another account cache',async()=>{
  const clean=harness({account:true,initial:[entry()]});await clean.api.syncInitial();assert.equal(clean.list().length,0);
  const other=harness({account:true,initial:[entry()]});other.setOwner('other@example.com');other.dirty.set('a@example.com',true);
  await other.api.syncInitial();assert.equal(other.list().length,0);
  const first=harness({account:true,initial:[entry()]});first.setOwner(null);
  await first.api.syncInitial();assert.equal(first.list().length,1);assert.equal(first.calls.filter(x=>x.method==='PUT').length,1);
});

test('legacy sync and new saves serialize network writes; account guard header is retained',async()=>{
  const h=harness({account:true,initial:[entry({id:'old'})]});let inFlight=0,max=0;
  h.setApi(async(url,opts)=>{inFlight++;max=Math.max(max,inFlight);await new Promise(resolve=>setImmediate(resolve));inFlight--;return opts.body||[];});
  await Promise.all([h.api.syncLegacy(),h.api.handle(0,'status')]);assert.equal(max,1);
  assert.ok(h.calls.every(call=>call.headers['X-Xray-Library-Owner']==='a@example.com'));
});

test('source-version mismatch, nonassistant and missing message snapshots offer no save',async()=>{
  const h=harness();
  for(const invalid of [message({role:'user'}),message({knowledge_terms:[]}),message({version:99}),
    message({answer_kind:'library_action',library_action:{operation:'save_terms',source_version:2,terms:[term()]}})]){
    h.S.case.chat=[invalid];assert.equal(h.api.html(invalid,0),'');assert.equal((await h.api.handle(0,'status')).status,'invalid');
  }
  assert.equal(h.writes.length,0);
});

test('legacy and initial synchronization failures resolve false instead of unhandled rejection',async()=>{
  const h=harness({account:true});h.setApi(async()=>{throw Error('offline');});
  assert.equal(await h.api.syncLegacy(),false);assert.equal(await h.api.syncInitial(),false);assert.equal(h.notices.length,2);
  h.api.configure({notify:()=>{throw Error('toast unavailable');}});
  assert.equal(await h.api.syncInitial(),false);
});

test('switching account with failed cache write does not relabel or upload foreign cached terms',async()=>{
  const h=harness({account:true,initial:[entry({id:'foreign'})]});h.setOwner('old@example.com');
  h.api.configure({write:()=>false});
  assert.equal(await h.api.syncInitial(),false);assert.equal(h.getOwner(),'old@example.com');
  assert.equal(h.list()[0].id,'foreign');assert.equal(await h.api.syncLegacy(),false);
  assert.equal(h.calls.filter(call=>call.method==='PUT').length,0);
});

test('failed final owner installation rolls back cache or leaves a quarantine, never a wrong owner',async()=>{
  const h=harness({account:true,initial:[entry({id:'foreign'})]});h.setOwner('old@example.com');h.setRemote([entry({id:'account-a'})]);
  h.api.configure({writeOwner:value=>{if(value==='a@example.com')return false;h.setOwner(value);return true;}});
  assert.equal(await h.api.syncInitial(),false);assert.equal(h.getOwner(),'old@example.com');assert.equal(h.list()[0].id,'foreign');
  assert.equal(await h.api.syncLegacy(),false);assert.equal(h.calls.filter(call=>call.method==='PUT').length,0);
});

test('legacy deletion during remote lookup is not resurrected by a chat save',async()=>{
  const old=entry({id:'remove-me'}),h=harness({account:true,initial:[old]});let finish;
  h.setApi(async(url,opts)=>opts.method==='PUT'?opts.body:new Promise(resolve=>finish=resolve));
  const saving=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  const before=h.list();h.setRaw('[]');assert.equal(h.api.recordChange(before,[]),true);finish([old]);
  assert.equal((await saving).status,'synced');assert.deepEqual(h.list().map(e=>e.id),['status']);
  assert.deepEqual(Array.from(h.calls.find(call=>call.method==='PUT').body,e=>e.id),['status']);
});

test('persisted deletion survives failed synchronization and next-page initial merge',async()=>{
  const old=entry({id:'remove-me'}),h=harness({account:true,initial:[old]});
  h.setRaw('[]');h.api.recordChange([old],[]);h.setRemote([old]);
  assert.equal(await h.api.syncInitial(),true);assert.deepEqual(h.list(),[]);
  assert.deepEqual(h.calls.find(call=>call.method==='PUT').body,[]);assert.equal(h.api.hasPending(),false);
});

test('new local deletion during PUT stays pending until a later serialized write',async()=>{
  const old=entry({id:'remove-me'}),h=harness({account:true,initial:[old]});let finish;
  h.setApi(async(url,opts)=>opts.method==='PUT'?new Promise(resolve=>finish=()=>resolve(opts.body)):[old]);
  const saving=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  const before=h.list(),after=before.filter(e=>e.id!=='remove-me');h.setRaw(JSON.stringify(after));h.api.recordChange(before,after);finish();
  assert.equal((await saving).status,'synced');assert.equal(h.api.hasPending(),true);
  assert.deepEqual(Array.from(h.removed.get('a@example.com')),['remove-me']);
});

test('navigating away and back to the same report prevents old auto-save execution',async()=>{
  const h=harness();h.S.viewNo=1;h.S.navigationEpoch=4;
  const reply=message({answer_kind:'library_action',library_action:{operation:'save_terms',source_version:1,auto_save:true,terms:[term()]}});
  h.S.case.chat=[reply];const context=h.api.captureContext({requestId:'req1',autoEligible:true});
  h.setRoute('#/library');h.S.navigationEpoch++;h.setRoute('#/case/c1/v/2');h.S.navigationEpoch++;
  assert.equal((await h.api.receive(reply,context)).length,0);assert.equal(h.writes.length,0);
});

test('manual save cancelled during GET stays cancelled after returning to the same hash',async()=>{
  const h=harness({account:true});h.S.navigationEpoch=10;let finish;
  h.setApi(()=>new Promise(resolve=>finish=resolve));
  const pending=h.api.handle(0,'status');await new Promise(resolve=>setImmediate(resolve));
  h.setRoute('#/library');h.S.navigationEpoch++;h.setRoute('#/case/c1/v/2');h.S.navigationEpoch++;finish([]);
  assert.equal((await pending).status,'changed');assert.equal(h.writes.length,0);
  assert.equal(h.calls.filter(call=>call.method==='PUT').length,0);
});

test('background account synchronization is not cancelled by navigation epochs',async()=>{
  const h=harness({account:true,initial:[entry()]});h.S.navigationEpoch=3;let finish;
  h.setApi((url,opts)=>new Promise(resolve=>finish=()=>resolve(opts.body)));
  const pending=h.api.syncLegacy();await new Promise(resolve=>setImmediate(resolve));
  h.S.navigationEpoch++;h.setRoute('#/library');finish();
  assert.equal(await pending,true);assert.equal(h.api.hasPending(),false);
});
