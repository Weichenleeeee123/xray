const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ctx=vm.createContext({URL});
vm.runInContext(`const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));`,ctx);
const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
vm.runInContext(app.slice(app.indexOf('function markText('),app.indexOf('function rawSourceLinks(')),ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../source-records.js'),'utf8'),ctx);
const render=(source,content,quotes=[])=>{
  ctx.record={source_id:source,kind:'commercial',content};ctx.quotes=quotes;
  const before=JSON.stringify(content),html=vm.runInContext('SourceRecords.render(record,quotes)',ctx);
  assert.equal(JSON.stringify(content),before,'presentation must not mutate evidence');
  return html;
};
const readable=html=>html.split('<details class="sr-json">')[0];

for(const [source,row,title] of [
  ['qcc_labor',{日期:'2019-01-21',案由:'解除劳动合同',案号:'案字01',机构:'仲裁委',它的角色:'未列明',被告:false},'解除劳动合同'],
  ['qcc_hearings',{案由:'买卖合同',法院:'某法院',它的角色:'原告',被告:false},'买卖合同'],
  ['qcc_filings',{案号:'立案01',日期:null},'立案01'],
  ['qcc_jobs',{职位:'工程师',月薪:'18-25k·14薪',地点:'杭州',学历:'硕士',日期:'2026-09-30'},'工程师'],
  ['qcc_licenses',{名称:'许可证',状态:'有效',有效期至:'2031-09-23',编号:'许可01',机关:'发证机关'},'许可证'],
  ['qcc_qualifications',{名称:'产品认证',状态:'撤销',发证日期:'2025-01-01'},'产品认证'],
  ['qcc_controller',{名称:'自然人',是自然人:true,总持股比例:'37.9208%',表决权比例:null},'自然人'],
]) test(`${source}: key records and all remaining fields stay readable`,()=>{
  const html=render(source,{'平台记录总数':30,'返回的明细':[row]});
  assert.match(html,/平台记录总数 <strong>30<\/strong> 条 · 本次取得 <strong>1<\/strong>/);
  assert.ok(readable(html).includes(title));
  for(const key of Object.keys(row)) assert.ok(readable(html).includes(key),key);
  assert.match(html,/查看已保存 JSON/);assert.doesNotMatch(readable(html),/<pre class="json">/);
});
test('changes retain before and after arrays and unknown fields',()=>{
  const html=readable(render('qcc_changes',{'返回的明细':[{项目:'住所变更',日期:'2026-09-07',变更前:['旧地址'],变更后:['新地址'],新字段:{nested:['补充']} }]}));
  assert.match(html,/sr-compare/);for(const v of ['旧地址','新地址','新字段','nested','补充'])assert.ok(html.includes(v));
});
test('financial table unions keys, keeps exact units, mixed periods and missing cells',()=>{
  const html=readable(render('qcc_finance',{'报告期':[{报告期:'2026年中报',营业总收入:'39.72 亿元'},{报告期:'2025年年报',净利润:'12.39 亿元',新指标:0}],说明:'只返回2期'}));
  assert.match(html,/财务报告期明细/);assert.match(html,/不同报告期口径/);
  for(const v of ['39.72 亿元','12.39 亿元','新指标','只返回2期','未提供'])assert.ok(html.includes(v));
  assert.match(html,/<td>0<\/td>/);
});
test('registry nested penalties and unknown structures recursively display every field',()=>{
  const html=readable(render('registry',{工商信息:{企业名称:'测试公司',地区信息:{城市:'杭州'},未知字段:[false,0,null,{X:'新值'}]},行政处罚:{摘要:'1条',行政处罚信息:[{决定文书号:'罚字01',处罚日期:'2022-09-06',金额:'8500元'}]},风险扫描:{失信信息:0}}));
  for(const v of ['城市','杭州','未知字段','否','新值','罚字01','8500元','失信信息'])assert.ok(html.includes(v));
  assert.doesNotMatch(html,/<pre class="json">/);
});
test('news links preserve provenance classification, escaping and unsafe URL text',()=>{
  const html=readable(render('qcc_news',{'平台记录总数':100,'全部返回新闻':[{标题:'<img onerror=bad>',日期:'2026-09-01',来源:'报道方',链接:'https://www.qcc.com/postnews/test.html'},{标题:'其他',链接:'javascript:alert(1)'}]}));
  assert.match(html,/&lt;img onerror=bad&gt;/);assert.doesNotMatch(html,/<img|href="javascript:/);
  assert.match(html,/平台转载页面/);assert.match(html,/本次取得 <strong>2<\/strong>/);assert.match(html,/javascript:alert/);
});
test('empty and failed content never invent zero records',()=>{
  assert.match(render('qcc_jobs',null),/没有取得/);
  assert.doesNotMatch(render('qcc_jobs',null),/0.*条/);
  assert.match(render('qcc_jobs',{'平台记录总数':0,'返回的明细':[]}),/本次取得 <strong>0<\/strong>/);
  assert.match(render('qcc_jobs',{}),/空对象/);
});
test('large samples collapse remaining rows and expose highlighted quotations',()=>{
  const rows=Array.from({length:25},(_,i)=>({职位:'职位'+i,地点:'杭州'}));
  let html=readable(render('qcc_jobs',{'返回的明细':rows}));
  assert.match(html,/其余 15 条/);assert.match(html,/职位24/);assert.doesNotMatch(html,/sr-more" open/);
  html=readable(render('qcc_jobs',{'返回的明细':rows},['职位24']));
  assert.match(html,/sr-more" open/);assert.match(html,/<mark>职位24<\/mark>/);
});
test('assets load renderer before app and raw dialog uses commercial renderer',()=>{
  const index=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
  assert.ok(index.indexOf('src="source-records.js')<index.indexOf('src="app.js'));
  assert.match(app,/kind === 'commercial'.*SourceRecords.render\(r, quotes \|\| \[\]\)/);
});
