const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const scripts=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
const prepaint=scripts.find(script=>!(/\bsrc\s*=/.test(script[1])));

function initialModes(hash,search=''){
  assert.ok(prepaint,'the document establishes its shell without waiting for external scripts');
  const modes=new Set();
  vm.runInNewContext(prepaint[2],{
    location:{hash,search},URLSearchParams,
    document:{body:{classList:{add(...names){names.forEach(name=>modes.add(name));}}}},
  });
  return [...modes].sort();
}

test('the document establishes its workspace before the visible header is parsed',()=>{
  assert.ok(prepaint);
  assert.ok(prepaint.index>html.indexOf('<body>'));
  assert.ok(prepaint.index+prepaint[0].length<html.indexOf('<header'));
  assert.equal(scripts[0],prepaint);
  for(const hash of ['#/case/saved','#/case/saved/v/2','#/cases','#/library','#/guide','#/me']){
    assert.deepEqual(initialModes(hash),['dossier-shell','report-workspace','research-mode'],hash);
  }
});

test('the initial shell honors classic reports while other application sections stay modern',()=>{
  for(const hash of ['#/case/saved','#/case/saved/v/2']){
    assert.deepEqual(initialModes(hash,'?classic'),[],hash);
    assert.deepEqual(initialModes(hash,'?theme=light&classic=1'),[],hash);
  }
  for(const hash of ['#/cases','#/library','#/guide','#/me']){
    assert.deepEqual(initialModes(hash,'?classic'),['dossier-shell','report-workspace','research-mode'],hash);
  }
});

test('workspace navigation initializes before the application can render its first route',()=>{
  const source=script=>(script[1].match(/\bsrc="([^"?]+)/)||[])[1];
  const workspace=scripts.findIndex(script=>source(script)==='report-workspace.js');
  const application=scripts.findIndex(script=>source(script)==='app.js');
  assert.ok(workspace>=0);
  assert.ok(application>workspace);
  assert.doesNotMatch(scripts[workspace][1],/\b(?:async|defer)\b/);
});

test('archive and collection icons have native dimensions while stylesheets are loading',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
  for(const [name,kinds] of [
    ['archiveIcon',['file','arrow','chat','unknown']],
    ['collectionIcon',['search','file','bookmark','cards','folder','arrow','unknown']],
  ]){
    const definition=source.match(new RegExp(`function ${name}\\(kind\\) \\{[\\s\\S]*?\\n\\}`));
    assert.ok(definition,name);
    const icon=vm.runInNewContext(`${definition[0]};${name}`);
    for(const kind of kinds){
      const tag=icon(kind).match(/^<svg\b[^>]*>/)?.[0];
      assert.ok(tag,`${name}(${kind})`);
      assert.match(tag,/\bwidth="19"/);
      assert.match(tag,/\bheight="19"/);
    }
  }
});
