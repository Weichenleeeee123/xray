// 企er 路演 v08：主线换成杭州银行求职（预制示例 B）。运行：
//   "<codex runtime>/node/bin/node.exe" output/pitch-refined/build-v08.mjs
// 产出 output/pitch-refined/企er-路演-v08.pptx，预览图写到 .tmp/pitch-v07/render-v08/。
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
const OUT = path.join(here, '企er-路演-v08.pptx');
const RENDER = path.join(root, '.tmp/pitch-v07/render-v08');

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

// ========== 02 场景钩子：杭州银行 offer ==========
{
  const s = slide(false, 2);
  kicker(s, '从一句话开始');
  T(s, '“我收到杭州银行的 offer，\n想知道这家单位靠不靠谱。”', {x: M, y: 1.3, w: 7.3, h: 1.6, fontFace: SERIF, fontSize: 30, bold: true, color: C.ink, lineSpacingMultiple: 1.15});
  T(s, '手里只有招聘公告里的一段银行介绍。', {x: M, y: 2.85, w: 6.8, h: 0.4, fontSize: 18, color: C.muted});
  T(s, '该信多少？', {x: M, y: 4.0, w: 6.5, h: 0.8, fontFace: SERIF, fontSize: 40, bold: true, color: C.brass});
  T(s, '赛题问：把储蓄、信任交给一家公司之前，凭什么判断它靠得住？\n求职，交出去的是信任和几年时间。', {x: M, y: 4.9, w: 6.9, h: 0.75, fontSize: 14, color: C.muted, lineSpacingMultiple: 1.2});
  // 招聘公告摘录（用户材料原文）
  const x = 8.15, y = 1.0, w = 4.43, h = 5.45;
  card(s, x, y, w, h, {fill: 'FFFFFF', shadow: true, r: 0.04});
  s.addShape(p.shapes.RECTANGLE, {x, y, w, h: 1.05, fill: {color: C.navy}, line: {color: C.navy, width: 0}});
  T(s, '杭州银行 2022 校园招聘公告', {x: x + 0.35, y: y + 0.22, w: w - 0.7, h: 0.4, fontFace: SERIF, fontSize: 17, bold: true, color: C.cream});
  T(s, '里的银行介绍（摘录）', {x: x + 0.35, y: y + 0.6, w: w - 0.7, h: 0.3, fontSize: 12, color: C.brassL});
  const lines = [
    ['成立于 1996 年 9 月，总部位于杭州', false],
    ['全行拥有 200 余家分支机构', true],
    ['2016 年 10 月 27 日在上交所上市，\n股票代码 600926', true],
    ['截至 2020 年末，总资产 11,692.57 亿元', false],
    ['归属于上市公司股东净利润 71.36 亿元', false],
    ['《银行家》全球银行 1000 强，\n按一级资本排名第 144 位', false],
  ];
  let yy = y + 1.35;
  lines.forEach(([t, hi]) => {
    const n = t.split('\n').length;
    if (hi) s.addShape(p.shapes.RECTANGLE, {x: x + 0.22, y: yy - 0.05, w: 0.05, h: 0.32 * n + 0.04, fill: {color: C.brass}, line: {type: 'none'}});
    T(s, t, {x: x + 0.38, y: yy, w: w - 0.7, h: 0.32 * n, fontSize: 13, color: hi ? C.ink : '5B5348', bold: hi, lineSpacingMultiple: 1.05});
    yy += 0.32 * n + 0.3;
  });
  chip(s, '用户提供的材料 · 2026-10-02 摘录', x, y + h + 0.12, {pt: 10});
  foot(s, '演示用预制示例：真实公司，资料是 2026-10-03 04:55 预先联网查询的快照，现场不重新联网。');
  notes.push('一位应届生输入：我收到杭州银行的 offer，想知道这家单位靠不靠谱。她手里只有招聘公告里的一段介绍。赛题问，把信任交给一家公司之前凭什么判断它靠得住；求职，交出去的就是信任和几年时间。今天用的是预先联网跑好的杭州银行案卷。');
}

