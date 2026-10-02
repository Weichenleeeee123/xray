import test from 'node:test';
import assert from 'node:assert/strict';
import { proxyBackend } from '../backend-proxy.ts';

test('production proxy preserves complete input, query, status and streamed response', async () => {
  const body = {company_name:'测试公司',need:'完整需求',material_text:'原始材料\n第2行'};
  const request = new Request('https://penguin.test/api/runs?after=4', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const response = await proxyBackend(request,'https://backend.test',async (r) => {
    assert.equal(r.url,'https://backend.test/api/runs?after=4');
    assert.deepEqual(await r.json(),body);
    assert.equal(r.headers.get('X-Forwarded-Host'),'penguin.test');
    return new Response('{"type":"begin"}\n',{status:202,headers:{'Content-Type':'application/x-ndjson'}});
  });
  assert.equal(response.status,202);
  assert.match(response.headers.get('Content-Type'),/ndjson/);
  assert.equal(await response.text(),'{"type":"begin"}\n');
});
test('report, assets and offline replay use the same configured backend', async () => {
  for (const [path,want] of [['/xray/','/xray/'],['/xray/app.js','/xray/app.js'],['/research-assets/goose-actions-v2.png','/research-assets/goose-actions-v2.png'],['/demo/','/demo/']]) {
    const r=await proxyBackend(new Request('https://penguin.test'+path),'https://backend.test',async req=>{
      assert.equal(req.url,'https://backend.test'+want); return new Response('asset');
    });
    assert.equal(r.status,200);
  }
  assert.equal(await proxyBackend(new Request('https://penguin.test/office.png'),'https://backend.test'),null);
  const redirect=await proxyBackend(new Request('https://penguin.test/xray'),'https://backend.test');
  assert.equal(redirect.headers.get('location'),'https://penguin.test/xray/');
});
test('upstream errors stay errors and gateway failures are actionable JSON', async () => {
  const req=new Request('https://penguin.test/api/runs');
  assert.equal((await proxyBackend(req,undefined)).status,503);
  assert.equal((await proxyBackend(req,'https://penguin.test')).status,503);
  assert.equal((await proxyBackend(req,'https://backend.test',async()=>{throw new Error('private error')})).status,502);
  const r=await proxyBackend(req,'https://backend.test',async()=>Response.json({detail:'字段不完整'},{status:422}));
  assert.equal(r.status,422); assert.equal((await r.json()).detail,'字段不完整');
});

test('redirects preserve the mounted report path without duplicating /xray', async () => {
  const r = await proxyBackend(new Request('https://penguin.test/xray/app.js'),
    'https://backend.test/prefix', async () => new Response(null, {
      status: 307, headers: {location: 'https://backend.test/prefix/xray/?saved=1'},
    }));
  assert.equal(r.headers.get('location'), '/xray/?saved=1');
});

test('multipart document bytes and original filename survive forwarding', async () => {
  const body=new FormData();
  body.append('file',new Blob([new Uint8Array([0,255,10,13,88])]),'合同.pdf');
  const req=new Request('https://penguin.test/api/files/read',{method:'POST',body});
  const response=await proxyBackend(req,'https://backend.test',async r=>{
    const received=await r.formData(); const file=received.get('file');
    assert.equal(file.name,'合同.pdf');
    assert.deepEqual([...new Uint8Array(await file.arrayBuffer())],[0,255,10,13,88]);
    return Response.json({text:'完整材料'});
  });
  assert.equal((await response.json()).text,'完整材料');
});
