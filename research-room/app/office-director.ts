import { motionAt, roundedRoute, SEAT, ease } from './office-motion.ts';
import type { Point, Phase } from './office-motion';
import { stations, collectionFinished } from './research-events.ts';
import type { ResearchState, Station } from './research-events';
const locations: Record<Station, Point> = {
  enterprise: { x: 24, y: 44 },
  library: { x: 15, y: 62 },
  news: { x: 70, y: 43 },
  data: { x: 76, y: 67 },
  social: { x: 45, y: 42 },
};
type Action = Phase & { station?: Station; tasks?: string[]; finish?: string };
const same = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y) < 0.01;
// Feet navigate a walkable graph. Desk footprint is never used as a shortcut.
const nodes = [
  SEAT,
  { x: 50, y: 98 },
  { x: 24, y: 98 },
  { x: 24, y: 68 },
  { x: 24, y: 49 },
  { x: 50, y: 49 },
  { x: 70, y: 49 },
  { x: 76, y: 68 },
  { x: 76, y: 98 },
  locations.enterprise,
  locations.library,
  locations.news,
  locations.data,
  locations.social,
  { x: 32, y: 98 },
];
const edges = [
  [0, 1],
  [1, 14],
  [14, 2],
  [2, 3],
  [3, 4],
  [4, 5],
  [5, 6],
  [6, 7],
  [7, 8],
  [8, 1],
  [4, 9],
  [3, 10],
  [6, 11],
  [7, 12],
  [5, 13],
];
const dist = (a: Point, b: Point) =>
  Math.hypot((a.x - b.x) * 16.72, (a.y - b.y) * 9.41);