// ========== 03 问题：大公司的记录太多 ==========
{
  const s = slide(false, 3);
  kicker(s, '为什么需要企er');
  title(s, '查得到，不等于看得懂');
  T(s, '查询工具给你的：一家大银行的记录', {x: M, y: 1.95, w: 5.4, h: 0.35, fontSize: 14, bold: true, color: C.muted});
  card(s, M, 2.4, 5.3, 3.7, {fill: 'EFE9DD', line: 'E2D9C8'});
  const rows = [['新闻舆情', '3,425 条'], ['裁判文书', '1,507 条'], ['立案信息', '1,164 条'], ['开庭公告', '1,000 条'], ['行政许可', '110 条'], ['工商变更', '46 次'], ['股权出质', '39 条'], ['行政处罚', '5 条']];
  rows.forEach(([k, v], i) => {
    const y = 2.58 + i * 0.4;
    T(s, k, {x: M + 0.25, y, w: 2.2, h: 0.3, fontSize: 12.5, color: '8F887B'});
    T(s, v, {x: M + 2.6, y, w: 2.4, h: 0.3, fontSize: 12.5, color: '7D7668', align: 'right'});
  });
  T(s, '…… 哪些跟“去不去”有关？', {x: M + 0.25, y: 5.8, w: 4.8, h: 0.3, fontSize: 12.5, color: '8F887B'});
  const rx = 6.85;
  T(s, '她真正要问的', {x: rx, y: 1.95, w: 5.7, h: 0.35, fontSize: 14, bold: true, color: C.brass});
  const qs = ['它是不是正规单位？', '发 offer、签合同、交社保的，\n是不是同一家？', '那些处罚和官司，跟我有关吗？'];
  qs.forEach((q, i) => {
    const y = 2.45 + i * 1.25;
    T(s, String(i + 1).padStart(2, '0'), {x: rx, y: y + 0.02, w: 0.8, h: 0.6, fontFace: SERIF, fontSize: 30, bold: true, color: C.brassL});
    T(s, q, {x: rx + 0.85, y: y + 0.06, w: 4.9, h: 0.9, fontFace: SERIF, fontSize: 22, bold: true, color: C.ink, lineSpacingMultiple: 1.1});
    if (i < 2) hline(s, rx, y + 1.08, 5.73, C.line);
  });
  T(s, [
    {text: '企er 按需求排重点：', options: {bold: true}},
    {text: '求职先看用工；处罚和官司照实列出，每条都能点开出处。'},
  ], {x: M, y: 6.4, w: CW, h: 0.4, fontSize: 16});
  notes.push('查杭州银行，工具能给你几千条记录：新闻 3425 条、裁判文书 1507 条、行政处罚 5 条。公司越大，记录越多。但求职者要问的只有三件事：它正不正规？发 offer、签合同、交社保的是不是同一家？那些处罚和官司跟我有没有关系？');
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
    ['读懂需求', '识别为：求职入职，替自己看\n需求决定先查什么、先答什么'],
    ['汇集记录', '持牌名单、工商与年报、财报、\n政府网站、新闻投诉：61 条记录'],
    ['对照规则', '对照 2 条说法、35 项检查，\n写成 8 条看得懂的短句'],
  ];
  steps.forEach(([h, d], i) => {
    const y = 1.95 + i * 1.1;
    T(s, String(i + 1).padStart(2, '0'), {x: rx, y, w: 0.6, h: 0.4, fontFace: SERIF, fontSize: 18, bold: true, color: C.brassL});
    T(s, h, {x: rx + 0.55, y, w: rw - 0.55, h: 0.4, fontSize: 17, bold: true, color: C.cream});
    T(s, d, {x: rx + 0.55, y: y + 0.42, w: rw - 0.55, h: 0.6, fontSize: 12, color: C.creamM, lineSpacingMultiple: 1.1});
  });
  hline(s, M, 5.55, CW, C.navyLine);
  T(s, '已接入', {x: M, y: 5.83, w: 1, h: 0.3, fontSize: 12, bold: true, color: C.brassL});
  let cx = M + 0.85;
  ['金融监管持牌名单', '中基协私募公示', '企查查智能体数据', '巨潮资讯公告', '监管与政府网站', '用户上传的材料'].forEach((t) => { cx += chip(s, t, cx, 5.8, {dark: true, pt: 11}) + 0.15; });
  notes.push('入口很简单：公司全称加一句需求。小企识别为求职入职，把持牌名单、工商年报、财报、政府网站和新闻投诉汇成一个案卷，一共 61 条记录，再用规则做 35 项检查。');
}

