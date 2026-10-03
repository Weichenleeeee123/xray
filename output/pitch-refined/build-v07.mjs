// 企er 路演 v07：编辑式重排。运行：
//   "<codex runtime>/node/bin/node.exe" output/pitch-refined/build-v07.mjs
// 产出 output/pitch-refined/企er-路演-v07.pptx，预览图写到 .tmp/pitch-v07/render/。
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const NM = 'C:/Users/Weichen Li/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/';
const require = createRequire(NM);
const pptxgen = require('pptxgenjs');

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const A = (f) => path.join(here, 'assets', f);
const OUT = path.join(here, '企er-路演-v07.pptx');
const RENDER = path.join(root, '.tmp/pitch-v07/render');

// ---------- tokens ----------
const C = {
  navy: '192A3D', navy2: '23364A', navyLine: '3A4855',
  paper: 'F5F0E6', card: 'FFFCF6', paper2: 'EDE5D5', line: 'DCD2C0',
  ink: '1D2935', muted: '6F685C',
  brass: 'A27536', brassL: 'D8B574',
  cream: 'F3ECDD', creamM: 'B4AB9B',
  red: 'B0432E', amber: 'B67F24', grey: '8A8478', green: '4F7A62',
};
const SERIF = 'Noto Serif SC';
const SANS = 'Microsoft YaHei';
const W = 13.333, M = 0.75, CW = W - 2 * M;

const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';
p.title = '企er · 有出处的企业研究助手';
p.author = '企er 团队';
p.theme = {headFontFace: SERIF, bodyFontFace: SANS};

// ---------- helpers ----------
const tw = (s, pt) => [...s].reduce((n, ch) => n + (/[\u2E80-\uFFFF\u2018-\u201D\u2026]/.test(ch) ? 1 : 0.56), 0) * pt / 72;
const shadow = () => ({type: 'outer', blur: 10, offset: 3, angle: 90, color: '000000', opacity: 0.16});

