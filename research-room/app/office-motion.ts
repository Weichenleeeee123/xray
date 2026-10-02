export type Point = { x: number; y: number };
export type Facing = 'back' | 'front' | 'right' | 'left';
export type Phase = {
  id: string;
  label: string;
  detail: string;
  start: number;
  end: number;
  mode: 'walk' | 'action';
  visual: string;
  from: Point;
  to: Point;
  route?: Point[];
  papers: number;
};
export const SEAT = { x: 50, y: 96 };
const screenDistance = (a: Point, b: Point) =>
  Math.hypot((b.x - a.x) * 16.72, (b.y - a.y) * 9.41);
// Round a corner inside its adjacent segments, without cutting through furniture.
export function roundedRoute(points: Point[]) {
  const route = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1],
      b = points[i],
      c = points[i + 1];
    const radius = Math.min(
      30,
      screenDistance(a, b) / 3,
      screenDistance(b, c) / 3,
    );
    const u = radius / screenDistance(a, b),
      v = radius / screenDistance(b, c);
    const entry = { x: b.x + (a.x - b.x) * u, y: b.y + (a.y - b.y) * u };
    const exit = { x: b.x + (c.x - b.x) * v, y: b.y + (c.y - b.y) * v };
    route.push(entry);
    for (let step = 1; step <= 8; step++) {
      const t = step / 8,
        s = 1 - t;
      route.push({
        x: s * s * entry.x + 2 * s * t * b.x + t * t * exit.x,
        y: s * s * entry.y + 2 * s * t * b.y + t * t * exit.y,
      });
    }
  }
  route.push(points.at(-1)!);
  return route;
}
export const phaseProgress = (p: Phase, time: number) =>
  Math.max(0, Math.min(1, (time - p.start) / (p.end - p.start)));
export const ease = (t: number) => t * t * (3 - 2 * t);
export function motionAt(p: Phase, time: number) {
  if (!p.route)
    return { position: p.to, facing: 'back' as Facing, distance: 0, frame: 0 };
  const segments = p.route
    .slice(1)
    .map((to, i) => ({
      from: p.route![i],
      to,
      length: Math.hypot(
        (to.x - p.route![i].x) * 16.72,
        (to.y - p.route![i].y) * 9.41,
      ),
    }));
  const total = segments.reduce((s, p) => s + p.length, 0);
  if (total < 0.001)
    return { position: p.to, facing: 'back' as Facing, distance: 0, frame: 0 };
  const progress = phaseProgress(p, time);
  // A short acceleration/deceleration at the ends; constant pace through the route.
  const ramp = 0.08;
  const travel =
    progress < ramp
      ? (progress * progress) / (2 * ramp * (1 - ramp))
      : progress > 1 - ramp
        ? 1 - (1 - progress) ** 2 / (2 * ramp * (1 - ramp))
        : (progress - ramp / 2) / (1 - ramp);
  const distance = total * travel;
  let remaining = distance;
  let segment = segments[segments.length - 1];
  for (const [i, candidate] of segments.entries()) {
    segment = candidate;
    if (remaining <= candidate.length || i === segments.length - 1) break;
    remaining -= candidate.length;
  }
  const t = Math.min(1, remaining / segment.length);
  const dx = (segment.to.x - segment.from.x) * 16.72,
    dy = (segment.to.y - segment.from.y) * 9.41;
  const facing: Facing =
    Math.abs(dy) > Math.abs(dx) * 0.65
      ? dy < 0
        ? 'back'
        : 'front'
      : dx < 0
        ? 'left'
        : 'right';
  return {
    position: {
      x: segment.from.x + (segment.to.x - segment.from.x) * t,
      y: segment.from.y + (segment.to.y - segment.from.y) * t,
    },
    facing,
    distance,
    frame: Math.floor(distance / 21) % 4,
  };
}