// ========== 05 报告第一眼：五维轮廓 + 初步结论（实拍） ==========
{
  const s = slide(false, 5);
  kicker(s, '报告第一眼');
  title(s, '先看个大概：五维轮廓和初步结论');
  const iw = CW, ih = iw * 878 / 2712;
  s.addImage({path: A('crops/B-overview.jpg'), x: M, y: 1.75, w: iw, h: ih, altText: '杭州银行报告的企业五维轮廓与初步结论', shadow: shadow()});
  const axes = [
    ['经营资格', 'ok', '持牌城商行\n行政许可 110 条'],
    ['基本面', 'ok', '存续 30 年\n年报参保 7,458 人'],
    ['资金面', 'ok', '2025 营收 387.99 亿\n净利润 190.29 亿'],
    ['风险稳定性', 'bad', '行政处罚 5 条\n政府网站点名 1 份'],
    ['消息面', 'warn', '近一年负面新闻 2 条\n网上投诉 1 条'],
  ];
  const colW = CW / 5, y0 = 1.75 + ih + 0.25;
  axes.forEach(([l, st, d], i) => {
    const x = M + i * colW;
    badge(s, st, x, y0 + 0.02, 0.26);
    T(s, l, {x: x + 0.34, y: y0, w: colW - 0.4, h: 0.3, fontSize: 13, bold: true});
    T(s, RADAR_TEXT[st], {x: x + 0.34, y: y0 + 0.3, w: colW - 0.4, h: 0.25, fontSize: 10.5, color: st === 'ok' ? C.green : st === 'bad' ? C.red : C.amber});
    T(s, d, {x: x + 0.34, y: y0 + 0.58, w: colW - 0.5, h: 0.55, fontSize: 11, color: C.muted, lineSpacingMultiple: 1.1});
  });
  foot(s, '实拍：预制示例在本地运行当前版本。雷达是定性示意，不设评分；每一维取查过的记录里最需关注的一项。');
  notes.push('报告第一眼：五维轮廓和初步结论。经营资格、基本面、资金面都未见异常；风险稳定性因为 5 条行政处罚往里收，消息面待关注。雷达不打分，只让你看个大概。');
}

