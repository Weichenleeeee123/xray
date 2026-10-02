const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function harness(){
  const nodes=new Map(), listeners={}, timers=[];
  const node=()=>({innerHTML:'',textContent:'',hidden:true,isConnected:true,open:true,dataset:{},close(){this.open=false;},classList:{add(){},remove(){},contains(){return false;}}});
  const ctx=vm.createContext({FormData,AbortController,URLSearchParams,console,
    setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){},
    location:{hash:'#/case/first',search:'',replace(){}},
    document:{body:node(),querySelector:s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},querySelectorAll:()=>[],addEventListener(){}},
    window:{addEventListener:(event,fn)=>{listeners[event]=fn;},scrollTo(){}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app.js'),'utf8').replace(/boot\(\);\s*$/,''),ctx);
  const run=code=>vm.runInContext(code,ctx);
  run(`researchCleanup=()=>{}; renderTop=()=>{}; globalThis.notices=[]; toast=(message,bad)=>notices.push({message,bad}); shellHtml=x=>x;
    renderCase=()=>{ globalThis.rendered=S.case.id; useTerms(ver().terms||[]); };
    globalThis.pending={}; api=(url,opts)=>new Promise((resolve,reject)=>{pending[url]={resolve,reject,opts};});`);
  return {ctx,run,nodes,listeners,timers};
}
function result(id){return {id,current:1,versions:[{no:1,terms:[]}],raw:[],chat:[]};}
async function openReport(h,id='first'){
  h.ctx.caseResult=result(id);h.run(`location.hash='#/case/${id}'`);
  const work=h.run('route()');h.run(`pending['/api/cases/${id}'].resolve(caseResult)`);await work;
}
function restoreApi(h){
  const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
  h.run(source.slice(source.indexOf('async function api('),source.indexOf('// ---------- 小工具')));
}

test('a saved report starts loading before optional startup metadata finishes',async()=>{
  const h=harness();h.run('boot()');
  assert.ok(h.run(`Boolean(pending['/api/cases/first'])`));
  h.ctx.caseResult=result('first');h.run(`pending['/api/cases/first'].resolve(caseResult)`);
  await Promise.resolve();await Promise.resolve();
  assert.equal(h.run('rendered'),'first');
});

test('late case response cannot replace a newer navigation',async()=>{
  const h=harness();const first=h.run('route()');
  h.run(`location.hash='#/case/second'`);const second=h.run('route()');
  h.ctx.caseResult=result('second');h.run(`pending['/api/cases/second'].resolve(caseResult)`);await second;
  h.ctx.caseResult=result('first');h.run(`pending['/api/cases/first'].resolve(caseResult)`);await first;
  assert.equal(h.run('S.case.id'),'second');assert.equal(h.run('rendered'),'second');
  assert.equal(h.run(`pending['/api/cases/first'].opts.signal.aborted`),true);
});

test('late failed case response does not overwrite a successfully opened report',async()=>{
  const h=harness();const first=h.run('route()');h.run(`location.hash='#/case/second'`);const second=h.run('route()');
  h.ctx.caseResult=result('second');h.run(`pending['/api/cases/second'].resolve(caseResult)`);await second;
  h.nodes.get('#view').innerHTML='second report';
  h.run(`pending['/api/cases/first'].reject(new Error('older request failed'))`);await first;
  assert.equal(h.nodes.get('#view').innerHTML,'second report');
});

test('late list response cannot update a different page or replace its case cache',async()=>{
  const h=harness();h.run(`location.hash='#/cases'`);const list=h.run('route()');
  h.run(`location.hash='#/case/second'`);const second=h.run('route()');
  h.ctx.caseResult=result('second');h.run(`pending['/api/cases/second'].resolve(caseResult)`);await second;
  h.run(`$('#caseList').innerHTML='left behind'`);
  h.run(`pending['/api/cases'].resolve([{id:'stale',company_name:'stale'}])`);await list;
  assert.equal(h.nodes.get('#caseList').innerHTML,'left behind');assert.equal(h.run('S.cases.length'),0);
});

test('late global glossary preserves the viewed versions own terms and does not rerender it',async()=>{
  const h=harness();const ready=h.run('boot()');
  h.ctx.caseResult={...result('first'),versions:[{no:1,terms:[{id:'own',term:'该版术语',aliases:[],plain:'原解释'}]}]};
  // The report must be independent from global metadata.
  assert.ok(h.run(`Boolean(pending['/api/cases/first'])`));
  h.run(`pending['/api/cases/first'].resolve(caseResult)`);await Promise.resolve();await Promise.resolve();
  h.run(`renderCase=()=>{throw new Error('must not erase reader input')};
    pending['/api/health'].resolve({llm:{mode:'off'}});pending['/api/scenarios'].resolve([]);
    pending['/api/sources'].resolve([]);pending['/api/demo/cases'].resolve([]);
    pending['/api/glossary'].resolve([{id:'global',term:'全局术语',aliases:[],plain:'全局解释'}]);`);
  await ready;
  assert.equal(h.run(`S.vTermById.has('own')`),true);assert.equal(h.run(`S.termById.has('global')`),true);
});

test('read requests receive a default timeout and actionable reading recovery text',async()=>{
  const h=harness();
  restoreApi(h);
  h.run(`fetch=(_url,init)=>new Promise((resolve,reject)=>{init.signal?.addEventListener('abort',()=>reject(new Error('aborted')));})`);
  const request=h.run(`api('/api/cases/first')`);
  assert.equal(h.timers.at(-1).ms,12000);h.timers.at(-1).fn();
  await assert.rejects(request,e=>/重试/.test(e.message)&&!e.message.includes('恢复回答'));
});

test('optional metadata has a six second timeout independent from the twelve second report read',async()=>{
  const h=harness();restoreApi(h);
  h.run(`globalThis.transport={};fetch=(url,init)=>new Promise((resolve,reject)=>{
    transport[url]={resolve,signal:init.signal};init.signal.addEventListener('abort',()=>reject(new Error('aborted')));
  })`);
  const boot=h.run('boot()');
  assert.equal(h.timers.filter(t=>t.ms===6000).length,5);
  assert.equal(h.timers.filter(t=>t.ms===12000).length,1);
  h.timers.filter(t=>t.ms===6000).forEach(t=>t.fn());
  await h.run('startupReady');
  assert.equal(h.run(`transport['/api/health'].signal.aborted`),true);
  assert.equal(h.run(`transport['/api/cases/first'].signal.aborted`),false);
  h.ctx.caseResult=result('first');
  h.run(`transport['/api/cases/first'].resolve({ok:true,json:async()=>caseResult})`);await boot;
  assert.equal(h.run('rendered'),'first');
});

for(const [from,to] of [['me','cases'],['cases','me']]){
  test(`a late ${from} case-list read cannot replace the newer ${to} page`,async()=>{
    const h=harness();h.run(`location.hash='#/${from}'`);const first=h.run('route()');
    h.run(`globalThis.older=pending['/api/cases'];location.hash='#/${to}'`);const second=h.run('route()');
    h.run(`pending['/api/cases'].resolve([])`);await second;
    h.nodes.get('#view').innerHTML='newer page with draft';
    h.run(`older.resolve([{id:'stale'}])`);await first;
    assert.equal(h.nodes.get('#view').innerHTML,'newer page with draft');
    assert.equal(h.run('S.cases.length'),0);
    assert.equal(h.run('older.opts.signal.aborted'),true);
  });
}

for(const changed of ['case','version','audience','reopened preview']){
  test(`a late one-pager error cannot replace a different ${changed}`,async()=>{
    const h=harness();await openReport(h);
    const old=h.run('loadOnepager(ver())');
    if(changed==='case')await openReport(h,'second');
    if(changed==='version')h.run('S.case.versions.push({no:2,terms:[]});S.viewNo=2');
    if(changed==='audience')h.run(`S.audience='teller'`);
    if(changed==='reopened preview')h.nodes.set('#onepager',{innerHTML:'',isConnected:true});
    h.run(`$('#onepager').innerHTML='current print preview'`);
    h.run(`pending['/api/cases/first/onepager?audience=family&version=1'].reject(new Error('old timeout'))`);await old;
    assert.equal(h.nodes.get('#onepager').innerHTML,'current print preview');
  });
}

test('the current one-pager still displays its own response and failure',async()=>{
  const h=harness();await openReport(h);
  h.run('opBody=op=>op.title');
  const success=h.run('loadOnepager(ver())');
  h.run(`pending['/api/cases/first/onepager?audience=family&version=1'].resolve({title:'current contents'})`);await success;
  assert.equal(h.nodes.get('#onepager').innerHTML,'current contents');
  h.run(`S.audience='teller'`);const failed=h.run('loadOnepager(ver())');
  h.run(`pending['/api/cases/first/onepager?audience=teller&version=1'].reject(new Error('please retry'))`);await failed;
  assert.match(h.nodes.get('#onepager').innerHTML,/please retry/);
});

test('switching audiences back still ignores the first request in the same preview',async()=>{
  const h=harness();await openReport(h);
  h.run('opBody=op=>op.title');
  const old=h.run('loadOnepager(ver())');
  h.run(`globalThis.oldPrint=pending['/api/cases/first/onepager?audience=family&version=1'];S.audience='teller'`);
  const other=h.run('loadOnepager(ver())');
  h.run(`S.audience='family'`);const current=h.run('loadOnepager(ver())');
  h.run(`pending['/api/cases/first/onepager?audience=family&version=1'].resolve({title:'latest family preview'})`);await current;
  h.run(`oldPrint.reject(new Error('old family failure'))`);await old;
  h.run(`pending['/api/cases/first/onepager?audience=teller&version=1'].reject(new Error('old teller failure'))`);await other;
  assert.equal(h.nodes.get('#onepager').innerHTML,'latest family preview');
});

for(const target of ['case/second','cases','me']){
  test(`a completed review refresh cannot pull the reader back from ${target}`,async()=>{
    const h=harness();await openReport(h);
    const work=h.run(`refreshReviews({disabled:false,textContent:'',isConnected:true})`);
    assert.equal(h.run(`pending['/api/cases/first/reviews'].opts.method`),'POST');
    assert.equal(h.run(`pending['/api/cases/first/reviews'].opts.signal`),undefined);
    if(target==='case/second')await openReport(h,'second');
    else{
      h.run(`location.hash='#/${target}'`);const next=h.run('route()');
      h.run(`pending['/api/cases'].resolve([])`);await next;
    }
    h.ctx.updated={...result('first'),current:2};
    h.run(`pending['/api/cases/first/reviews'].resolve(updated)`);await work;
    assert.equal(h.run('location.hash'),`#/${target}`);
    assert.equal(h.run('S.case?.id'),target==='case/second'?'second':undefined);
    assert.match(h.run('notices.at(-1).message'),/案卷/);
  });
}

test('a completed update cannot replace a newly reopened copy of the same report',async()=>{
  const h=harness();await openReport(h);
  const work=h.run(`refreshReviews({disabled:false,textContent:'',isConnected:true})`);
  await openReport(h,'second');await openReport(h,'first');
  h.ctx.updated={...result('first'),current:2};
  h.run(`pending['/api/cases/first/reviews'].resolve(updated)`);await work;
  assert.equal(h.run('location.hash'),'#/case/first');
  assert.equal(h.run('S.case.current'),1);
});

test('a completed review refresh cannot replace a version revisited through references',async()=>{
  const h=harness();await openReport(h);
  h.run(`S.case.versions.push({no:2,terms:[]});S.case.current=2;S.viewNo=2;
    location.hash='#/case/first/v/2';globalThis.originalRoute=routeRequest;
    globalThis.originButton={disabled:false,textContent:'',isConnected:true}`);
  const work=h.run('refreshReviews(originButton)');
  h.ctx.history={replaceState(_state,_title,hash){h.ctx.location.hash=hash;}};
  const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
  h.run(source.slice(source.indexOf('function renderCase()'),source.indexOf('function caseHead(')));
  h.run(`isDesignReview=()=>false;caseHead=()=>'';conclusionHtml=()=>'';chartsHtml=()=>'';
    tabsHtml=()=>'';panelHtml=()=>'';assistHtml=()=>'';qiLauncherHtml=()=>'';
    initResearchDesign=()=>{};loadReviews=()=>{};loadOnepager=()=>{};scrollChat=()=>{}`);
  const view=h.nodes.get('#view');let markup=view.innerHTML;
  // Replacing the view removes the original action button from the live DOM.
  Object.defineProperty(view,'innerHTML',{get(){return markup;},set(value){markup=value;h.ctx.originButton.isConnected=false;}});
  h.run('selectRefVersion(1);selectRefVersion(2)');
  assert.equal(h.run('originalRoute===routeRequest'),true);
  assert.equal(h.ctx.originButton.isConnected,false);
  assert.equal(h.run('location.hash'),'#/case/first/v/2');
  h.ctx.updated={...result('first'),current:3,versions:[{no:1,terms:[]},{no:2,terms:[]},{no:3,terms:[]}]};
  h.run(`pending['/api/cases/first/reviews'].resolve(updated)`);await work;
  assert.equal(h.run('S.case.current'),2);
  assert.equal(h.run('location.hash'),'#/case/first/v/2');
  assert.match(h.run('notices.at(-1).message'),/案卷/);
});

function beginReview(h){
  h.run(`S.case.case={company_name:'first company'};S.rvStars=4;S.rvRel='customer';
    globalThis.reviewButton={disabled:false,textContent:''};
    globalThis.reviewForm={text:{value:'这里是十个字以上的真实经历描述'},nickname:{value:'测试用户'},
      isConnected:true,querySelector(){return reviewButton;}};
    reviewsPanel=()=>'<p>published reviews</p>'`);
  return h.run('submitReview(reviewForm)');
}

test('a published review cannot overwrite another companys reviews or draft',async()=>{
  const h=harness();await openReport(h);const work=beginReview(h);
  assert.equal(h.run(`pending['/api/reviews'].opts.method`),'POST');
  assert.equal(h.run(`pending['/api/reviews'].opts.body.company`),'first company');
  assert.equal(h.run(`pending['/api/reviews'].opts.signal`),undefined);
  await openReport(h,'second');
  h.run(`S.case.case={company_name:'second company'};S.reviews={company:'second company',count:0,reviews:[]};
    S.rvStars=2;S.rvRel='employee';$('#research-reviews-body').innerHTML='second company draft';
    pending['/api/reviews'].resolve({company:'first company',count:1,reviews:[]})`);
  await work;
  assert.equal(h.run('S.reviews.company'),'second company');
  assert.equal(h.run('S.rvStars'),2);assert.equal(h.run('S.rvRel'),'employee');
  assert.equal(h.nodes.get('#research-reviews-body').innerHTML,'second company draft');
  assert.match(h.run('notices.at(-1).message'),/原评价.*案卷/);
});

test('an old review publication cannot reset a new form in the same report',async()=>{
  const h=harness();await openReport(h);const work=beginReview(h);
  h.run(`reviewForm.isConnected=false;S.reviews={company:'first company',count:0,reviews:[]};
    S.rvStars=2;S.rvRel='employee';$('#research-reviews-body').innerHTML='new draft';
    pending['/api/reviews'].resolve({company:'first company',count:1,reviews:[]})`);
  await work;
  assert.equal(h.run('S.reviews.count'),0);
  assert.equal(h.run('S.rvStars'),2);assert.equal(h.run('S.rvRel'),'employee');
  assert.equal(h.nodes.get('#research-reviews-body').innerHTML,'new draft');
  assert.match(h.run('notices.at(-1).message'),/原评价.*案卷/);
});

test('an old failed review publication does not touch a current form or restore the old button',async()=>{
  const h=harness();await openReport(h);const work=beginReview(h);
  await openReport(h,'second');h.run(`S.case.case={company_name:'second company'};$('#rvErr').textContent='current validation';
    pending['/api/reviews'].reject(new Error('old publication failed'))`);
  await work;
  assert.equal(h.nodes.get('#rvErr').textContent,'current validation');
  assert.equal(h.run('reviewButton.disabled'),true);
  assert.match(h.run('notices.at(-1).message'),/原评价.*案卷/);
});

test('a review publication still updates the current form or shows its current failure',async()=>{
  for(const succeeds of [true,false]){
    const h=harness();await openReport(h);const work=beginReview(h);
    if(succeeds)h.run(`pending['/api/reviews'].resolve({company:'first company',count:1,reviews:[]})`);
    else h.run(`pending['/api/reviews'].reject(new Error('please retry'))`);
    await work;
    if(succeeds){
      assert.equal(h.run('S.reviews.count'),1);assert.equal(h.run('S.rvStars'),0);
      assert.equal(h.nodes.get('#research-reviews-body').innerHTML,'<p>published reviews</p>');
    }else{
      assert.match(h.nodes.get('#rvErr').textContent,/please retry/);
      assert.equal(h.run('reviewButton.disabled'),false);
    }
  }
});

function beginResolve(h){
  h.run(`$('#resDlg').dataset={jid:'A1',kind:'clarified'};$('#resDlg').open=true;
    globalThis.resolveEvent={preventDefault(){},target:{note:{value:'已核对'},isConnected:true}}`);
  return h.run('submitResolve(resolveEvent)');
}

test('a completed judgment update does not replace or navigate away from another report',async()=>{
  const h=harness();await openReport(h);const work=beginResolve(h);
  assert.equal(h.run(`pending['/api/cases/first/resolve'].opts.method`),'POST');
  assert.equal(h.run(`pending['/api/cases/first/resolve'].opts.body.note`),'已核对');
  await openReport(h,'second');h.ctx.updated={...result('first'),current:2};
  h.run(`pending['/api/cases/first/resolve'].resolve(updated)`);await work;
  assert.equal(h.run('S.case.id'),'second');assert.equal(h.run('location.hash'),'#/case/second');
  assert.match(h.run('notices.at(-1).message'),/案卷/);
});

test('an old failed judgment update cannot write into a newer report dialog',async()=>{
  const h=harness();await openReport(h);const work=beginResolve(h);
  await openReport(h,'second');h.run(`$('#resErr').textContent='new dialog draft'`);
  h.run(`pending['/api/cases/first/resolve'].reject(new Error('old failure'))`);await work;
  assert.equal(h.nodes.get('#resErr').textContent,'new dialog draft');
});

test('review and judgment updates still open their saved version when the reader stays',async()=>{
  for(const kind of ['reviews','resolve']){
    const h=harness();await openReport(h);
    const work=kind==='reviews'?h.run(`refreshReviews({disabled:false,textContent:'',isConnected:true})`):beginResolve(h);
    h.ctx.updated={...result('first'),current:2};
    h.run(`pending['/api/cases/first/${kind}'].resolve(updated)`);await work;
    assert.equal(h.run('S.case.current'),2);assert.equal(h.run('location.hash'),'#/case/first/v/2');
  }
});

test('the delayed change-banner scroll does not move a report opened after saving',async()=>{
  const h=harness();await openReport(h);
  const work=h.run(`refreshReviews({disabled:false,textContent:'',isConnected:true})`);
  h.ctx.updated={...result('first'),current:2};
  h.run(`pending['/api/cases/first/reviews'].resolve(updated)`);await work;
  await openReport(h,'second');
  h.run(`globalThis.scrolledWrong=false;$('.chg-banner').scrollIntoView=()=>{scrolledWrong=true;}`);
  h.timers.find(t=>t.ms===80).fn();
  assert.equal(h.run('scrolledWrong'),false);
});
