export type Point = { x: number; y: number };
export type Facing = 'back' | 'front' | 'right' | 'left';
export type Phase = { id: string; label: string; detail: string; start: number; end: number; mode: 'walk' | 'action'; visual: string; from: Point; to: Point; route?: Point[]; papers: number };
export const SEAT = { x: 50, y: 96 };
const A = { x: 24, y: 44 }, L = { x: 15, y: 62 }, N = { x: 70, y: 43 }, C = { x: 76, y: 67 }, D = { x: 45, y: 42 };
const exit = [SEAT, { x: 47, y: 98 }, { x: 24, y: 98 }, { x: 24, y: 70 }, A];
const home = [D, { x: 50, y: 49 }, { x: 69, y: 56 }, { x: 76, y: 68 }, { x: 76, y: 98 }, { x: 50, y: 98 }, SEAT];
const specs: Array<[string, number, string, string, Point[], number]> = [
  ['brief', 1100, '确认研究任务', 'desk', [SEAT], 0],
  ['stand', 1000, '放下资料，起身', 'stand', [SEAT], 0],
  ['walk-archive', 5700, '前往企业资料柜', 'walk', exit, 0],
  ['archive', 1400, '核对企业资料', 'research', [A], 0],
  ['walk-library', 1600, '前往窗下书架', 'walk', [A, {x:20,y:51}, L], 1],
  ['library', 1600, '翻阅图书与年报', 'research', [L], 1],
  ['walk-news', 4000, '前往新闻资料架', 'walk', [L, {x:23,y:52}, {x:49,y:48}, {x:62,y:48}, N], 2],
  ['news', 1300, '摘录新闻摘要', 'research', [N], 2],
  ['walk-data', 1500, '前往数据终端', 'walk', [N, {x:73,y:51}, C], 3],
  ['data', 1300, '核验经营数据', 'research', [C], 3],
  ['knock', 650, '门外传来敲门声', 'listen', [C], 4],
  ['walk-door', 2700, '走向办公室门', 'walk', [C, {x:68,y:51}, {x:51,y:46}, D], 4],
  ['open-door', 1000, '打开办公室门', 'door', [D], 4],
  ['talk', 1800, '交流社会舆情', 'talk', [D], 4],
  ['close-door', 900, '结束访谈，关门', 'door', [D], 4],
  ['walk-desk', 5600, '带着资料返回工位', 'walk', home, 5],
  ['sit', 1000, '坐回椅子，整理资料', 'sit', [SEAT], 5],
  ['report', 2400, '撰写研究报告', 'desk', [SEAT], 5],
];
let cursor = 0;
const screenDistance = (a:Point,b:Point) => Math.hypot((b.x-a.x)*16.72,(b.y-a.y)*9.41);
// Round a corner inside its adjacent segments, without cutting through furniture.
function roundedRoute(points:Point[]) {
  const route=[points[0]];
  for(let i=1;i<points.length-1;i++) {
    const a=points[i-1], b=points[i], c=points[i+1];
    const radius=Math.min(30,screenDistance(a,b)/3,screenDistance(b,c)/3);
    const u=radius/screenDistance(a,b),v=radius/screenDistance(b,c);
    const entry={x:b.x+(a.x-b.x)*u,y:b.y+(a.y-b.y)*u};
    const exit={x:b.x+(c.x-b.x)*v,y:b.y+(c.y-b.y)*v};
    route.push(entry);
    for(let step=1;step<=8;step++) {
      const t=step/8,s=1-t;
      route.push({x:s*s*entry.x+2*s*t*b.x+t*t*exit.x,y:s*s*entry.y+2*s*t*b.y+t*t*exit.y});
    }
  }
  route.push(points.at(-1)!);
  return route;
}
export const phases: Phase[] = specs.map(([id, duration, label, visual, route, papers]) => {
  const start = cursor; cursor += duration;
  return {id, start, end:cursor, label, detail: label, visual, mode:visual === 'walk' ? 'walk' : 'action', from:route[0], to:route.at(-1)!, route:visual === 'walk' ? roundedRoute(route) : undefined, papers};
});
export const DURATION = cursor;
export const phaseAt = (time:number) => phases.find(p => time < p.end) ?? phases.at(-1)!;
export const phaseProgress = (p:Phase, time:number) => Math.max(0,Math.min(1,(time-p.start)/(p.end-p.start)));
export const ease = (t:number) => t*t*(3-2*t);
export function motionAt(p:Phase, time:number) {
  if (!p.route) return {position:p.to, facing:'back' as Facing, distance:0, frame:0};
  const segments = p.route.slice(1).map((to,i) => ({from:p.route![i],to,length:Math.hypot((to.x-p.route![i].x)*16.72,(to.y-p.route![i].y)*9.41)}));
  const total=segments.reduce((s,p)=>s+p.length,0);
  const progress=phaseProgress(p,time);
  // A short acceleration/deceleration at the ends; constant pace through the route.
  const ramp=.08;
  const travel=progress<ramp ? progress*progress/(2*ramp*(1-ramp)) : progress>1-ramp ? 1-(1-progress)**2/(2*ramp*(1-ramp)) : (progress-ramp/2)/(1-ramp);
  const distance=total*travel;
  let remaining=distance;
  let segment=segments[segments.length-1];
  for (const [i,candidate] of segments.entries()) { segment=candidate; if(remaining<=candidate.length || i===segments.length-1) break; remaining-=candidate.length; }
  const t=Math.min(1,remaining/segment.length);
  const dx=(segment.to.x-segment.from.x)*16.72, dy=(segment.to.y-segment.from.y)*9.41;
  const facing:Facing=Math.abs(dy)>Math.abs(dx)*.65 ? dy<0?'back':'front' : dx<0?'left':'right';
  return {position:{x:segment.from.x+(segment.to.x-segment.from.x)*t,y:segment.from.y+(segment.to.y-segment.from.y)*t},facing,distance,frame:Math.floor(distance/21)%4};
}
export function doorAt(time:number) {
  const open=phases.find(p=>p.id==='open-door')!, close=phases.find(p=>p.id==='close-door')!;
  if(time<open.start || time>=close.end) return 0;
  if(time<open.end) return ease(phaseProgress(open,time));
  if(time<close.start) return 1;
  return 1-ease(phaseProgress(close,time));
}