// ========== 06 第一问 ==========
{
  const s = slide(false, 6);
  kicker(s, '第一问');
  title(s, '发 offer 的和交社保的，是不是同一家？');
  badge(s, 'ok', M, 2.12, 0.72);
  T(s, '已查项\n暂未见异常', {x: M + 0.95, y: 1.95, w: 3.9, h: 1.5, fontFace: SERIF, fontSize: 40, bold: true, color: C.green, lineSpacingMultiple: 1.05});
  T(s, '先看和求职最相关的记录：\n它是持牌银行，参保 7,458 人，\n当被告的劳动官司 0 条。', {x: M, y: 3.65, w: 4.6, h: 1.2, fontSize: 16, bold: true, lineSpacingMultiple: 1.2});
  T(s, '“暂未见异常”只说已查的部分。最后一步要看你自己的劳动合同和社保缴费单位。', {x: M, y: 5.0, w: 4.5, h: 0.8, fontSize: 13, color: C.muted, lineSpacingMultiple: 1.15});
  const rx = 5.85, rw = W - M - rx;
  const rows = [
    ['ok', '持牌机构名单', '银行业金融机构法人名单已收录：城市商业银行', '出处 · 金融监管总局 2025-06-30'],
    ['ok', '参保人数 · 登记状态', '年报参保 7,458 人；存续 30 年', '出处 · 企查查工商数据'],
    ['ok', '劳动纠纷', '劳动仲裁 4 条，当被告的劳动官司 0 条', '出处 · 企查查涉诉数据'],
    ['ok', '招聘', '188 条，最近 2026-01-14；月薪如 12-20K、7-12K', '出处 · 企查查招聘数据'],
  ];
  rows.forEach(([k, l, v, src], i) => {
    const y = 1.95 + i * 1.0;
    card(s, rx, y, rw, 0.85);
    badge(s, k, rx + 0.22, y + 0.14, 0.3);
    T(s, l, {x: rx + 0.68, y: y + 0.12, w: 3.2, h: 0.32, fontSize: 14.5, bold: true});
    chip(s, src, rx + rw - 0.2, y + 0.13, {right: true, pt: 9.5, h: 0.27});
    T(s, v, {x: rx + 0.68, y: y + 0.48, w: rw - 0.9, h: 0.3, fontSize: 12.5});
  });
  card(s, rx, 5.98, rw, 0.62, {fill: C.paper2, line: C.paper2});
  T(s, [{text: '怎么核：', options: {bold: true, color: C.brass}}, {text: '入职后在社保 App 或当地社保查询里，看缴费单位名称。'}], {x: rx + 0.25, y: 6.1, w: rw - 0.5, h: 0.4, fontSize: 13});
  notes.push('第一问：发 offer 的和交社保的是不是同一家？它是持牌城商行，参保 7458 人，存续 30 年，当被告的劳动官司 0 条。结论是已查项暂未见异常。但这只说已查的部分，最后要看你自己的合同和社保缴费单位，系统也写了怎么核。');
}

