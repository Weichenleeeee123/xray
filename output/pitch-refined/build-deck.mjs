import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile, FileBlob} from '@oai/artifact-tool';
import JSZip from 'jszip';

const root=process.cwd();
const runtime=String.raw`C:\Users\Weichen Li\.cache\codex-runtimes\codex-primary-runtime\dependencies`;
process.env.RUNTIME_NODE_MODULES=path.join(runtime,'node/node_modules');
process.env.RUNTIME_NODE=path.join(runtime,'node/bin/node.exe');
process.env.RUNTIME_PYTHON=path.join(runtime,'python/python.exe');
const skill=String.raw`C:\Users\Weichen Li\.codex\plugins\cache\openai-primary-runtime\presentations\26.905.11957\skills\presentations`;
const {finalizePresentation,resolvePresentationFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const rev=process.argv[2]||'v06';
const output=path.join(root,'output/pitch-refined');
const tmp=path.join(root,'.tmp/pitch-product/refined',rev);
const assets=path.join(output,'assets');
await fs.mkdir(tmp,{recursive:true});
const C={navy:'#222E39',paper:'#F7F0E0',ink:'#29333A',muted:'#756E61',gold:'#A67F45',lightGold:'#E2BC78',paper2:'#EEE4D1',line:'#D8CDB8',bookend:'#192A3D'};
const font=resolvePresentationFont({fontFamily:'Microsoft YaHei'});
const p=Presentation.create({slideSize:{width:1280,height:720}});
p.theme.colorScheme={name:'企er 编辑式路演',themeColors:{accent1:C.gold,accent2:C.lightGold,accent3:'#527A80',accent4:'#A44738',accent5:'#506348',accent6:'#795037',bg1:C.paper,bg2:C.paper2,tx1:C.ink,tx2:C.muted,dk1:C.ink,dk2:C.navy,lt1:C.paper,lt2:C.paper2,hlink:'#527A80',folHlink:'#795037'}};
const slides=new WeakMap(),imageCounts=new WeakMap(),crops=[];
const script=[
{title:'有出处的企业研究助手',seconds:15,notes:'大家好，我们做的是企 er，一个有出处的企业研究助手。把钱或信任交给一家公司之前，它帮助普通人看清：这次判断的依据是什么，还有哪些事情需要确认。',cue:'产品名之后稍停，先建立定位。',source:'README.md 产品主线与底线。小企插画沿用项目原有素材。'},
{title:'查询之后，判断之前',seconds:30,notes:'准备买理财、接受 offer，或者找一家公司合作时，人们能找到公司介绍、登记信息和新闻。但查到资料之后，还有一段工作：介绍和合同说的是不是同一个主体？宣传的数字和公开记录是不是同一个口径？这些记录，究竟能回答我这次的什么问题？企 er 把这段核对过程做成了产品。',cue:'每行只点出一个待确认的问题，不展开案例。',source:'README.md；docs/2026-10-02-xray-hackathon-prd.md。场景为产品定位，不声称完成用户调研。'},
{title:'公司全称，加一句需求',seconds:25,notes:'入口很简单：输入公司全称，再说一句这次想做什么。有宣传单或协议，也可以附上。小企把公开记录和用户材料收进同一份案卷，围绕这个需求组织报告。查询过程中，用户能看到不同资料来源的处理状态，完成后直接进入报告。',cue:'先指公司输入，再指需求；让整体产品画面停留数秒。',source:'research-room/app/page.tsx；web/app.js；backend/app/models.py。首页截图来自项目浏览器验收，不是设计效果图。'},
{title:'先读与本次需求有关的结论',seconds:35,notes:'报告先把企业概况和初步结论放在一起。比如理财，先核实收款主体和相关资格；求职，则先关心签约主体与用工信息。结论旁边就是依据，用户可以点开继续核对，再进入四个信号和详细资料。雷达只帮助快速浏览各维度的记录状态，不是给企业打安全分。',cue:'指向右侧初步结论与依据，雷达只带一句，不解释虚构公司的背景。',source:'docs/2026-10-03-report-overview-restoration.md；web/case-design.js；backend/app/scenarios。截图为虚构案例、未接模型的本地界面。需求影响范围、排序和表述。'},
{title:'企业说法的逐项核验',seconds:35,notes:'这是产品里最关键的一步。系统保留企业原话，把能核对的说法放到相关记录旁边。这里用虚构材料演示：宣传里的门店数量，与登记的分支机构数量，需要先讲清口径，再判断它能证明什么。每条对照保留出处，没有足够依据的说法也会继续标明。用户看到的是可检查的核验过程。',cue:'只讲这一条对照。强调门店与分支机构口径可能不同，不据此直接定性。',source:'backend/app/analysis/verify.py；backend/app/models.py Verdict。图片为虚构演示材料的原界面局部，未接模型。门店与分支机构不是天然等价指标。'},
{title:'解释报告，也能打开出处',seconds:30,notes:'看不懂某一条，还可以直接问小企。回答围绕当前案卷和所选版本展开，关键事实带出处，点开后能看到来源、日期和原始记录。这里展示的是基础答复的出处入口。接入在线模型后，程序仍会检查引用和引文，让用户有地方核对回答，而不是只能相信一段解释。',cue:'指一次出处标题与日期，给观众时间看清来源入口。',source:'backend/app/assistant.py；backend/tests/test_assistant_grounding_rewrite.py。截图为虚构案卷、未接模型时的基础答复出处，不作为在线模型回答质量证明。引用校验不等于零幻觉。'},
{title:'研究可以继续，依据可以回看',seconds:35,notes:'真正的判断往往不会一次结束。对方补了一份协议，用户收到新的回复，或者改变了需求，都能加入原案卷继续分析。新报告会说明哪些判断改变了、为什么改变，哪些没有变。旧版本同时保留，旧回答的引用也仍然回到回答时的版本，方便复盘当时掌握了什么。',cue:'指向第二版与第一版切换，说明新版本不会覆盖旧依据。',source:'backend/app/analysis/diff.py；backend/app/analysis/judgments.py；web/report-workspace.js。截图为虚构案卷版本选择器局部，预制示例，本次未重新联网。'},
{title:'规则与 AI 的分工',seconds:35,notes:'这套产品的关键设计，是把核验判定和自然语言解释分开。规则负责对照已有记录、给出判定并比较版本变化；AI 负责理解需求、读取材料、解释结果和回答问题。回答中的出处与引文再由程序校验。这样，一次研究保留下来的不仅有解释，还有可以复核的输入、规则结果和引用关系。',cue:'按左、右、下的顺序讲分工；不逐条念六个条目。',source:'README.md 底线；backend/app/analysis/verify.py；backend/app/assistant.py。相同规则输入得到相同规则判定，不声称模型输出完全确定或事实全量。'},
{title:'从研究报告，到下一次沟通',seconds:40,notes:'研究的结果还需要帮助下一次沟通。产品可以生成给家人看的一页结论，也可以生成网点提示单，把查到的依据、还缺的材料和该问的问题放在一起。比如这条：急用时多久能取回，相关条款写进合同了吗？下一步，我们希望先在网点沟通中验证，用户能否看懂依据与缺口，柜员能否把核实步骤讲具体。这是待验证方向，还没有银行采用或效果数据。',cue:'读右侧核实问题，再讲网点验证；避免把设想说成已有合作。',source:'backend/app/analysis/report.py onepager；docs/2026-10-02-xray-hackathon-prd.md。右侧问题来自虚构案例已有报告阅读画面，仅为核实问题示例；网点应用待验证。'},
{title:'企er',seconds:20,notes:'企 er 把公司资料、企业说法和用户需求，接成一份能追问、能补充、能回看的研究案卷。把钱或信任交出去之前，先把依据看清楚。欢迎体验，谢谢大家。',cue:'停在产品名与网址，不继续播放附录。',source:'README.md 产品主线；项目原有小企办公室插画。体验入口 qier.asia。'},
{title:'查询状态的四种含义',seconds:0,notes:'答辩备用。未匹配只描述本次查询范围，不能等同于企业没有相关问题。未覆盖与查询失败分别展示，避免把没有获取到记录误读成正常。每个来源还需结合查询时间与数据截至日。',source:'backend/app/models.py Coverage；backend/app/analysis/gaps.py；README.md 底线。'},
{title:'当前能力与验证计划',seconds:0,notes:'答辩备用。现有产品已经包含需求输入、报告、材料对照、引用追问、版本补充与一页结论。后续先验证网点沟通中的可理解性和核实动作，再讨论接入和商业模式。没有银行采用、收费、效果提升的已验证数字。资料来自公开记录和用户材料，不作企业安全担保，不替代最终决策。',source:'README.md；backend/app/analysis/report.py；docs/2026-10-02-xray-hackathon-prd.md 第12节。'}
];

function text(s,v,x,y,w,h,size=30,color=C.ink,bold=false,extra={}){const q=s.shapes.add({geometry:'textbox',name:v.replace(/\n/g,' ').slice(0,55),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});q.text=v;q.text.style={typeface:font,fontSize:size,color,bold,wrap:'square',autoFit:'none',verticalAlignment:'top',insets:{left:0,right:0,top:0,bottom:0},...extra};return q;}
function rule(s,x,y,w,color=C.line){s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function page(i,section,dark=false){const s=p.slides.add();slides.set(s,i+1);s.background.fill=dark?C.navy:C.paper;const fg=dark?C.lightGold:C.gold; text(s,section,72,40,1000,32,20,fg);text(s,`${String(i+1).padStart(2,'0')}`,1144,40,64,32,20,fg,false,{alignment:'right'});s.speakerNotes.textFrame.setText(`${script[i].seconds?'【主讲 '+script[i].seconds+' 秒】':'【答辩备用】'}\n${script[i].notes}\n\n${script[i].cue?'【动作】'+script[i].cue+'\n\n':''}【来源与口径】\n${script[i].source}`);return s;}
function title(s,v,dark=false){text(s,v,72,91,1136,74,45,dark?C.paper:C.navy,true);}
function foot(s,v,dark=false){text(s,v,72,670,1136,28,18,dark?'#D2C5AD':C.muted);}
async function pic(s,file,x,y,w,h,alt,crop){s.images.add({blob:new Uint8Array(await fs.readFile(path.join(assets,file))),contentType:file.endsWith('.png')?'image/png':'image/jpeg',alt,fit:crop?'cover':'contain',position:{left:x,top:y,width:w,height:h}});const idx=imageCounts.get(s)||0;imageCounts.set(s,idx+1);if(crop)crops.push({slide:slides.get(s),imageIndex:idx,crop});}
function table(s,values,x,y,width,height,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width,height,columnWidths:widths,values});t.borders.assign({fill:C.line,width:1,style:'solid'});for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.navy:(r%2?C.paper:C.paper2);cell.text.style={typeface:font,fontSize:26,bold:r===0||c===0,color:r===0?C.paper:C.ink,autoFit:'none',verticalAlignment:'middle',insets:{left:22,right:22,top:14,bottom:14}};}return t;}

