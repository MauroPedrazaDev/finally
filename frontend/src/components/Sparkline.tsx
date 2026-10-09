import type { Point } from "@/lib/priceBuffer";

export function Sparkline({ points, width = 76, height = 22 }: { points: Point[]; width?: number; height?: number }) {
  if (points.length < 2) {
    return <svg width={width} height={height} aria-hidden className="block" />;
  }
  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
    if (p.value < min) min = p.value;
    if (p.value > max) max = p.value;
  }
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const d = points
    .map((p, i) => `${(i * step).toFixed(1)},${(height - 2 - ((p.value - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  const rising = points[points.length - 1].value >= points[0].value;
  return (
    <svg width={width} height={height} aria-hidden className="block">
      <polyline
        points={d}
        fill="none"
        stroke={rising ? "#26b36b" : "#e5484d"}
        strokeWidth={1.2}
        strokeLinejoin="round"
      />
    </svg>
  );
}