// ========== 07 逐条对照 ==========
{
  const s = slide(true, 7);
  kicker(s, '逐条对照', true);
  title(s, '它说的，和记录里的', true);
  const cx1 = M, cx2 = 5.0, cx3 = 10.35;
  T(s, '招聘公告上说', {x: cx1, y: 1.85, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  T(s, '记录里查到', {x: cx2, y: 1.85, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  T(s, '规则判定', {x: cx3, y: 1.85, w: 2.2, h: 0.3, fontSize: 12, bold: true, color: C.creamM});
  const rows = [
    ['全行拥有 200 余家分支机构', '336 家', '登记的分支机构\n登记的规模和宣传大致相符'],
    ['2016 年上交所上市，\n股票代码 600926', '600926', '上交所主板，上市日期 2016-10-27\n和宣传说的一致'],
  ];
  rows.forEach(([said, big, sub], i) => {
    const y = 2.3 + i * 1.25;
    hline(s, M, y - 0.08, CW, C.navyLine);
    T(s, said, {x: cx1, y: y + 0.15, w: 4.0, h: 0.85, fontFace: SERIF, fontSize: 20, bold: true, color: C.cream, lineSpacingMultiple: 1.1});
    T(s, big, {x: cx2, y: y + 0.12, w: 2.2, h: 0.75, fontFace: SERIF, fontSize: 34, bold: true, color: C.brassL});
    T(s, sub, {x: cx2 + 2.3, y: y + 0.2, w: 2.95, h: 0.7, fontSize: 12.5, color: C.creamM, lineSpacingMultiple: 1.1});
    pill(s, '与记录相符', cx3, y + 0.27, C.green, {w: 1.75, pt: 13});
  });
  hline(s, M, 2.3 + 2 * 1.25 - 0.08, CW, C.navyLine);
  T(s, '正规公司的说法，大部分能对上。\n这本身就是一个有用的结论。', {x: M, y: 5.0, w: 7.5, h: 1.2, fontFace: SERIF, fontSize: 24, bold: true, color: C.cream, lineSpacingMultiple: 1.2});
  T(s, '这次材料里抽出 2 条可对照的说法。\n同一套规则用在问题公司上，\n会标出“与记录不符”“不合规承诺”\n（见备用页）。', {x: 8.55, y: 5.0, w: 4.03, h: 1.4, fontSize: 12, color: C.creamM, lineSpacingMultiple: 1.2});
  foot(s, '对方的每条说法，都拿官方记录和法规对一遍。判定由固定规则给出，不由 AI 决定。', true);
  notes.push('再把招聘公告里的说法和记录对照：200 余家分支机构，登记的是 336 家；2016 年上市、代码 600926，和上市记录一致。正规公司的说法大多能对上，这本身就是有用的结论。判定由规则给出，不是 AI 拍脑袋。');
}

// ========== 08 记录照实列出 ==========
{
  const s = slide(false, 8);
  kicker(s, '记录照实列出');
  title(s, '处罚和官司不藏也不放大，标上日期和出处');
  const iw = 7.3;
  // 时间线（取自预制示例 B 的事件与处罚记录，按顺序排列、非等距）
  const ev = [
    ['1996', '09-25', '公司成立', 'ok'],
    ['2021', '07-05', '许可 / 批复', 'ok'],
    ['2022', '05-23', '人行杭州中支\n罚款 580 万', 'bad'],
    ['2023', '07-21', '浙江证监局\n责令改正', 'bad'],
    ['2024', '01-09', '浙江金融监管\n罚款 210 万', 'bad'],
    ['2024', '08-12', '浙江金融监管\n罚款 110 万', 'bad'],
    ['2024', '11-25', '外汇局浙江\n处罚', 'bad'],
    ['2025', '11-07', '网上投诉\n1 条', 'warn'],
  ];
  card(s, M, 1.85, iw, 3.2, {fill: C.card});
  T(s, '1996 — 2026', {x: M + 0.3, y: 2.0, w: 3, h: 0.45, fontFace: SERIF, fontSize: 20, bold: true});
  T(s, '按事件顺序排列 · 非等距', {x: M + iw - 3.3, y: 2.08, w: 3, h: 0.3, fontSize: 10.5, color: C.muted, align: 'right'});
  const ty = 3.15, step = (iw - 0.8) / (ev.length - 1);
  hline(s, M + 0.4, ty, iw - 0.8, C.line);
  ev.forEach(([yr, md, lab, st], i) => {
    const cx = M + 0.4 + i * step;
    const col = st === 'bad' ? C.red : st === 'warn' ? C.amber : C.brass;
    T(s, yr, {x: cx - 0.45, y: ty - 0.5, w: 0.9, h: 0.28, fontSize: 12, bold: true, align: 'center'});
    s.addShape(p.shapes.OVAL, {x: cx - 0.08, y: ty - 0.08, w: 0.16, h: 0.16, fill: {color: col}, line: {color: 'FFFFFF', width: 1.5}});
    T(s, md, {x: cx - 0.45, y: ty + 0.18, w: 0.9, h: 0.25, fontSize: 10.5, color: C.muted, align: 'center'});
    T(s, lab, {x: cx - 0.5, y: ty + 0.45, w: 1.0, h: 0.6, fontSize: 10, color: st === 'ok' ? C.muted : C.ink, align: 'center', lineSpacingMultiple: 1.05});
  });
  T(s, '另有 1 条罚款 975 万元（浙江金融监管局，日期未公示）。每个节点在报告里都能点开原文。', {x: M + 0.3, y: 4.55, w: iw - 0.6, h: 0.35, fontSize: 11, color: C.muted});
  card(s, M, 5.35, iw, 1.3, {fill: C.paper2, line: C.paper2});
  T(s, '系统建议你问对方的第一个问题', {x: M + 0.3, y: 5.5, w: iw - 0.6, h: 0.3, fontSize: 12, bold: true, color: C.brass});
  T(s, '“监管点名的事项，处理完了吗？”', {x: M + 0.3, y: 5.82, w: iw - 0.6, h: 0.45, fontFace: SERIF, fontSize: 20, bold: true});
  T(s, '怎么核：点开原始数据里的原文链接，看处罚或通报的内容和日期', {x: M + 0.3, y: 6.27, w: iw - 0.6, h: 0.3, fontSize: 11.5, color: C.muted});
  const rx = M + iw + 0.45, rw = W - M - rx;
  const facts = [
    ['bad', '行政处罚 5 条', '2022—2024 年，人行杭州中支、\n金融监管总局浙江监管局等；\n罚款 110 万至 975 万元'],
    ['bad', '政府网站点名 1 份', '2023-07-21 证监会浙江监管局：责令改正措施'],
    ['warn', '近一年负面新闻 2 条', '最近一条 2026-09-30，报道罚款 975 万元'],
    ['ok', '劳动纠纷', '劳动仲裁 4 条，当被告的劳动官司 0 条'],
  ];
  facts.forEach(([k, h, d], i) => {
    const y = 1.9 + i * 1.18;
    badge(s, k, rx, y + 0.02, 0.28);
    T(s, h, {x: rx + 0.4, y, w: rw - 0.4, h: 0.32, fontSize: 14.5, bold: true});
    T(s, d, {x: rx + 0.4, y: y + 0.36, w: rw - 0.4, h: 0.75, fontSize: 11.5, color: C.muted, lineSpacingMultiple: 1.12});
  });
  foot(s, '资料截至 2026-10-02；只列查到的事，没查到不代表没发生。');
  notes.push('处罚和官司，企 er 不藏也不放大：2022 到 2024 年 5 条行政处罚、2023 年一份责令改正，都标上日期，能点开原文。系统不替你下结论，而是告诉你该问什么、去哪儿核。');
}

// ========== 09 该问的问题 + 一页结论 ==========
{
  const s = slide(false, 9);
  kicker(s, '带着问题去签约');
  title(s, '该问对方的 4 个问题，和一页结论');
  const qs = [
    ['监管点名的事项，处理完了吗？', '点开原文链接，看处罚或通报的内容和日期'],
    ['发 offer 的、签劳动合同的、交社保的，是不是同一家？', '入职后在社保 App 里看缴费单位名称'],
    ['入职前要不要交任何费用？', '正规单位不收；被要求交钱可向人社部门举报'],
    ['试用期多长、工资多少，写进劳动合同了吗？', '看合同原文；试用期上限见《劳动合同法》第十九条'],
  ];
  qs.forEach(([q, how], i) => {
    const y = 1.9 + i * 1.0;
    T(s, String(i + 1).padStart(2, '0'), {x: M, y, w: 0.6, h: 0.4, fontFace: SERIF, fontSize: 20, bold: true, color: C.brassL});
    T(s, q, {x: M + 0.65, y: y + 0.02, w: 6.5, h: 0.4, fontSize: 15.5, bold: true});
    T(s, '怎么核：' + how, {x: M + 0.65, y: y + 0.43, w: 6.5, h: 0.3, fontSize: 12, color: C.muted});
    if (i < 3) hline(s, M + 0.65, y + 0.86, 6.5, C.line);
  });
  card(s, M, 5.95, 7.15, 0.7, {fill: C.paper2, line: C.paper2});
  T(s, [{text: '拿到 offer 或劳动合同？', options: {bold: true, color: C.brass}}, {text: '补进同一个案卷，出新版本，标出哪里变了、为什么。'}], {x: M + 0.25, y: 6.1, w: 6.8, h: 0.4, fontSize: 13});
  const ih = 4.95, iw = ih * 1520 / 1904, ix = W - M - iw;
  s.addImage({path: A('crops/B-print.jpg'), x: ix, y: 1.6, w: iw, h: ih, altText: '杭州银行案卷的一页结论打印预览', shadow: shadow()});
  chip(s, '实拍 · 一页结论，可切换给家人 / 给网点柜员', W - M, 6.63, {right: true, pt: 9.5, h: 0.26});
  notes.push('最后落到行动：该问对方的 4 个问题，每个都写了怎么核。右边是一键打印的一页结论，给家人或给网点柜员。拿到劳动合同后补进案卷，系统出新版本，标出哪里变了。');
}

// ========== 07 追问与出处 ==========
{
  const s = slide(false, 10);
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

// ========== 09 方法 ==========
{
  const s = slide(true, 11);
  kicker(s, '方法', true);
  title(s, '结论来自记录和规则，AI 只负责读材料、说人话', true, {fontSize: 30});
  const steps = [
    ['汇集', '公开记录 + 用户材料', '持牌名单、工商年报、\n财报、司法舆情；\n招聘公告、合同、截图'],
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

// ========== 12 换一个需求，换一个第一问 ==========
{
  const s = slide(false, 12);
  kicker(s, '同一套方法');
  title(s, '换一个需求，换一个第一问');
  // 文案取自 backend/app/scenarios/*.json 的 label / first_question / hand_over
  const sc = [
    ['求职入职', '发 offer 的和交社保的\n是不是同一家；有没有让你先交钱', '时间和信任，有时还有押金、培训费', true],
    ['存钱 / 理财 / 投资', '它有没有资格收这笔钱', '储蓄'],
    ['合作签约 / 付款', '签约方、收款方、干活的\n是不是同一家，有没有所需资质', '货款、定金'],
    ['预付消费', '收钱的是不是跟你签约、\n给你服务的那家公司', '预付款'],
    ['接手 / 入股', '股权干不干净（出质、冻结）\n有没有对外担保和欠税', '资金和经营责任'],
    ['其他', '它是不是它说的那家公司，\n记录和说法对不对得上', '钱或信任'],
  ];
  const cw = (CW - 2 * 0.3) / 3, ch = 1.85;
  sc.forEach(([l, q, give, cur], i) => {
    const x = M + (i % 3) * (cw + 0.3), y = 1.85 + Math.floor(i / 3) * (ch + 0.25);
    card(s, x, y, cw, ch, {fill: cur ? C.navy : C.card, line: cur ? C.navy : C.line});
    T(s, l, {x: x + 0.28, y: y + 0.2, w: cw - 0.56, h: 0.35, fontFace: SERIF, fontSize: 16, bold: true, color: cur ? C.brassL : C.brass});
    if (cur) chip(s, '今天的示例', x + cw - 0.25, y + 0.22, {right: true, dark: true, pt: 9.5, h: 0.26});
    T(s, '第一问：' + q, {x: x + 0.28, y: y + 0.65, w: cw - 0.56, h: 0.75, fontSize: 13, bold: true, color: cur ? C.cream : C.ink, lineSpacingMultiple: 1.12});
    T(s, '交出去的：' + give, {x: x + 0.28, y: y + 1.43, w: cw - 0.5, h: 0.3, fontSize: 10.5, color: cur ? C.creamM : C.muted});
  });
  T(s, [{text: '对杭州银行：', options: {bold: true, color: C.brass}}, {text: '网点劝阻客户、手机银行转账前“透视收款方”、校招与对公客户尽调，用的都是同一份案卷。'}], {x: M, y: 6.15, w: CW, h: 0.4, fontSize: 14});
  foot(s, '落地场景为设想，待与杭州银行业务方共同验证。');
  notes.push('同一套方法，换个需求就换个第一问：理财先问有没有资格收钱，签约先问签约收款干活是不是同一家。对杭州银行，网点劝阻、转账前透视收款方、校招和对公尽调，都能用同一份案卷，这些还要和业务方一起验证。');
}

// ========== 11 收尾 ==========
{
  const s = slide(true, 13);
  T(s, '把钱或信任交出去之前，\n先把依据看清楚。', {x: M, y: 1.7, w: 7.2, h: 2.2, fontFace: SERIF, fontSize: 42, bold: true, color: C.cream, lineSpacingMultiple: 1.2});
  T(s, '企er · 有出处的企业研究助手', {x: M, y: 4.25, w: 7, h: 0.45, fontSize: 18, color: C.brassL, bold: true});
  T(s, 'qier.asia', {x: M, y: 5.25, w: 5, h: 0.75, fontFace: SERIF, fontSize: 36, bold: true, color: C.brassL});
  T(s, '现场可试：输入任意公司全称，再加一句需求。', {x: M, y: 6.05, w: 6.5, h: 0.35, fontSize: 14, color: C.creamM});
  s.addImage({path: A('closing-office.png'), x: 7.75, y: 0.9, w: 4.83, h: 5.74, altText: '小企在办公室阅读报告的插画'});
  notes.push('企 er 把一次查询，变成一份能追问、能补充、能回看的研究案卷。把钱或信任交出去之前，先把依据看清楚。网址是 qier.asia，现场就可以输入任意公司试一试。谢谢大家。');
}

// ========== 05 报告第一眼：五维轮廓 ==========
{
  const s = slide(false, 14);
  kicker(s, '答辩备用 · 问题公司长什么样');
  title(s, '同一把尺子：问题公司和杭州银行');
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
  notes.push('答辩备用。同一套规则放在问题公司上是什么样？报告的第一眼是企业五维轮廓：经营资格、基本面、资金面、风险稳定性、消息面。它不打分，每一维只取查过的记录里最需要留意的一项，越往里越要当心。左边是虚构的满盈禾，五维都有异常记录，整个缩成一圈；右边是真实的杭州银行，资格、基本面、资金面都未见异常，只有行政处罚和负面新闻让两维往里收。两家公司差在哪，一眼就能看个大概。');
}

// ========== 08 版本 ==========
{
  const s = slide(false, 15);
  kicker(s, '答辩备用 · 补充材料（虚构示例）');
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
  notes.push('答辩备用，用的是虚构示例满盈禾。判断不是一次就结束的。对方业务员回微信说：钱转到财务的个人账户，急用随时可以取。补进来，v2 马上标出新疑点：收款人是个人。再补一份认购协议，写着 12 个月封闭期、不得提前赎回，v3 就把“随时可取”从无法核验改成与记录不符。如果误传了一张停水通知，判断不会乱动。每个版本和旧回答的出处都保留。');
}

// ========== 13 备用：查询状态与边界 ==========
{
  const s = slide(false, 16);
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
const chars = notes.slice(0, 13).join('').replace(/[\s\p{P}\p{S}]/gu, '').length;
console.log('RENDERED', deck.slides.items.length, 'slides; main-script chars', chars);

// ---------- speaker script ----------
const titles = ['封面', '从一句话开始', '查得到，不等于看得懂', '产品入口', '报告第一眼：五维轮廓和初步结论', '第一问：发 offer 的和交社保的是不是同一家', '它说的，和记录里的', '记录照实列出', '该问的问题和一页结论', '追问与出处', '方法：规则与 AI 的分工', '换一个需求，换一个第一问', '收尾', '答辩备用：问题公司对照', '答辩备用：补充材料后的版本', '答辩备用：查询状态与边界'];
const secs = [10, 28, 25, 18, 26, 26, 22, 26, 25, 20, 24, 22, 12];
const md = ['# 企er 路演 v08 · 逐页讲稿', '',
  `主讲第 1–13 页，按 ${secs.reduce((a, b) => a + b, 0)} 秒分配（约 ${chars} 字，不含标点），留出翻页和停顿；第 14–16 页答辩备用。讲稿也写进了每页的演讲者备注。尚未真人排练计时。`, '',
  ...notes.flatMap((n, i) => [`## ${i + 1}. ${titles[i]}${secs[i] ? `（${secs[i]} 秒）` : ''}`, '', n, ''])];
await fs.writeFile(path.join(here, '逐页讲稿-v08.md'), md.join('\n'));