export function routeBetween(from: Point, to: Point) {
  if (same(from, to)) return [from, to];
  const start = nodes.findIndex((n) => same(n, from)),
    end = nodes.findIndex((n) => same(n, to));
  if (start < 0 || end < 0) throw new Error('Unknown office waypoint');
  const costs = nodes.map(() => Infinity),
    prev = nodes.map(() => -1),
    visited = new Set<number>();
  costs[start] = 0;
  while (!visited.has(end)) {
    let best = -1;
    for (let i = 0; i < nodes.length; i++)
      if (!visited.has(i) && (best < 0 || costs[i] < costs[best])) best = i;
    if (best < 0 || !Number.isFinite(costs[best]))
      throw new Error('No office route');
    visited.add(best);
    for (const [a, b] of edges) {
      const next = a === best ? b : b === best ? a : -1;
      if (next < 0) continue;
      const cost = costs[best] + dist(nodes[best], nodes[next]);
      if (cost < costs[next]) {
        costs[next] = cost;
        prev[next] = best;
      }
    }
  }
  const path = [];
  for (let i = end; i !== -1; i = prev[i]) path.unshift(nodes[i]);
  return roundedRoute(path);
}
export class OfficeDirector {
  clock = 0;
  local = 0;
  position: Point = SEAT;
  queue: Action[] = [];
  visited = new Set<string>();
  returning = false;
  finished = false;
  paperStage = 0;
  reportStage = 0;
  socialHandled = false;
  socialStarted = false;
  action: Action = this.make('idle', '等待研究任务', 'desk', 900, SEAT);
  make(
    id: string,
    label: string,
    visual: string,
    duration: number,
    to: Point,
    extra: Partial<Action> = {},
  ): Action {
    return {
      id,
      label,
      detail: label,
      visual,
      mode: visual === 'walk' ? 'walk' : 'action',
      start: 0,
      end: duration,
      from: this.position,
      to,
      papers: 0,
      ...extra,
    };
  }
  walk(to: Point, label: string) {
    const route = routeBetween(this.position, to);
    const length = route.slice(1).reduce((n, p, i) => n + dist(route[i], p), 0);
    const a = this.make(
      'walk',
      label,
      'walk',
      Math.max(220, (length / 560) * 1000),
      to,
      { route },
    );
    this.position = to;
    return a;
  }
  setNext() {
    const a = this.queue.shift();
    if (a) {
      this.action = a;
      this.local = 0;
    }
  }
  tick(delta: number, state: ResearchState) {
    if (this.finished) return;
    if (state.connection === 'disconnected' || state.connection === 'error') return;
    // Backend processing stages own the desk activity, never an elapsed-time guess.
    if (this.action.id === 'idle' || this.action.id === 'report') {
      const running = state.steps.find((s) => !s.lookup && s.phase === 'start');
      const labels: Record<string, string> = {
        intake: '读懂研究需求', rules: '对照记录与规则', plain: '撰写研究报告',
      };
      this.action.label = running ? labels[running.id] ?? running.label
        : this.action.id === 'report' ? '等待报告保存确认' : '等待研究任务';
    }
    this.clock += delta;
    this.local += delta;
    const a = this.action;
    const pendingLookup = state.steps.some((s) => s.lookup && s.phase === 'start' &&
      !this.visited.has(s.id) && s.id !== 'reviews' && s.id !== 'opinion');
    const lookupEnded = a.id === 'research' &&
      !a.tasks?.some((id) => state.steps.some((s) => s.id === id && s.phase === 'start'));
    // Wake a stationary actor immediately. A walk still finishes continuously.
    const boundary = this.local >= a.end || lookupEnded ||
      ((a.id === 'idle' || a.id === 'wait') && pendingLookup);
    if (!boundary) return;
    if (a.finish === 'left') this.paperStage = 1;
    if (a.finish === 'right') this.paperStage = 2;
    if (a.finish === 'sort') this.paperStage = 3;
    if (a.id === 'bind-report') this.reportStage = 1;
    if (a.id === 'push-report') this.reportStage = 2;
    if (a.id === 'present-report') this.reportStage = 3;
    if (a.id === 'close-door') this.socialHandled = true;
    const collectionDone = collectionFinished(state);
    const hasVisitor = state.steps.some(
      (s) => (s.id === 'reviews' || s.id === 'opinion') &&
        s.phase === 'done' && s.coverage === 'found',
    );
    const receivingVisitor = this.socialStarted && !this.socialHandled;
    const shouldReceive = hasVisitor && !this.socialStarted && !this.socialHandled &&
      !this.returning && state.connection !== 'saved';

    // Completion cancels unstarted source actions. Finish the current movement and
    // any committed reception, then return directly; never replay completed lookups.
    if ((collectionDone || state.connection === 'saved') && !this.returning &&
        !receivingVisitor && !shouldReceive) {
      this.queue = [];
      this.returning = true;
      this.position = a.to;
      this.socialHandled = true;
      if (!same(this.position, SEAT)) {
        this.queue.push(this.walk(SEAT, '资料收集已结束，返回工位'));
        this.queue.push(this.make('sit', '回到工位', 'sit', 200, SEAT));
      } else if (a.visual !== 'desk')
        this.queue.push(this.make('sit', '回到工位', 'sit', 200, SEAT));
      this.queue.push(this.make('sort', '核对并归档资料', 'desk', 350, SEAT, { finish: 'sort' }));
      this.queue.push(this.make('report', '核对资料并撰写报告', 'desk', 250, SEAT));
      this.setNext();
      return;
    }
    if (shouldReceive) {
      // Knocking and the journey share this one committed sequence. Arrival at
      // the door always opens it; a generic social lookup never sends us there.
      for (const task of [a, ...this.queue])
        for (const id of task.tasks ?? [])
          if (state.steps.some((s) => s.id === id && s.phase === 'start'))
            this.visited.delete(id);
      this.queue = [];
      this.socialStarted = true;
      this.position = a.to;
      if (a.visual === 'desk')
        this.queue.push(this.make('stand', '放下资料，起身', 'stand', 250, SEAT));
      if (!same(this.position, locations.social))
        this.queue.push(this.walk(locations.social, '门外传来敲门声，前往接待访客'));
      this.queue.push(
        this.make('open-door', '开门接待访客', 'door', 900, this.position),
        this.make('talk-visitor', '听访客讲新闻和投诉（未经核实）', 'talk', 1200, this.position),
        this.make('close-door', '告别访客，关门', 'door', 900, this.position),
      );
      this.setNext();
      return;
    }
    if (
      a.id === 'research' &&
      a.tasks?.some(
        (id) => state.steps.find((s) => s.id === id)?.phase === 'start',
      )
    ) {
      this.local %= a.end;
      return;
    }
    if (!receivingVisitor && this.queue.some((task) => task.id === 'research' &&
        !task.tasks?.some((id) => state.steps.some((s) => s.id === id && s.phase === 'start')))) {
      this.queue = [];
      this.position = a.to;
    }
    if (this.queue.length) {
      this.setNext();
      return;
    }
    const pending = state.steps.filter(
      (s) => s.lookup && s.phase === 'start' && !this.visited.has(s.id) &&
        s.id !== 'reviews' && s.id !== 'opinion',
    );
    const first = pending[0];
    if (first && !this.returning) {
      const station = stations.find((s) =>
        (s.steps as readonly string[]).includes(first.id),
      );
      if (!station) {
        this.visited.add(first.id);
        return;
      }
      const tasks = pending
        .filter((s) => (station.steps as readonly string[]).includes(s.id))
        .map((s) => s.id);
      tasks.forEach((id) => this.visited.add(id));
      if (a.visual === 'desk')
        this.queue.push(this.make('stand', '放下资料，起身', 'stand', 250, SEAT));
      this.queue.push(this.walk(locations[station.id], `前往${station.title}`));
      this.queue.push(this.make(
        'research', `查阅${station.title}`, 'research', 1600,
        this.position, { station: station.id, tasks },
      ));
      this.setNext();
      return;
    }
    if (this.returning && state.connection === 'saved') {
      if (this.reportStage < 3) {
        const next =
          this.reportStage === 0
            ? this.make(
                'bind-report',
                '合上封面，装订企业研究卷宗',
                'desk',
                450,
                SEAT,
              )
            : this.reportStage === 1
              ? this.make(
                  'push-report',
                  '将卷宗推到桌面中央',
                  'desk',
                  350,
                  SEAT,
                )
              : this.make(
                  'present-report',
                  '收回翅膀，示意查看报告',
                  'desk',
                  350,
                  SEAT,
                );
        this.action = next;
        this.local = 0;
        return;
      }
      this.finished = true;
      this.action = this.make('complete', '报告已保存', 'desk', 1, SEAT);
      this.local = 0;
      return;
    }
    // A canceled lookup can leave us just standing up. Settle back into the
    // chair instead of looping the stand-up transition while waiting for work.
    if (a.visual === 'stand' || a.visual === 'sit') {
      this.action = a.visual === 'stand'
        ? this.make('sit', '等待后续资料任务', 'sit', 200, SEAT)
        : this.make('idle', '等待后续资料任务', 'desk', 900, SEAT);
      this.local = 0;
      return;
    }
    // Wait at a stable location, not on a walking cel or a completed lookup.
    if (a.mode === 'walk' || a.id === 'research')
      this.action = this.make(
        'wait',
        '等待后续资料任务',
        'research',
        1200,
        this.position,
      );
    this.local %= this.action.end;
  }
  sample() {
    const a = this.action,
      p = Math.min(1, this.local / a.end),
      motion = motionAt(a, Math.min(this.local, a.end));
    const seated =
      a.visual === 'desk'
        ? 1
        : a.visual === 'stand'
          ? 1 - ease(p)
          : a.visual === 'sit'
            ? ease(p)
            : 0;
    const door =
      a.id === 'open-door'
        ? ease(p)
        : a.id === 'close-door'
          ? 1 - ease(p)
          : a.visual === 'talk'
            ? 1
            : 0;
    const gathering =
      a.id === 'sort' ? ease(p) : a.id === 'gather-left' ? ease(p) : this.paperStage >= 1 ? 1 : 0;
    const gatheringRight =
      a.id === 'sort' ? ease(p) : a.id === 'gather-right' ? ease(p) : this.paperStage >= 2 ? 1 : 0;
    const sorting = a.id === 'sort' ? ease(p) : this.paperStage >= 3 ? 1 : 0;
    const binding =
      a.id === 'bind-report' ? ease(p) : this.reportStage >= 1 ? 1 : 0;
    const pushing =
      a.id === 'push-report' ? ease(p) : this.reportStage >= 2 ? 1 : 0;
    const presenting =
      a.id === 'present-report' ? ease(p) : this.reportStage >= 3 ? 1 : 0;
    const wingReach =
      a.id === 'bind-report'
        ? ease(Math.min(1, p * 2))
        : a.id === 'push-report'
          ? 1 - pushing * 0.4
          : a.id === 'present-report'
            ? 0.6 * (1 - presenting)
            : 0;
    return {
      phase: a,
      motion,
      seated,
      door,
      local: this.local,
      clock: this.clock,
      socialHandled: this.socialHandled,
      knocking: this.socialStarted && !this.socialHandled && door === 0 &&
        a.id !== 'close-door',
      gathering,
      gatheringRight,
      sorting,
      binding,
      pushing,
      presenting,
      wingReach,
      finished: this.finished,
    };
  }
}
