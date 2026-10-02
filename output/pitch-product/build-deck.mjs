import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile, FileBlob} from '@oai/artifact-tool';
import JSZip from 'jszip';

// Run from the repository root with the bundled Node runtime. No packages are installed.
const root=process.cwd();
const runtime=String.raw`C:\Users\Weichen Li\.cache\codex-runtimes\codex-primary-runtime\dependencies`;
process.env.RUNTIME_NODE_MODULES=path.join(runtime,'node/node_modules');
process.env.RUNTIME_NODE=path.join(runtime,'node/bin/node.exe');
process.env.RUNTIME_PYTHON=path.join(runtime,'python/python.exe');
const skill=String.raw`C:\Users\Weichen Li\.codex\plugins\cache\openai-primary-runtime\presentations\26.905.11957\skills\presentations`;
const {finalizePresentation,resolvePresentationFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const rev=process.argv[2]||'v01';
const output=path.join(root,'output/pitch-product');
const tmp=path.join(root,'.tmp/pitch-product',rev);
const assets=path.join(output,'assets');
await fs.mkdir(tmp,{recursive:true});
const C={navy:'#222E39',paper:'#F7F0E0',ink:'#29333A',muted:'#6F675B',gold:'#B88B4C',lightGold:'#E2BC78',paper2:'#EDE2CD',line:'#D9CCB4',deepGold:'#8A641F',teal:'#527A80',bookend:'#192A3D'};
const font=resolvePresentationFont({fontFamily:'Microsoft YaHei'});
const p=Presentation.create({slideSize:{width:1280,height:720}});
const slideNumbers=new WeakMap();
const imageCounts=new WeakMap();
const nativeCropRequests=[];
p.theme.colorScheme={name:'企er 黄铜蓝柜',themeColors:{accent1:C.gold,accent2:C.lightGold,accent3:C.teal,accent4:'#A44738',accent5:'#506348',accent6:'#795037',bg1:C.paper,bg2:C.paper2,tx1:C.ink,tx2:C.muted,dk1:C.ink,dk2:C.navy,lt1:C.paper,lt2:C.paper2,hlink:C.teal,folHlink:'#795037'}};

const script=[
{title:'企er',seconds:15,notes:'大家好，我们做的是企 er，一个有出处的企业研究助手。把钱或信任交给一家公司之前，用户最需要的，是弄清这次决定有哪些依据，还有什么没确认。',source:'README.md 开头与底线；docs/2026-10-03-qier-color-palette.md。'},
{title:'托付之前的判断难题',seconds:30,notes:'一个人准备买理财、接受 offer，或者找一家公司合作，通常已经看过不少介绍。但宣传、登记、年报和新闻分散在不同地方。查到一个数字，未必知道是不是同一家主体、是不是同一个时间点，更不知道它对这次决定意味着什么。企 er 要解决的，就是从一堆资料到一个具体判断之间的这段距离。',source:'docs/2026-10-02-xray-hackathon-prd.md 第 0–3 节。场景为产品定位，未声称用户调研结果。'},
{title:'公司全称，加一句需求',seconds:30,notes:'入口是公司名称，加一句这次要做什么，例如替家人了解理财，或核实刚收到的 offer。有宣传材料、合同，也可以一起提交。企 er 把查源、核验、出处和版本更新接成固定流程：查过什么、判断依据是什么、补材料后哪里变了，都留在同一个案卷里，按这次需求组织。',source:'README.md 快速开始；research-room/app；backend/app/models.py。'},
{title:'报告跟着这次需求组织',seconds:35,notes:'报告先回答这次最关心的问题。理财时先看收款主体和相关资格，求职时关注签约主体、劳动记录和是否要求先交钱。用户先读摘要，看到需要核实、查到记录、仍待确认和下一步，再看财务、信用、风险、口碑四个信号。要核对时，继续进入问询复核和详细信息。这样既能先看懂重点，也能深入找到每条判断的依据。',source:'web/report-workspace.js 与 report-workspace.css 当前阅读摘要；backend/app/scenarios；backend/app/analysis/report.py。截图为主代理于 2026-10-03 提供的 report-brief-v2.jpg，模型 off，虚构案例第 2 版。需求影响核验范围、排序和措辞，不声称覆盖所有资料。'},
{title:'把企业说法放到记录旁边',seconds:35,notes:'这里用一段虚构材料说明产品怎么工作。系统保留对方的原话，把能核对的说法逐条列出，再展示相关记录和规则判断。用户可以看到哪里相符、哪里有差异，也能看到哪些说法还无法核验。对照时，要同时核对主体、日期和指标口径。比如宣传的门店与登记的分支机构，就需要把口径讲清楚。材料里写了什么，也不等于事实已经成立。',source:'backend/app/models.py Verdict；backend/app/analysis/verify.py。截图为主代理于 2026-10-03 提供的 report-claims-compact.jpg，模型 off、公司为虚构，选取一张材料核对图的完整区域。此页只证明对照功能，不提供对真实公司的判断。'},
{title:'四类查询状态分开呈现',seconds:35,notes:'一份可信的报告，还必须把空白讲明白。查到了，表示这个来源有记录。查了没有，表示在本次范围内没有匹配记录。没查，表示数据源没有覆盖，或者这次没有执行。查询失败，则表示请求没有成功。这四种情况不能混在一起。企 er 会保留来源和时间，让用户知道结论能说到哪里。尤其是未覆盖，不能被读成正常。',source:'backend/app/models.py Coverage；backend/app/analysis/gaps.py；README.md 底线。'},
{title:'小企解释报告，关键事实带出处',seconds:35,notes:'如果用户看不懂某一条，可以选中它，再问小企。助手基于当前案卷和所选版本解释，关键事实带出处，点击引用能回到依据。图中是基础答复打开的第一版出处，当前没有连接模型。在线模型的回答同样要经过引用和引文校验。规则负责判定，AI 帮人理解材料和结果。聊天出现新情况，也需要加入案卷后重新分析。',source:'backend/app/assistant.py；backend/tests/test_assistant_grounding_rewrite.py。截图为主代理于 2026-10-03 提供的 report-assistant-citations.jpg，模型 off、虚构案例，选取出处弹窗的前两条来源。校验是具体边界措施，不代表零幻觉保证。'},
{title:'新材料进入新版本',seconds:35,notes:'实际判断很少一次结束。对方补了一份协议，用户收到新的回复，或者自己的需求变了，都可以继续补充。系统保留原来的版本，再生成新报告，并逐项说明哪里变了、为什么变，哪些保持不变。证据仍不足，也会继续写明。旧回答的引用会回到原来的版本，所以用户能复盘当时基于什么材料得出那条判断。',source:'backend/app/analysis/diff.py；backend/app/analysis/judgments.py；backend/app/models.py Version；docs/demo-runbook.md 旧版引用验收。'},
{title:'一页报告，支持下一步核实',seconds:35,notes:'对个人，企 er 把查到的依据、还缺的资料和该问的问题放进一页报告，方便和家人一起讨论。对银行网点，现有的提示单可以作为沟通材料，帮助柜员把需要确认的事项讲具体。我们希望先验证这样一段沟通，能否帮助用户读懂来源、识别缺口，再决定补什么材料。它提供研究依据，最终决策仍由人作出。',source:'backend/app/analysis/report.py onepager family/teller；docs/2026-10-02-xray-hackathon-prd.md 第 12 节。网点使用是拟验证方向，未声称客户采用或银行接入。'},
{title:'有出处的企业研究助手',seconds:15,notes:'企 er 把一次查询接成一份可以追问、补充和回看的案卷。把钱或信任交出去前，先把依据看清楚。谢谢大家。',source:'README.md 产品主线。'},
{title:'产品边界与当前能力',seconds:0,notes:'答辩备用页，不计入五分钟主讲。说明数据、规则和 AI 各自承担的工作。联网来源受接口配置、查询时间和覆盖范围限制。产品不打安全分，也不对企业作安全担保。',source:'README.md 数据与底线；backend/app/models.py；backend/app/assistant.py。'},
{title:'答辩时的四个重点',seconds:0,notes:'答辩备用页，不计入五分钟主讲。问到商业化时，先讲拟验证的网点沟通场景，不声称已有客户、收费、合作或效果数字。问到数据完整性时，区分未覆盖和未匹配，明确公开记录的能力边界。',source:'README.md；docs/2026-10-02-xray-hackathon-prd.md 第 12 节。'}
];
const cues=['开场停留，读完产品名再进入判断问题。','让主问题停留两秒，再解释下面两类困难。','指向公司输入与研究需求，预留约四秒。','依次指向四层阅读路径，预留约五秒。','只指原话、记录和无法核验的位置，预留约六秒，不讲公司历史。','逐行指向四类状态，预留约四秒。','指向回答的出处入口与规则边界，预留约六秒。','在 v1、补充、v2 三处各停顿，预留约五秒。','强调网点用途是拟验证场景，预留约三秒。','收尾停留，不继续播放附录。'];

function text(slide,value,x,y,w,h,size=30,color=C.ink,bold=false,extra={}){
const shape=slide.shapes.add({geometry:'textbox',name:value.replace(/\n/g,' ').slice(0,45),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
shape.text=value;shape.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none',wrap:'square',verticalAlignment:'top',insets:{left:0,right:0,top:0,bottom:0},...extra};return shape;}
function line(slide,x,y,w,color=C.line){slide.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1.5}});}
async function pic(slide,file,x,y,w,h,alt,crop){const full=path.join(assets,file);slide.images.add({blob:new Uint8Array(await fs.readFile(full)),contentType:file.endsWith('.png')?'image/png':'image/jpeg',alt,fit:crop?'cover':'contain',position:{left:x,top:y,width:w,height:h}});const imageIndex=imageCounts.get(slide)||0;imageCounts.set(slide,imageIndex+1);if(crop)nativeCropRequests.push({slide:slideNumbers.get(slide),imageIndex,file,crop});}
function page(i,title,{dark=false}={}){const s=p.slides.add();slideNumbers.set(s,i+1);s.background.fill=dark?C.navy:C.paper;const fg=dark?C.paper:C.navy;if(title){text(s,title,68,55,1144,76,46,fg,true);text(s,'企er',68,666,150,26,17,dark?C.lightGold:C.muted,true);text(s,`${i+1}`,1145,666,68,26,17,dark?C.lightGold:C.muted,false,{alignment:'right'});}s.speakerNotes.textFrame.setText(`${script[i].seconds?`【主讲 ${script[i].seconds} 秒】`:'【答辩备用，不计入主讲】'}\n${script[i].notes}${cues[i]?`\n\n【动作与停留】\n${cues[i]}`:''}\n\n【来源与口径】\n${script[i].source}`);return s;}
function table(slide,values,x,y,width,height,widths){const t=slide.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width,height,columnWidths:widths,values});t.borders.assign({fill:C.line,width:1,style:'solid'});for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.navy:(r%2?C.paper:C.paper2);cell.text.style={typeface:font,fontSize:r===0?25:26,bold:r===0||c===0,color:r===0?C.paper:C.ink,autoFit:'none',verticalAlignment:'middle',insets:{left:18,right:18,top:13,bottom:13}};}return t;}