// 01. Warm-paper cover, original brand art, generous quiet space.
{const s=page(0,'回响48H 黑客松    杭州银行「透视·真相」');text(s,'企er',70,132,720,139,106,C.navy,true);text(s,'有出处的\n企业研究助手',76,302,726,179,61,C.navy,true);await pic(s,'cover-goose.png',841,135,367,405,'项目原有小企放大镜插画');rule(s,76,576,1132);text(s,'把钱或信任交出去前，先把依据看清楚',76,608,1074,48,28,C.muted);}
// 02. Editorial comparison makes the problem concrete without invented metrics.
{const s=page(1,'为什么需要企er');title(s,'查询之后，判断之前');text(s,'查到的信息',72,204,465,45,27,C.muted);text(s,'真正要确认的事',602,204,606,45,27,C.gold);const rows=[['公司介绍与合同','说的是同一个主体吗？'],['宣传数字与公开记录','时间和指标口径一致吗？'],['一长串查询结果','哪些与这次决定有关？']];for(let i=0;i<3;i++){const y=284+i*114;rule(s,72,y-22,1136);text(s,rows[i][0],72,y,482,60,33,C.navy);text(s,rows[i][1],602,y,606,60,36,C.navy,true);}foot(s,'理财、求职与合作，都需要从资料走到具体问题。');}
// 03. One large authentic product view; no explanatory card grid.
{const s=page(2,'产品入口',true);title(s,'公司全称，加一句需求',true);await pic(s,'home-polished-desktop.jpg',72,169,1136,469,'企er研究室首页与公司、需求输入',{left:0.008,top:0.102,right:0.008,bottom:0.162});foot(s,'公开记录与用户材料，收进围绕本次需求的研究案卷。',true);}
// 04. Latest restored overview: visible radar and need-driven initial conclusion.
{const s=page(3,'产品体验  /  先看重点');title(s,'先读与本次需求有关的结论');await pic(s,'report-overview-restored-desktop.jpg',72,184,1136,383,'最新报告企业概况：六维雷达、初步结论与可点击依据',{left:214/1677,top:175/879,right:44/1677,bottom:226/879});text(s,'理财：收款主体与相关资格',72,594,562,48,27,C.navy,true);text(s,'求职：签约主体与用工信息',676,594,532,48,27,C.navy,true);foot(s,'虚构公司演示，未接模型。雷达展示记录状态，不是企业安全评分。');}
// 05. A single evidence detail, enlarged enough to read from the room.
{const s=page(4,'产品体验  /  逐项核验');title(s,'企业说法的逐项核验');text(s,'它说的，\n和查到的\n对得上吗？',72,219,425,241,51,C.navy,true);await pic(s,'report-claims-compact.jpg',540,222,668,355,'虚构材料中的门店宣传与登记分支机构的对照及来源入口',{left:0.556,top:0.293,right:0.0257,bottom:0.306});text(s,'先对齐主体、日期和口径，再讨论记录能证明什么。',72,605,1136,48,27,C.gold,true);foot(s,'虚构公司演示，未接模型。门店与登记分支机构可能采用不同口径。');}
// 06. Dark evidence page: a question and an authentic citation close-up.
{const s=page(5,'产品体验  /  追问依据',true);title(s,'解释报告，也能打开出处',true);text(s,'这条记录\n说明了什么？',72,225,495,175,53,C.paper,true);text(s,'选中一条，问小企。\n关键事实带回对应证据。',76,447,495,101,28,'#D2C5AD');await pic(s,'report-assistant-citations.jpg',622,238,586,310,'基础答复的原文出处，保留材料来源、官方记录、采集日期与原文入口',{left:455/1676,top:91/925,right:472/1676,bottom:437/925});text(s,'来源与日期，随回答一起保留',622,577,586,48,27,C.lightGold);foot(s,'虚构案卷的基础答复出处，未接模型。在线模型回答同样经过引用与引文校验。',true);}
// 07. Version history, supported by the real selector rather than a mock UI.
{const s=page(6,'产品体验  /  持续研究');title(s,'研究可以继续，依据可以回看');text(s,'v1',72,204,160,87,68,C.gold,true);text(s,'当时的材料与结论',240,216,520,53,36,C.navy,true);text(s,'旧回答的出处保留原版本',240,282,520,47,27,C.muted);rule(s,72,360,674);text(s,'v2',72,404,160,87,68,C.gold,true);text(s,'补充后的变化与原因',240,416,540,53,36,C.navy,true);text(s,'新回复、新协议，或修改需求',240,482,535,47,27,C.muted);await pic(s,'report-versions-mobile.jpg',832,199,376,404,'虚构案卷可切换第一版与第二版的真实产品控件',{left:80/390,top:171/844,right:15/390,bottom:356/844});foot(s,'虚构案卷版本选择器局部。示例沿用预制资料，本次未重新联网查询。');}
// 08. Method and differentiation; a quiet two-column typographic composition.
{const s=page(7,'产品方法',true);title(s,'规则与 AI 的分工',true);text(s,'规则',72,204,520,96,70,C.paper,true);text(s,'AI',710,204,498,96,70,C.lightGold,true);rule(s,72,331,496,'#55606B');rule(s,710,331,498,'#55606B');text(s,'对照已有记录\n生成核验判定\n逐项比较新旧版本',72,369,526,177,32,C.paper);text(s,'识别本次需求\n读取用户材料\n解释结果并回答问题',710,369,498,177,32,C.paper);text(s,'回答中的出处与引文，再由程序核验',72,600,1136,53,31,C.lightGold);foot(s,'相同规则输入得到相同判定。引用校验不代表对模型准确性的绝对保证。',true);}
// 09. Concrete output and a clearly labelled proposed validation setting.
{const s=page(8,'使用价值');text(s,'一页结论，\n带进下一次沟通',72,135,560,171,53,C.navy,true);text(s,'给家人',76,381,520,47,31,C.gold,true);text(s,'一起看依据，明确还缺什么',76,435,526,54,28);text(s,'给网点柜员',76,523,520,47,31,C.gold,true);text(s,'把需要核实的事项讲具体',76,577,526,54,28);text(s,'核实问题示例',710,142,498,43,25,C.gold);rule(s,710,207,498);text(s,'急用时多久能取回，\n提前取有没有违约金，\n写进合同了吗？',710,250,498,233,36,C.navy,true);text(s,'网点沟通是下一步拟验证方向',710,552,498,73,27,C.muted);foot(s,'右侧为虚构材料中的核实问题。尚无银行采用或效果数据，最终决策由人作出。');}
// 10. Product close, distinct from the opening; a real experience destination.
{const s=page(9,'企er    有出处的企业研究助手');text(s,'每次判断，\n都有依据可回看。',72,180,701,186,55,C.navy,true);text(s,'从一次查询，\n到一份可以继续研究的案卷。',76,426,698,104,31,C.muted);await pic(s,'closing-office.png',832,137,376,447,'原有小企办公室阅读报告插画');rule(s,76,617,1132);text(s,'qier.asia',76,643,698,52,36,C.gold,true);text(s,'欢迎体验',989,649,219,41,26,C.muted,false,{alignment:'right'});}
// 11. Native editable table for technical follow-up.
{const s=page(10,'答辩备用  /  资料覆盖');title(s,'查询状态的四种含义');table(s,[['状态','它实际说明什么'],['查到了','这个来源中有匹配记录'],['查了没有','本次查询范围内没有匹配记录'],['没查','数据源未覆盖，或本次未执行'],['查询失败','本次请求没有成功']],72,192,1136,382,[280,856]);text(s,'未覆盖，不能被读成正常',72,602,1136,55,37,C.navy,true);foot(s,'状态需结合来源、查询时间和数据截至日理解。');}
// 12. Honest readiness and next validation, no unsupported traction metrics.
{const s=page(11,'答辩备用  /  落地与边界');title(s,'当前能力与验证计划');text(s,'当前已实现',72,201,508,51,33,C.gold,true);text(s,'需求驱动的研究报告\n材料对照与来源追问\n版本补充与一页结论',72,279,530,181,31,C.navy);text(s,'下一步拟验证',710,201,498,51,33,C.gold,true);text(s,'用户能否读懂依据与缺口\n柜员能否说清核实步骤\n哪些资料仍需人工补充',710,279,498,181,30,C.navy);rule(s,72,535,1136);text(s,'公开记录有覆盖与时间边界，产品不作企业安全担保。',72,570,1136,51,29,C.navy,true);foot(s,'下一步先验证沟通效果，再评估试点接入与收费方式。');}