function T(s, text, o) {
  s.addText(text, {isTextBox: true, margin: 0, fontFace: SANS, color: C.ink, valign: 'top', ...o});
}
function slide(dark, n) {
  const s = p.addSlide();
  made.push(s);
  s.background = {color: dark ? C.navy : C.paper};
  if (n) T(s, String(n).padStart(2, '0'), {x: W - M - 0.6, y: 7.0, w: 0.6, h: 0.25, fontSize: 10, color: dark ? C.creamM : C.muted, align: 'right'});
  return s;
}
function kicker(s, text, dark) {
  T(s, text, {x: M, y: 0.48, w: CW, h: 0.3, fontSize: 12, color: dark ? C.brassL : C.brass, charSpacing: 2, bold: true});
}
function title(s, text, dark, o = {}) {
  T(s, text, {x: M, y: 0.82, w: CW, h: 0.75, fontFace: SERIF, fontSize: 32, bold: true, color: dark ? C.cream : C.ink, ...o});
}
function foot(s, text, dark) {
  T(s, text, {x: M, y: 6.98, w: CW - 1, h: 0.28, fontSize: 10.5, color: dark ? C.creamM : C.muted});
}
// 出处标签：全片唯一的视觉母题。
function chip(s, text, x, y, o = {}) {
  const pt = o.pt || 10.5, h = o.h || 0.3, w = tw(text, pt) + 0.32;
  const ax = o.right ? x - w : x;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, {x: ax, y, w, h, rectRadius: 0.06,
    fill: {color: o.fill || (o.dark ? C.navy2 : C.card)}, line: {color: o.line || (o.dark ? C.brassL : C.brass), width: 0.75}});
  T(s, text, {x: ax, y, w, h, fontSize: pt, color: o.color || (o.dark ? C.brassL : C.brass), align: 'center', valign: 'middle'});
  return w;
}
function badge(s, kind, x, y, d = 0.36) {
  const map = {bad: [C.red, '✕'], warn: [C.amber, '!'], miss: [C.amber, '?'], ok: [C.green, '✓']};
  const [col, g] = map[kind];
  s.addShape(p.shapes.OVAL, {x, y, w: d, h: d, fill: {color: col}, line: {color: col, width: 0}});
  T(s, g, {x, y: y - 0.01, w: d, h: d, fontSize: d * 34, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle'});
}
function pill(s, text, x, y, col, o = {}) {
  const pt = o.pt || 13, h = o.h || 0.4, w = o.w || tw(text, pt) + 0.4;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, {x, y, w, h, rectRadius: 0.2, fill: {color: col}, line: {color: col, width: 0}});
  T(s, text, {x, y, w, h, fontSize: pt, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle'});
}
function card(s, x, y, w, h, o = {}) {
  s.addShape(p.shapes.ROUNDED_RECTANGLE, {x, y, w, h, rectRadius: o.r ?? 0.08,
    fill: {color: o.fill || C.card}, line: {color: o.line || C.line, width: o.lw ?? 0.75},
    ...(o.shadow ? {shadow: shadow()} : {})});
}
function hline(s, x, y, w, col) { s.addShape(p.shapes.LINE, {x, y, w, h: 0, line: {color: col, width: 0.75}}); }

// 自由多边形 / 折线：pts 为绝对坐标（英寸）。
function poly(s, pts, o = {}, close = true) {
  const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
  const x = Math.min(...xs), y = Math.min(...ys);
  const w = Math.max(Math.max(...xs) - x, 0.01), h = Math.max(Math.max(...ys) - y, 0.01);
  const points = pts.map(([px, py]) => ({x: px - x, y: py - y}));
  if (close) points.push({close: true});
  s.addShape(p.shapes.CUSTOM_GEOMETRY, {x, y, w, h, points, fill: o.fill || {type: 'none'}, line: o.line || {type: 'none'}});
}
// 与产品 web/case-design.js researchRadar 同一套半径与文案（f723b1b 起五维）。
const RADAR_LEVEL = {ok: 115, warn: 78, miss: 62, bad: 46};
const RADAR_TEXT = {ok: '未见异常', warn: '有待关注', bad: '有异常记录', miss: '缺应有记录', none: '未覆盖'};
const RADAR_TONE = {bad: 'ED9B89', none: 'AC9781'};
function radar(s, cx, cy, R, dims) {
  const n = dims.length;
  const pt = (i, r) => [cx + Math.sin(i * 2 * Math.PI / n) * r, cy - Math.cos(i * 2 * Math.PI / n) * r];
  [0.25, 0.5, 0.75, 1].forEach((f) => poly(s, dims.map((_, i) => pt(i, R * f)), {line: {color: '6E6456', width: 0.6}}));
  dims.forEach((_, i) => poly(s, [[cx, cy], pt(i, R)], {line: {color: '6E6456', width: 0.6}}, false));
  const dots = dims.map((d, i) => pt(i, R * (RADAR_LEVEL[d.status] || 46) / 132));
  poly(s, dots, {fill: {color: C.brassL, transparency: 80}, line: {color: 'DFB477', width: 1.5}});
  dots.forEach(([x, y]) => s.addShape(p.shapes.OVAL, {x: x - 0.045, y: y - 0.045, w: 0.09, h: 0.09, fill: {color: 'F1CD91'}, line: {type: 'none'}}));
  dims.forEach((d, i) => {
    const [x, y] = pt(i, R * 1.33);
    T(s, d.label, {x: x - 0.75, y: y - 0.24, w: 1.5, h: 0.26, fontSize: 12.5, color: 'F4E6D2', align: 'center'});
    T(s, RADAR_TEXT[d.status], {x: x - 0.75, y: y + 0.03, w: 1.5, h: 0.22, fontSize: 10, color: RADAR_TONE[d.status] || 'D4B38B', align: 'center'});
  });
}

const notes = [];
const made = [];

// ========== 01 封面 ==========
{
  const s = slide(true);
  T(s, '回响 48H 黑客松  ·  杭州银行「X-Ray 透视·真相」', {x: M, y: 0.6, w: 7, h: 0.3, fontSize: 12, color: C.brassL, charSpacing: 2});
  T(s, '企er', {x: M - 0.05, y: 1.75, w: 6, h: 1.6, fontFace: SERIF, fontSize: 100, bold: true, color: C.cream});
  T(s, '有出处的企业研究助手', {x: M, y: 3.45, w: 6.5, h: 0.7, fontFace: SERIF, fontSize: 32, bold: true, color: C.brassL});
  T(s, '把钱或信任交给一家公司之前，先把依据看清楚。', {x: M, y: 4.45, w: 6.5, h: 0.4, fontSize: 17, color: C.creamM});
  chip(s, '出处 · 每条结论都能点开原始记录', M, 5.2, {dark: true, pt: 11});
  T(s, 'qier.asia', {x: M, y: 6.6, w: 3, h: 0.4, fontSize: 15, bold: true, color: C.brassL});
  s.addImage({path: A('cover-goose.png'), x: 7.25, y: 1.0, w: 5.88, h: 6.5, altText: '小企拿放大镜的插画'});
  notes.push('大家好，我们做的是企 er，一个有出处的企业研究助手。把钱或信任交给一家公司之前，它帮普通人把依据看清楚。');
}

// ========== 02 场景钩子 ==========
{
  const s = slide(false, 2);
  kicker(s, '从一句话开始');
  T(s, '“我妈想在这家公司存 20 万理财，\n最怕急用时取不出来。”', {x: M, y: 1.3, w: 7.3, h: 1.6, fontFace: SERIF, fontSize: 30, bold: true, color: C.ink, lineSpacingMultiple: 1.15});
  T(s, '她手里只有一张宣传单。', {x: M, y: 2.85, w: 6.5, h: 0.4, fontSize: 18, color: C.muted});
  T(s, '她该信吗？', {x: M, y: 4.1, w: 6.5, h: 0.8, fontFace: SERIF, fontSize: 40, bold: true, color: C.brass});
  T(s, '赛题原话：家人要把储蓄交给一家公司，你凭什么判断它靠得住？', {x: M, y: 5.0, w: 6.6, h: 0.4, fontSize: 14, color: C.muted});
  // 宣传单
  const x = 8.35, y = 1.0, w = 4.23, h = 5.7;
  card(s, x, y, w, h, {fill: 'FFFFFF', shadow: true, r: 0.04});
  s.addShape(p.shapes.RECTANGLE, {x, y, w, h: 1.25, fill: {color: '7A2E22'}, line: {color: '7A2E22', width: 0}});
  T(s, '满盈禾 康养·财富', {x: x + 0.35, y: y + 0.25, w: w - 0.7, h: 0.45, fontFace: SERIF, fontSize: 20, bold: true, color: 'F8E7C2'});
  T(s, '颐养天年 财富无忧', {x: x + 0.35, y: y + 0.72, w: w - 0.7, h: 0.35, fontSize: 13, color: 'F1D9A8'});
  T(s, '保本保息', {x: x + 0.35, y: y + 1.5, w: w - 0.7, h: 0.5, fontFace: SERIF, fontSize: 24, bold: true, color: '7A2E22'});
  T(s, '年化 9%', {x: x + 0.35, y: y + 2.0, w: w - 0.7, h: 0.75, fontFace: SERIF, fontSize: 40, bold: true, color: 'B23A1E'});
  const lines = ['正规理财 · 安全稳健', '国资背景', '某大型银行 资金存管', '注册资本 5000 万 · 实力雄厚', '全国 30 家门店 · 10 万会员的信赖'];
  lines.forEach((t, i) => T(s, t, {x: x + 0.35, y: y + 2.95 + i * 0.4, w: w - 0.7, h: 0.36, fontSize: 13.5, color: '3B3027'}));
  T(s, '名额有限 · 先到先得', {x: x + 0.35, y: y + 5.05, w: w - 0.7, h: 0.36, fontSize: 13.5, bold: true, color: 'B23A1E'});
  chip(s, '宣传单（虚构）', x, y - 0.42, {pt: 10});
  foot(s, '演示案例：杭州满盈禾康养健康咨询有限公司为虚构公司，资料为预制快照；持牌名单、私募公示为真实公开数据。');
  notes.push('先看一个场景。一位用户输入：我妈想在这家公司存 20 万理财，最怕急用时取不出来。她手里只有一张宣传单：保本保息、年化 9%、国资背景、银行存管、30 家门店。赛题问的就是这件事：你凭什么判断它靠得住？说明一下，这家公司是我们虚构的演示案例，但后面用来对照的持牌名单、私募公示都是真实的公开数据。');
}

// ========== 03 问题 ==========
{
  const s = slide(false, 3);
  kicker(s, '为什么需要企er');
  title(s, '查得到，不等于看得懂');
  // 左：查询工具给你的
  T(s, '查询工具给你的', {x: M, y: 1.95, w: 5.2, h: 0.35, fontSize: 14, bold: true, color: C.muted});
  card(s, M, 2.4, 5.3, 3.7, {fill: 'EFE9DD', line: 'E2D9C8'});
  const rows = [['统一社会信用代码', '91330106MA2H******'], ['成立日期', '2025-02-18'], ['注册资本', '5000 万元'], ['经营范围', '健康管理咨询；养老服务；日用百货……'], ['股东', '张某明 70%，李某华 30%'], ['股权出质', '1 条'], ['行政处罚', '1 条'], ['参保人数', '4']];
  rows.forEach(([k, v], i) => {
    const y = 2.58 + i * 0.4;
    T(s, k, {x: M + 0.25, y, w: 1.8, h: 0.3, fontSize: 12, color: '9C9486'});
    T(s, v, {x: M + 2.05, y, w: 3.05, h: 0.3, fontSize: 12, color: '8A8273'});
  });
  T(s, '…… 还有几十项', {x: M + 0.25, y: 5.8, w: 4, h: 0.3, fontSize: 12, color: '9C9486'});
  // 右：她真正要问的
  const rx = 6.85;
  T(s, '她真正要问的', {x: rx, y: 1.95, w: 5.7, h: 0.35, fontSize: 14, bold: true, color: C.brass});
  const qs = ['它有资格收这笔钱吗？', '它说的，和记录对得上吗？', '急用时，钱拿得回来吗？'];
  qs.forEach((q, i) => {
    const y = 2.5 + i * 1.25;
    T(s, String(i + 1).padStart(2, '0'), {x: rx, y: y + 0.02, w: 0.8, h: 0.6, fontFace: SERIF, fontSize: 30, bold: true, color: C.brassL});
    T(s, q, {x: rx + 0.85, y: y + 0.08, w: 4.9, h: 0.6, fontFace: SERIF, fontSize: 25, bold: true, color: C.ink});
    if (i < 2) hline(s, rx, y + 1.0, 5.73, C.line);
  });
  T(s, [
    {text: '企er 不打分，', options: {bold: true, color: C.ink}},
    {text: '把每个说法和官方记录逐条对照，给出能点开出处的判断。', options: {color: C.ink}},
  ], {x: M, y: 6.45, w: CW, h: 0.4, fontSize: 16});
  notes.push('现在查一家公司不难，企查查、公示系统都能查到一大串字段。但普通人真正要问的只有三件事：它有资格收这笔钱吗？它说的和记录对得上吗？急用时钱拿得回来吗？从一串字段走到这三个答案，中间的核对工作没人替她做。企 er 不打分，而是把每个说法和官方记录逐条对照，给出能点开出处的判断。');
}

// ========== 04 入口 ==========
{
  const s = slide(true, 4);
  kicker(s, '产品入口', true);
  title(s, '输入公司全称，再说一句你要做什么', true);
  const iw = 7.7, ih = iw * 687 / 1663;
  s.addImage({path: A('crops/home.jpg'), x: M, y: 1.95, w: iw, h: ih, altText: '企er 首页：公司名称与研究需求输入', shadow: shadow()});
  const rx = M + iw + 0.5, rw = W - M - rx;
  const steps = [
    ['读懂需求', '识别为：存钱理财、20 万、替妈妈看\n需求决定先查什么'],
    ['汇集记录', '持牌名单、私募公示、工商年报、司法舆情、用户材料，收进一个案卷'],
    ['交出报告', '按需求排好重点，每条结论都带出处'],
  ];
  steps.forEach(([h, d], i) => {
    const y = 1.95 + i * 1.1;
    T(s, String(i + 1).padStart(2, '0'), {x: rx, y, w: 0.6, h: 0.4, fontFace: SERIF, fontSize: 18, bold: true, color: C.brassL});
    T(s, h, {x: rx + 0.55, y, w: rw - 0.55, h: 0.4, fontSize: 17, bold: true, color: C.cream});
    T(s, d, {x: rx + 0.55, y: y + 0.42, w: rw - 0.55, h: 0.7, fontSize: 12, color: C.creamM, lineSpacingMultiple: 1.1});
  });
  hline(s, M, 5.55, CW, C.navyLine);
  T(s, '已接入', {x: M, y: 5.83, w: 1, h: 0.3, fontSize: 12, bold: true, color: C.brassL});
  let cx = M + 0.85;
  ['金融监管持牌名单', '中基协私募公示', '企查查智能体数据', '巨潮资讯公告', '监管与政府网站', '用户上传的材料'].forEach((t) => { cx += chip(s, t, cx, 5.8, {dark: true, pt: 11}) + 0.15; });
  notes.push('入口很简单：输入公司全称，再说一句你要做什么。小企先读懂需求，比如这里识别为存钱理财、20 万、替妈妈看；然后把持牌名单、私募公示、工商年报、司法和舆情，还有用户自己的材料，汇到同一个案卷里。');
}

// ========== 05 报告第一眼：五维轮廓 ==========
{
  const s = slide(false, 5);
  kicker(s, '报告第一眼');
  title(s, '先看个大概：企业五维轮廓');
  const L = ['经营资格', '基本面', '资金面', '风险稳定性', '消息面'];
  const cases = [
    {name: '杭州满盈禾康养健康咨询有限公司', tag: '虚构 · 存 20 万理财', st: ['bad', 'bad', 'bad', 'bad', 'bad'],
     note: '五维都有异常记录：没有资格、实缴 0 元、\n70% 股权出质、虚假广告被罚、投诉集中在到期不兑付'},
    {name: '杭州银行股份有限公司', tag: '真实 · 求职入职', st: ['ok', 'ok', 'ok', 'bad', 'warn'],
     note: '资格、基本面、资金面未见异常；\n行政处罚让风险稳定性往里收，消息面待关注'},
  ];
  const cw = 5.75, ch = 4.3, y = 1.8;
  cases.forEach((c, i) => {
    const x = i ? W - M - cw : M;
    card(s, x, y, cw, ch, {fill: C.navy, line: C.navy, r: 0.1});
    T(s, c.name, {x: x + 0.3, y: y + 0.25, w: cw - 2.3, h: 0.35, fontFace: SERIF, fontSize: 15, bold: true, color: C.cream});
    chip(s, c.tag, x + cw - 0.3, y + 0.26, {right: true, dark: true, pt: 10, h: 0.28});
    radar(s, x + cw / 2, y + 2.42, 1.15, L.map((label, k) => ({label, status: c.st[k]})));
    T(s, c.note, {x: i ? W - M - cw : M, y: y + ch + 0.12, w: cw, h: 0.55, fontSize: 12, color: C.muted, lineSpacingMultiple: 1.1});
  });
  foot(s, '定性示意，不设评分：每一维取查过的记录里最需关注的一项，越往里越需要留意；位置不表示问题数量。');
  notes.push('报告打开，第一眼是企业五维轮廓：经营资格、基本面、资金面、风险稳定性、消息面。它不打分，每一维只取查过的记录里最需要留意的一项，越往里越要当心。左边是虚构的满盈禾，五维都有异常记录，整个缩成一圈；右边是真实的杭州银行，资格、基本面、资金面都未见异常，只有行政处罚和负面新闻让两维往里收。两家公司差在哪，一眼就能看个大概。');
}

// ========== 05 第一问：资格 ==========
{
  const s = slide(false, 6);
  kicker(s, '第一问');
  title(s, '它有资格收这笔钱吗？');
  badge(s, 'bad', M, 2.15, 0.82);
  T(s, '有问题', {x: M + 1.05, y: 1.95, w: 3.6, h: 1.1, fontFace: SERIF, fontSize: 58, bold: true, color: C.red});
  T(s, '4 份持牌名单、\n18,396 家私募管理人，\n都查不到它。', {x: M, y: 3.3, w: 4.6, h: 1.35, fontSize: 19, bold: true, color: C.ink, lineSpacingMultiple: 1.15});
  T(s, '先回答和这笔钱最相关的问题，依据就在旁边。', {x: M, y: 4.85, w: 4.55, h: 0.7, fontSize: 14, color: C.muted});
  const rx = 5.85, rw = W - M - rx;
  const rows = [
    ['bad', '持牌机构名单', '银行业 4,070 · 保险 238 · 期货 150 · 支付 156 家，都没有它', '出处 · 金融监管总局等 4 份名单'],
    ['bad', '私募基金管理人登记', '截至 2026-10-02 登记的 18,396 家里，没有它', '出处 · 中基协公示'],
    ['bad', '经营范围', '健康管理咨询、养老服务、日用百货……不含任何金融业务', '出处 · 企业登记信息'],
    ['miss', '理财产品登记编码', '宣传单上没有', '出处 · 用户材料'],
  ];
  rows.forEach(([k, l, v, src], i) => {
    const y = 1.95 + i * 1.15;
    card(s, rx, y, rw, 0.98);
    badge(s, k, rx + 0.22, y + 0.17, 0.32);
    T(s, l, {x: rx + 0.7, y: y + 0.15, w: 3.4, h: 0.35, fontSize: 15, bold: true});
    chip(s, src, rx + rw - 0.2, y + 0.16, {right: true, pt: 10, h: 0.28});
    T(s, v, {x: rx + 0.7, y: y + 0.55, w: rw - 0.9, h: 0.34, fontSize: 13, color: C.ink});
  });
  foot(s, '演示案例 · 公司为虚构。“没查”“查了没有”“查询失败”在报告里分开写，不会把没查到当成正常。');
  notes.push('报告打开，先回答第一问：它有资格收这笔钱吗？答案是有问题。我们查了银行、保险、期货、支付 4 份持牌名单，还有中基协 18,396 家私募管理人，都没有它；它的经营范围里也没有任何金融业务。每一条右边都标着出处，点开就是原始记录。');
}

// ========== 06 逐条对照 ==========
{
  const s = slide(true, 7);
  kicker(s, '逐条对照', true);
  title(s, '它说的，和记录里的', true);
  const cx1 = M, cx2 = 5.0, cx3 = 10.35;
  T(s, '宣传单上说', {x: cx1, y: 1.85, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  T(s, '记录里查到', {x: cx2, y: 1.85, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  T(s, '规则判定', {x: cx3, y: 1.85, w: 2.2, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  const rows = [
    ['保本保息 · 年化 9%', '8.2 倍', '一年期定存利率的倍数\n资管新规：不得承诺保本', '不合规承诺', C.red],
    ['国资背景', '0%', '国有持股\n2 个股东都是自然人', '与记录不符', C.red],
    ['注册资本 5000 万 · 实力雄厚', '¥0', '实缴资本\n认缴 5000 万，期限 2030 年', '说法有误导', C.amber],
    ['全国 30 家门店', '0 家', '登记的分支机构\n年报里参保 4 人', '说法有误导', C.amber],
  ];
  rows.forEach(([said, big, sub, verdict, col], i) => {
    const y = 2.3 + i * 1.08;
    hline(s, M, y - 0.08, CW, C.navyLine);
    T(s, said, {x: cx1, y: y + 0.18, w: 4.0, h: 0.5, fontFace: SERIF, fontSize: 20, bold: true, color: C.cream});
    T(s, big, {x: cx2, y: y + 0.05, w: 1.75, h: 0.75, fontFace: SERIF, fontSize: 34, bold: true, color: C.brassL});
    T(s, sub, {x: cx2 + 1.85, y: y + 0.13, w: 3.4, h: 0.7, fontSize: 12.5, color: C.creamM, lineSpacingMultiple: 1.1});
    pill(s, verdict, cx3, y + 0.2, col, {w: 1.75, pt: 13});
  });
  hline(s, M, 2.3 + 4 * 1.08 - 0.08, CW, C.navyLine);
  foot(s, '判定由固定规则给出，每条附法规或记录出处；口径不同会注明，比如门店不等于登记的分支机构。', true);
  notes.push('接着把宣传单上的每个说法拿来对照。保本保息、年化 9%：资管新规不允许承诺保本，9% 是一年期定存的 8.2 倍。国资背景：两个股东都是自然人。注册资本 5000 万：实际交了 0 元。30 家门店：登记的分支机构 0 家，年报里只有 4 个人参保。这些判定由固定规则给出，不是 AI 拍脑袋。');
}

// ========== 07 追问与出处 ==========
{
  const s = slide(false, 8);
  kicker(s, '追问与出处');
  title(s, '看不懂就问，每句回答都能点开原文');
  const steps = [
    ['选中报告里的一条，问小企', '回答只依据这份案卷查到的记录'],
    ['关键事实带出处', '来源、采集时间、数据截至日一起保留'],
    ['程序校验每条引用', '找不到依据的表述会被删掉，并注明“已省略”'],
  ];
  steps.forEach(([h, d], i) => {
    const y = 2.05 + i * 1.35;
    T(s, String(i + 1).padStart(2, '0'), {x: M, y, w: 0.9, h: 0.6, fontFace: SERIF, fontSize: 30, bold: true, color: C.brassL});
    T(s, h, {x: M + 0.95, y: y + 0.04, w: 5.6, h: 0.45, fontSize: 20, bold: true});
    T(s, d, {x: M + 0.95, y: y + 0.55, w: 5.6, h: 0.4, fontSize: 14, color: C.muted});
  });
  const ih = 4.45, iw = ih * 740 / 872, ix = W - M - iw;
  s.addImage({path: A('crops/sources-live.jpg'), x: ix, y: 1.85, w: iw, h: ih, altText: '杭州银行案卷的原文出处弹窗', shadow: shadow()});
  chip(s, '实拍 · 杭州银行（真实公司）· 联网查询 · 已接模型', W - M, 6.45, {right: true, pt: 10});
  notes.push('报告看不懂，可以选中一条直接问小企。回答只依据这份案卷，关键事实都带出处。右边是真实公司杭州银行、联网查询、接了模型时的出处弹窗：来源、采集时间、数据截至日都在。程序还会校验每条引用，找不到依据的表述直接删掉并注明已省略。');
}

// ========== 08 版本 ==========
{
  const s = slide(false, 9);
  kicker(s, '持续研究');
  title(s, '有了新材料，判断跟着更新');
  const cw = 3.72, gap = (CW - 3 * cw) / 2, y0 = 1.95, ch = 4.25;
  const cols = [
    {v: 'v1', tag: '首次分析', input: '宣传单', quote: '保本保息 · 年化 9%\n国资背景 · 银行存管\n注册资本 5000 万 · 30 家门店', out: [['bad', '3 条不符或不合规'], ['warn', '2 条有误导'], ['miss', '1 条无法核验']]},
    {v: 'v2', tag: '对方回复', input: '业务员的微信', quote: '“钱转到我们财务的个人账户就行”\n“到期前急用也没事，\n随时可以取出来。”', out: [['bad', '新疑点：收款人是个人'], ['miss', '新增：“随时可取”无法核验']]},
    {v: 'v3', tag: '补充材料', input: '认购协议节选', quote: '“第五条 认购期限为 12 个月，\n期间为封闭期，不得提前赎回。”', out: [['bad', '“随时可取” → 与记录不符'], ['bad', '提前退出扣本金 20%']]},
  ];
  cols.forEach((c, i) => {
    const x = M + i * (cw + gap);
    card(s, x, y0, cw, ch, {shadow: i === 2});
    T(s, c.v, {x: x + 0.3, y: y0 + 0.2, w: 1, h: 0.65, fontFace: SERIF, fontSize: 34, bold: true, color: C.brass});
    T(s, c.tag, {x: x + 1.2, y: y0 + 0.36, w: cw - 1.4, h: 0.35, fontSize: 15, bold: true});
    T(s, '新材料：' + c.input, {x: x + 0.3, y: y0 + 1.0, w: cw - 0.6, h: 0.3, fontSize: 11.5, color: C.muted});
    s.addShape(p.shapes.RECTANGLE, {x: x + 0.3, y: y0 + 1.35, w: cw - 0.6, h: 1.25, fill: {color: C.paper2}, line: {color: C.paper2, width: 0}});
    T(s, c.quote, {x: x + 0.45, y: y0 + 1.45, w: cw - 0.9, h: 1.05, fontSize: 12, color: '4A4237', lineSpacingMultiple: 1.15, valign: 'middle'});
    c.out.forEach(([k, t], j) => {
      const yy = y0 + 2.85 + j * 0.42;
      badge(s, k, x + 0.3, yy + 0.04, 0.26);
      T(s, t, {x: x + 0.68, y: yy, w: cw - 0.95, h: 0.4, fontSize: 12.5, bold: j === 0 && i > 0, color: C.ink});
    });
    if (i < 2) T(s, '→', {x: x + cw - 0.02, y: y0 + 0.3, w: gap + 0.04, h: 0.45, fontSize: 18, color: C.brass, align: 'center'});
  });
  T(s, [
    {text: '误传一张小区停水通知？', options: {bold: true}},
    {text: '  v4 判断不变：35 项都和上一版一样。旧版本和旧回答的出处都保留，随时回看。'},
  ], {x: M, y: 6.45, w: CW, h: 0.35, fontSize: 13.5, color: C.muted});
  notes.push('判断不是一次就结束的。对方业务员回微信说：钱转到财务的个人账户，急用随时可以取。补进来，v2 马上标出新疑点：收款人是个人。再补一份认购协议，写着 12 个月封闭期、不得提前赎回，v3 就把“随时可取”从无法核验改成与记录不符。如果误传了一张停水通知，判断不会乱动。每个版本和旧回答的出处都保留。');
}

// ========== 09 方法 ==========
{
  const s = slide(true, 10);
  kicker(s, '方法', true);
  title(s, '结论来自记录和规则，AI 只负责读材料、说人话', true, {fontSize: 30});
  const steps = [
    ['汇集', '公开记录 + 用户材料', '持牌名单、私募公示、工商年报、司法舆情；宣传单、合同、聊天截图'],
    ['规则核验', '对照 · 判定 · 比版本', '固定规则，每条写明法规出处；同样的输入，同样的结论'],
    ['AI 解读', '识需求 · 读材料 · 答追问', '识别场景，读图片和合同，把结果翻译成人话'],
    ['引用校验', '每句回到原文', '引用不到原文的表述，删掉并注明'],
  ];
  const bw = 2.6, gap = (CW - 4 * bw) / 3, y = 2.1, bh = 3.05;
  steps.forEach(([k, h, d], i) => {
    const x = M + i * (bw + gap);
    const key = i === 1;
    card(s, x, y, bw, bh, {fill: C.navy2, line: key ? C.brassL : C.navyLine, lw: key ? 1.5 : 0.75});
    T(s, String(i + 1).padStart(2, '0') + '  ' + k, {x: x + 0.25, y: y + 0.25, w: bw - 0.5, h: 0.35, fontSize: 13, bold: true, color: C.brassL});
    T(s, h, {x: x + 0.25, y: y + 0.75, w: bw - 0.5, h: 0.8, fontFace: SERIF, fontSize: 19, bold: true, color: C.cream, lineSpacingMultiple: 1.1});
    T(s, d, {x: x + 0.25, y: y + 1.65, w: bw - 0.5, h: 1.1, fontSize: 12, color: C.creamM, lineSpacingMultiple: 1.15});
    if (i < 3) s.addShape(p.shapes.LINE, {x: x + bw + 0.08, y: y + bh / 2, w: gap - 0.16, h: 0, line: {color: C.brassL, width: 1.25, endArrowType: 'triangle'}});
  });
  T(s, '底线', {x: M, y: 5.78, w: 1, h: 0.35, fontSize: 13, bold: true, color: C.brassL});
  let cx = M + 0.75;
  ['不打安全分', '没查到不等于没问题', '“查了没有”“没查”“查询失败”分开写', '不替用户做决定'].forEach((t) => { cx += chip(s, t, cx, 5.75, {dark: true, pt: 12, h: 0.36}) + 0.18; });
  notes.push('方法上我们做了一个关键切分：结论来自记录和规则，AI 只负责读材料、说人话。规则对照记录、给出判定、比较版本，同样的输入永远是同样的结论；AI 负责识别需求、读图片和合同、回答追问；最后程序再校验每条引用。我们也守几条底线：不打安全分，没查到不等于没问题，不替用户做决定。');
}

// ========== 10 价值 / 落地 ==========
{
  const s = slide(false, 11);
  kicker(s, '落到柜台');
  title(s, '一页结论，带进下一次沟通');
  // 提示单
  const x = M, y = 1.9, w = 5.55, h = 4.9;
  card(s, x, y, w, h, {fill: 'FFFFFF', shadow: true, r: 0.04});
  T(s, '网点提示单', {x: x + 0.35, y: y + 0.28, w: 3, h: 0.45, fontFace: SERIF, fontSize: 20, bold: true});
  chip(s, '产品生成 · 柜员版', x + w - 0.3, y + 0.32, {right: true, pt: 9.5, h: 0.26});
  T(s, '客户拟交给 杭州满盈禾康养健康咨询有限公司：储蓄 20 万', {x: x + 0.35, y: y + 0.8, w: w - 0.7, h: 0.3, fontSize: 11, color: C.muted});
  hline(s, x + 0.35, y + 1.18, w - 0.7, C.line);
  T(s, '它的说法里有 4 处和记录对不上、2 处要留意；\n记录里有 4 项不良情况；还有 2 项没查到。\n建议客户先核实下面三件事，再办理。', {x: x + 0.35, y: y + 1.32, w: w - 0.7, h: 0.85, fontSize: 12.5, bold: true, lineSpacingMultiple: 1.15});
  const qs = ['急用时多久能取回，提前取有没有违约金，写进合同了吗', '请给出金融许可证编号，或者理财产品登记编码', '收益从哪里来？钱投到了什么资产？写进合同了吗'];
  qs.forEach((q, i) => {
    const yy = y + 2.4 + i * 0.6;
    T(s, String(i + 1), {x: x + 0.35, y: yy, w: 0.3, h: 0.3, fontFace: SERIF, fontSize: 15, bold: true, color: C.brass});
    T(s, q, {x: x + 0.7, y: yy, w: w - 1.05, h: 0.5, fontSize: 12.5});
  });
  T(s, '供柜面参考：依据为公开记录和客户提供的材料，不构成对该公司的法律定性。', {x: x + 0.35, y: y + h - 0.55, w: w - 0.7, h: 0.35, fontSize: 9.5, color: C.muted});
  // 场景
  const rx = 6.95, rw = W - M - rx;
  const sc = [
    ['网点', '老人大额取现说要“去投资”：柜员查一下，拿着提示单劝阻，有依据，不只靠嘴说。'],
    ['手机银行', '向陌生的对公账户大额转账前，先“透视一下收款方”。'],
    ['家人', '家人版一页结论：一起看依据，明确还缺什么材料。'],
  ];
  sc.forEach(([h, d], i) => {
    const yy = 1.95 + i * 1.18;
    T(s, h, {x: rx, y: yy, w: 1.5, h: 0.4, fontFace: SERIF, fontSize: 19, bold: true, color: C.brass});
    T(s, d, {x: rx + 1.45, y: yy + 0.04, w: rw - 1.45, h: 0.85, fontSize: 14.5, lineSpacingMultiple: 1.15});
    hline(s, rx, yy + 0.98, rw, C.line);
  });
  T(s, '防范非法集资、提示资金风险，\n本就是银行的日常工作。', {x: rx, y: 5.4, w: rw, h: 0.9, fontFace: SERIF, fontSize: 18, bold: true, color: C.ink, lineSpacingMultiple: 1.15});
  T(s, '以上为落地设想，待与杭州银行业务方共同验证。', {x: rx, y: 6.42, w: rw, h: 0.3, fontSize: 11.5, color: C.muted});
  notes.push('研究的结果最后要能拿去用。产品能生成两种一页结论：家人版，一起看依据、明确还缺什么；柜员版的网点提示单，列出对不上的地方和建议客户先核实的三件事。我们设想的落地场景是：老人大额取现说要去投资，柜员查一下，拿着提示单劝阻，有依据，不只靠嘴说。防范非法集资本来就是银行的日常工作，这些还需要和杭州银行一起验证。');
}

// ========== 11 收尾 ==========
{
  const s = slide(true, 12);
  T(s, '把钱或信任交出去之前，\n先把依据看清楚。', {x: M, y: 1.7, w: 7.2, h: 2.2, fontFace: SERIF, fontSize: 42, bold: true, color: C.cream, lineSpacingMultiple: 1.2});
  T(s, '企er · 有出处的企业研究助手', {x: M, y: 4.25, w: 7, h: 0.45, fontSize: 18, color: C.brassL, bold: true});
  T(s, 'qier.asia', {x: M, y: 5.25, w: 5, h: 0.75, fontFace: SERIF, fontSize: 36, bold: true, color: C.brassL});
  T(s, '现场可试：输入任意公司全称，再加一句需求。', {x: M, y: 6.05, w: 6.5, h: 0.35, fontSize: 14, color: C.creamM});
  s.addImage({path: A('closing-office.png'), x: 7.75, y: 0.9, w: 4.83, h: 5.74, altText: '小企在办公室阅读报告的插画'});
  notes.push('企 er 把一次查询，变成一份能追问、能补充、能回看的研究案卷。把钱或信任交出去之前，先把依据看清楚。网址是 qier.asia，现场就可以输入任意公司试一试。谢谢大家。');
}

// ========== 12 备用：真实公司 ==========
{
  const s = slide(false, 13);
  kicker(s, '答辩备用 · 真实公司');
  title(s, '真实公司同样可用：杭州银行 · 求职场景');
  const ih = 4.85, iw = ih * 1312 / 876;
  s.addImage({path: A('crops/live-report.jpg'), x: M, y: 1.9, w: iw, h: ih, altText: '杭州银行求职场景的真实报告', shadow: shadow()});
  const rx = M + iw + 0.45, rw = W - M - rx;
  [['60', '条来源记录'], ['5', '条行政处罚'], ['7,458', '年报参保人数']].forEach(([n, l], i) => {
    const y = 1.9 + i * 1.3;
    T(s, n, {x: rx, y, w: rw, h: 0.7, fontFace: SERIF, fontSize: 36, bold: true, color: C.brass});
    T(s, l, {x: rx, y: y + 0.7, w: rw, h: 0.35, fontSize: 13, color: C.muted});
  });
  chip(s, '实拍 · 联网查询 · 已接模型', rx, 5.85, {pt: 10});
  notes.push('答辩备用。真实公司实时联网也能跑：杭州银行，求职场景，60 条来源记录，接了模型。报告按求职需求排重点，比如签约主体、用工信息，同时列出还没覆盖的资料。');
}

// ========== 13 备用：查询状态与边界 ==========
{
  const s = slide(false, 14);
  kicker(s, '答辩备用 · 资料覆盖');
  title(s, '查询状态分开写，没查到不当成正常');
  const rows = [
    [C.green, '查到了', '这个来源里有匹配记录'],
    [C.grey, '查了没有', '本次查询范围内没有匹配记录'],
    [C.amber, '没查', '数据源没覆盖，或本次没执行'],
    [C.red, '查询失败', '请求没有成功，会提示重试'],
  ];
  rows.forEach(([col, k, v], i) => {
    const y = 1.95 + i * 0.95;
    card(s, M, y, 7.3, 0.78);
    pill(s, k, M + 0.25, y + 0.19, col, {w: 1.5, pt: 13});
    T(s, v, {x: M + 2.05, y: y + 0.2, w: 5, h: 0.4, fontSize: 15});
  });
  const rx = 8.7, rw = W - M - rx;
  T(s, '边界', {x: rx, y: 1.95, w: rw, h: 0.4, fontFace: SERIF, fontSize: 20, bold: true, color: C.brass});
  ['不打安全分，不作法律定性', '每条资料写明采集时间和数据截至日', '公开记录有覆盖与时间边界', '最终决定由人作出'].forEach((t, i) => {
    T(s, t, {x: rx, y: 2.55 + i * 0.7, w: rw, h: 0.6, fontSize: 15, lineSpacingMultiple: 1.1});
    hline(s, rx, 2.55 + i * 0.7 + 0.55, rw, C.line);
  });
  notes.push('答辩备用。每个来源的状态分四种：查到了、查了没有、没查、查询失败，分开展示，避免把没获取到记录误读成正常。产品不打安全分，不作法律定性，最终决定由人作出。');
}

// ---------- write ----------
made.forEach((sl, i) => { if (notes[i]) sl.addNotes(notes[i]); });
await p.writeFile({fileName: OUT});
console.log('WROTE', OUT);

// ---------- render previews ----------
const {PresentationFile, FileBlob} = await import('file:///' + NM + '@oai/artifact-tool/dist/artifact_tool.mjs');
await fs.mkdir(RENDER, {recursive: true});
const deck = await PresentationFile.importPptx(await FileBlob.load(OUT));
for (let i = 0; i < deck.slides.items.length; i++) {
  const png = await deck.export({slide: deck.slides.items[i], format: 'png', scale: 1});
  await fs.writeFile(path.join(RENDER, `slide-${String(i + 1).padStart(2, '0')}.png`), new Uint8Array(await png.arrayBuffer()));
}
await fs.writeFile(path.join(RENDER, 'montage.webp'), new Uint8Array(await (await deck.export({format: 'webp', montage: true, scale: 0.5})).arrayBuffer()));
const chars = notes.slice(0, 12).join('').replace(/[\s\p{P}\p{S}]/gu, '').length;
console.log('RENDERED', deck.slides.items.length, 'slides; main-script chars', chars);

// ---------- speaker script ----------
const titles = ['封面', '从一句话开始', '查得到，不等于看得懂', '产品入口', '报告第一眼：五维轮廓', '第一问：它有资格收这笔钱吗', '它说的，和记录里的', '追问与出处', '有了新材料，判断跟着更新', '方法：规则与 AI 的分工', '一页结论，带到柜台', '收尾', '答辩备用：真实公司', '答辩备用：查询状态与边界'];
const secs = [12, 30, 25, 20, 24, 25, 28, 22, 30, 26, 30, 14];
const md = ['# 企er 路演 v07 · 逐页讲稿', '',
  `主讲第 1–12 页，按 ${secs.reduce((a, b) => a + b, 0)} 秒分配（约 ${chars} 字，不含标点），留出翻页和停顿；第 13–14 页答辩备用。讲稿也写进了每页的演讲者备注。尚未真人排练计时。`, '',
  ...notes.flatMap((n, i) => [`## ${i + 1}. ${titles[i]}${secs[i] ? `（${secs[i]} 秒）` : ''}`, '', n, ''])];
await fs.writeFile(path.join(here, '逐页讲稿-v07.md'), md.join('\n'));