// 01. Original illustration and minimal product statement.
{const s=page(0,null);s.background.fill=C.bookend;await pic(s,'cover-goose.png',628,0,652,720,'原有品牌小企放大镜插画');text(s,'企er',70,135,535,135,104,C.paper,true);text(s,'有出处的\n企业研究助手',75,320,535,160,54,C.paper,true);text(s,'把钱或信任交出去前，\n先把依据看清楚',77,525,510,88,30,C.lightGold);text(s,'回响48H 黑客松  杭州银行「X-Ray 透视·真相」',77,50,1000,35,21,C.lightGold);}
// 02. User decision, expressed as two information problems.
{const s=page(1,'托付之前的判断难题');text(s,'资料已经很多，\n哪些与这次决定有关？',70,170,1020,150,58,C.navy,true);line(s,70,360,1140);text(s,'信息散在各处',72,401,470,48,32,C.navy,true);text(s,'公司介绍、登记、年报和新闻\n需要放在一起核对',72,464,470,104,28);text(s,'记录还需要读懂',700,401,475,48,32,C.navy,true);text(s,'主体、时间和指标口径\n会影响它能支持什么判断',700,464,475,104,28);}
// 03. Product entry.
{const s=page(2,'公司全称，加一句需求');await pic(s,'home-polished-desktop.jpg',68,167,820,462,'小企研究室首页，输入公司与研究需求');text(s,'公司全称',936,176,284,50,31,C.navy,true);text(s,'明确这次查谁',936,228,284,50,26);text(s,'这次想做什么',936,334,284,50,31,C.navy,true);text(s,'理财、求职或合作\n重点随需求改变',936,386,284,95,26);text(s,'材料可选',936,526,284,44,28,C.deepGold,true);text(s,'宣传单、合同、回复',936,574,284,42,24,C.muted);}
// 04. Report structure; editable labels carry the key message.
{const s=page(3,'报告跟着这次需求组织');text(s,'阅读摘要',68,151,264,44,29,C.navy,true);text(s,'四个信号',338,151,264,44,29,C.navy);text(s,'问询复核',608,151,264,44,29,C.navy);text(s,'详细信息与来源',878,151,334,44,29,C.navy);await pic(s,'report-brief-v2.jpg',68,214,1144,371,'新版阅读摘要局部，完整保留下一步及需要核实、查到记录、仍待确认三栏',{left:0.127,top:0.483,right:0.027,bottom:0.02});text(s,'虚构公司演示画面，未接模型',68,622,1144,30,22,C.muted);}
// 05. A short function proof, not a company history.
{const s=page(4,'把企业说法放到记录旁边');await pic(s,'report-claims-compact.jpg',68,190,745,394,'虚构公司的门店宣传与登记记录对照，保留标题、完整图表及来源入口',{left:0.556,top:0.293,right:0.0257,bottom:0.306});text(s,'原话保留',857,179,356,47,32,C.navy,true);text(s,'能点开材料原文',857,235,356,55,27);text(s,'记录可查',857,331,356,47,32,C.navy,true);text(s,'同时核对主体、\n日期与指标口径',857,389,356,100,27);text(s,'无法核验也写明',857,535,356,47,31,C.deepGold,true);text(s,'虚构公司演示。材料有记载，不代表宣称属实',68,626,1140,30,22,C.muted);}
// 06. Editable evidence-status table.
{const s=page(5,'四类查询状态分开呈现');table(s,[['状态','它说明什么'],['查到了','这个来源中有匹配记录'],['查了没有','本次查询范围内没有匹配记录'],['没查','数据源未覆盖，或本次未执行'],['查询失败','本次请求没有成功']],68,163,1144,372,[300,844]);text(s,'未覆盖，不能当成正常',68,569,1144,57,39,C.navy,true);}
// 07. Assistant with evidence and deterministic boundary.
{const s=page(6,'小企解释报告，关键事实带出处');await pic(s,'report-assistant-citations.jpg',68,186,724,384,'基础答复打开的第一版出处弹窗局部，显示原材料与官方记录的来源和日期',{left:0.2715,top:0.0984,right:0.2798,bottom:0.47});text(s,'选中一条，再问',843,178,370,50,31,C.navy,true);text(s,'引用回到对应证据',843,242,370,82,28);text(s,'规则负责判定',843,363,370,47,31,C.navy,true);text(s,'AI 帮人读懂材料和结果',843,421,370,94,27);text(s,'新情况加入案卷，\n再生成新版本',843,546,370,90,27,C.muted);text(s,'虚构公司演示，基础答复的出处',68,622,740,34,22,C.muted);}
// 08. Editable version progression, with no invented company results.
{const s=page(7,'新材料进入新版本');text(s,'v1',69,173,197,95,64,C.deepGold,true);text(s,'原来的报告',270,179,830,57,39,C.navy,true);text(s,'保留当时的材料、判断和出处',273,243,874,61,29);line(s,69,327,1140);text(s,'补充',69,357,197,73,41,C.deepGold,true);text(s,'新材料、对方回复，或修改需求',273,360,925,60,33,C.navy,true);line(s,69,449,1140);text(s,'v2',69,479,197,95,64,C.deepGold,true);text(s,'变了什么，为什么变',273,479,908,60,39,C.navy,true);text(s,'没变的继续列出，旧引用仍回到旧版本',273,549,908,76,29);}
// 09. Concrete product value and a clearly proposed validation direction.
{const s=page(8,'一页报告，支持下一步核实');text(s,'已知的依据',69,175,541,65,42,C.navy,true);text(s,'还缺的资料',69,275,541,65,42,C.navy,true);text(s,'该问的问题',69,375,541,65,42,C.navy,true);text(s,'带进下一次讨论',694,181,514,62,39,C.deepGold,true);text(s,'个人与家人\n一起看懂，再补充核实',696,292,513,118,31);text(s,'拟验证的网点场景\n用提示单把待确认事项讲具体',696,455,517,115,29);text(s,'提供研究依据，最终决策由人作出',69,579,550,60,28,C.muted);}
// 10. Closing, original illustration.
{const s=page(9,null);s.background.fill=C.bookend;await pic(s,'closing-office.png',674,0,606,720,'原有办公室中小企阅读报告的插画');text(s,'企er',72,140,540,90,71,C.paper,true);text(s,'把钱或信任交出去前，\n先把依据看清楚',72,300,587,169,45,C.paper,true);text(s,'有出处的企业研究助手',74,515,579,50,31,C.lightGold);text(s,'基于公开资料，不作安全担保',74,627,579,36,22,C.paper);}
// 11. Optional backup slide.
{const s=page(10,'产品边界与当前能力');table(s,[['环节','当前承担的工作'],['数据','汇集公开记录与用户材料，保留来源和查询状态'],['确定性规则','按已有记录与规则生成核验判定，逐项比对版本'],['AI','识别需求、读取材料、解释报告、回答问题'],['用户','核对缺口，补充信息，作出最终决定']],68,165,1144,393,[260,884]);text(s,'不打安全分，不作安全担保。联网资料受配置与覆盖范围限制',68,590,1144,56,28,C.navy,true);}
// 12. Concise defense anchors, written as complete statements.
{const s=page(11,'答辩时的四个重点');text(s,'为什么不直接给安全分',68,169,526,54,31,C.navy,true);text(s,'公开记录有范围与时间边界，\n缺口不能折算成一个“安全”数字。',68,230,526,105,26);text(s,'与普通搜索的区别',693,169,519,54,31,C.navy,true);text(s,'围绕一次需求组织证据，\n保留宣称对照、出处和版本变化。',693,230,519,105,26);line(s,68,372,1144);text(s,'数据不完整时怎么办',68,414,526,54,31,C.navy,true);text(s,'四类状态分开，列出待确认事项，\n补材料后继续研究。',68,475,526,105,26);text(s,'下一步先验证什么',693,414,519,54,31,C.navy,true);text(s,'在网点沟通中验证：用户能否读懂\n依据与缺口，柜员能否说清下一步。',693,475,519,105,26);}