let candidate=path.join(tmp,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
// Preserve source image bytes and apply native PowerPoint source rectangles.
// The current bundled exporter otherwise replaces explicit crops with center-cover.
if(crops.length){const zip=await JSZip.loadAsync(await fs.readFile(candidate));for(const req of crops){const part=`ppt/slides/slide${req.slide}.xml`;let n=-1,count=0;const xml=(await zip.file(part).async('string')).replace(/<p:pic>[\s\S]*?<\/p:pic>/g,block=>{n++;if(n!==req.imageIndex)return block;if(!/<a:srcRect\b[^>]*\/>/.test(block))throw Error('Missing native crop');count++;const c=req.crop;return block.replace(/<a:srcRect\b[^>]*\/>/,`<a:srcRect l="${Math.round(c.left*100000)}" t="${Math.round(c.top*100000)}" r="${Math.round(c.right*100000)}" b="${Math.round(c.bottom*100000)}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" />`);});if(count!==1)throw Error('Ambiguous crop');zip.file(part,xml);}candidate=path.join(tmp,'candidate-native-crop.pptx');await fs.writeFile(candidate,await zip.generateAsync({type:'nodebuffer'}));}
const chars=script.slice(0,10).reduce((n,s)=>n+s.notes.replace(/[\s\p{P}\p{S}]/gu,'').length,0);
await fs.writeFile(path.join(tmp,'timing.json'),JSON.stringify({mainSlides:10,appendixSlides:2,seconds:script.reduce((n,s)=>n+s.seconds,0),spokenCharacters:chars,rehearsalMeasured:false},null,2));
// The finalizer requires a regular candidate inside the workspace, not a junction.
// Keep only the small package on C:, while previews remain on the D: build volume.
const staging=path.join(root,'.tmp/pitch-refined-packages',rev);
await fs.mkdir(staging,{recursive:true});
const boundedCandidate=path.join(staging,'candidate.pptx');
await fs.copyFile(candidate,boundedCandidate);
candidate=boundedCandidate;
const finalPath=path.join(output,`企er-设计感路演-${rev}.pptx`);
const receipt=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:path.join(runtime,'python/python.exe'),integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','11'],explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[11],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(staging,'validation.json')});
console.log(JSON.stringify({finalPath,chars,receipt}));
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<final.slides.items.length;i++){const slide=final.slides.items[i];await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await (await final.export({slide,format:'png',scale:1})).arrayBuffer()));await fs.writeFile(path.join(tmp,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await (await slide.export({format:'layout'})).text());}
await fs.writeFile(path.join(tmp,'montage.webp'),new Uint8Array(await (await final.export({format:'webp',montage:true,scale:0.5})).arrayBuffer()));
await fs.writeFile(path.join(tmp,'inspect.ndjson'),(await final.inspect({kind:'slide,textbox,image,table,notes',maxChars:1000000})).ndjson);
await fs.writeFile(path.join(output,`逐页讲稿-${rev}.md`),'# 企er · 五分钟路演讲稿\n\n10 页主讲，2 页答辩备用。主讲时长分配共 300 秒，正文约 '+chars+' 字（不计标点与空格），包含指示画面与翻页时间，尚未真人排练计时。\n\n'+script.map((s,i)=>`## ${i+1}. ${s.title}${s.seconds?'（'+s.seconds+' 秒）':'（答辩备用）'}\n\n${s.notes}\n\n${s.cue?'动作：'+s.cue+'\n\n':''}来源与口径：${s.source}\n`).join('\n'));
console.log('RENDERED_ALL_SLIDES');