let candidate=path.join(tmp,`candidate-${rev}.pptx`);
await (await PresentationFile.exportPptx(p)).save(candidate);
// The bundled exporter currently replaces explicit image.crop with center-cover.
// Preserve original image bytes and encode native PowerPoint source rectangles.
// Keep the unmodified export, and validate/render the resulting package below.
if(nativeCropRequests.length){
  const zip=await JSZip.loadAsync(await fs.readFile(candidate));
  for(const req of nativeCropRequests){
    const part=`ppt/slides/slide${req.slide}.xml`;
    let n=-1,changed=0;
    const xml=(await zip.file(part).async('string')).replace(/<p:pic>[\s\S]*?<\/p:pic>/g,block=>{
      n++;if(n!==req.imageIndex)return block;
      if(!/<a:srcRect\b[^>]*\/>/.test(block))throw new Error(`Native crop target is missing on slide ${req.slide}`);
      changed++;
      const c=req.crop;
      return block.replace(/<a:srcRect\b[^>]*\/>/,`<a:srcRect l="${Math.round(c.left*100000)}" t="${Math.round(c.top*100000)}" r="${Math.round(c.right*100000)}" b="${Math.round(c.bottom*100000)}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" />`);
    });
    if(changed!==1)throw new Error(`Ambiguous native crop target on slide ${req.slide}`);
    zip.file(part,xml);
  }
  candidate=path.join(tmp,`candidate-native-crop-${rev}.pptx`);
  await fs.writeFile(candidate,await zip.generateAsync({type:'nodebuffer'}));
  await fs.writeFile(path.join(tmp,'native-crops.json'),JSON.stringify(nativeCropRequests,null,2));
}
await fs.writeFile(path.join(tmp,'authored-proto.json'),JSON.stringify(p.toProto(),null,2));
const chars=script.slice(0,10).reduce((n,s)=>n+s.notes.replace(/[\s\p{P}\p{S}]/gu,'').length,0);
await fs.writeFile(path.join(tmp,'timing.json'),JSON.stringify({mainSlides:10,appendixSlides:2,allocatedSeconds:300,spokenCharacters:chars,characterRatePerMinuteIncludingPauses:chars/5,caseExplanationSeconds:35,estimatedSpeakingRate:250,estimatedSpeakingSeconds:Math.round(chars/250*60),visualDwellAndTransitionsSeconds:40,rehearsalMeasured:false,perSlide:script.slice(0,10).map((s,i)=>({slide:i+1,seconds:s.seconds,characters:s.notes.replace(/[\s\p{P}\p{S}]/gu,'').length,cue:cues[i]}))},null,2));
if(process.argv.includes('--draft-only')){
  const draft=await PresentationFile.importPptx(await FileBlob.load(candidate));
  for(const i of [0,2,3,9,10]){const png=await draft.export({slide:draft.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));}
  console.log(JSON.stringify({candidate,chars,draftOnly:true}));
  process.exit(0);
}
const finalPath=path.join(output,`企er-产品路演-5分钟-${rev}.pptx`);
const receipt=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:path.join(runtime,'python/python.exe'),integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','6','--require-native-table-slide','11'],explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[6,11],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(tmp,'validation.json')});
console.log(JSON.stringify({finalPath,chars,receipt},null,2));
// Re-import the actual final package, then render every slide for visual review.
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<final.slides.items.length;i++){const slide=final.slides.items[i];const png=await final.export({slide,format:'png',scale:1});await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));const layout=await slide.export({format:'layout'});await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await layout.text());}
const montage=await final.export({format:'webp',montage:true,scale:0.5});await fs.writeFile(path.join(tmp,'montage.webp'),new Uint8Array(await montage.arrayBuffer()));
await fs.writeFile(path.join(tmp,'final-inspect.ndjson'),(await final.inspect({kind:'slide,textbox,image,table,notes',maxChars:1000000})).ndjson);
await fs.writeFile(path.join(output,'逐页讲稿-5分钟.md'),'# 企er五分钟产品路演讲稿\n\n主讲 10 页，答辩附录 2 页。主讲分配 300 秒。正文约 '+chars+' 字（不计标点），按约 250 字/分钟讲述，加上约 40 秒指示画面和翻页，预计约五分钟；尚未真人排练计时。\n\n'+script.map((s,i)=>`## ${i+1}. ${s.title}${s.seconds?`（${s.seconds}秒）`:'（答辩附录）'}\n\n${s.notes}\n${cues[i]?`\n动作与停留：${cues[i]}\n`:''}\n来源与口径：${s.source}\n`).join('\n'));
await fs.writeFile(path.join(output,'build-deck.mjs'),await fs.readFile(new URL(import.meta.url)));
