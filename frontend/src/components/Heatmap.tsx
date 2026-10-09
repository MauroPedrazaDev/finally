"use client";

import { Treemap } from "recharts";
import { useElementSize } from "@/hooks/useElementSize";
import { fmtPercent } from "@/lib/format";
import { buildTiles, type HeatTile } from "@/lib/heatmap";
import type { ValuedPosition } from "@/lib/valuation";
import { Panel } from "./Panel";

interface HeatmapProps {
  positions: ValuedPosition[];
  /** Fixed size for tests; otherwise the panel body is measured. */
  size?: { width: number; height: number };
}

export function Heatmap({ positions, size }: HeatmapProps) {
  const [ref, measured] = useElementSize<HTMLDivElement>();
  const { width, height } = size ?? measured;
  const tiles = buildTiles(positions);

  return (
    <Panel title="Positions heatmap" aside={<Legend />} bodyClassName="relative">
      <div ref={ref} data-testid="heatmap" data-tiles={tiles.length} className="absolute inset-0">
        {tiles.length === 0 ? (
          <div className="flex h-full items-center justify-center text-fg-dim">No positions yet</div>
        ) : (
          width > 0 &&
          height > 0 && (
            <Treemap
              width={width}
              height={height}
              data={tiles}
              dataKey="size"
              aspectRatio={4 / 3}
              isAnimationActive={false}
              content={<Tile />}
            />
          )
        )}
      </div>
    </Panel>
  );
}

type TileProps = Partial<HeatTile> & {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
};

function Tile({ x = 0, y = 0, width = 0, height = 0, depth, ticker, fill, sign, pnlPct, weight }: TileProps) {
  if (depth !== 1 || !ticker) return null;
  const showLabel = width > 34 && height > 18;
  const showDetail = width > 60 && height > 38;
  return (
    <g data-testid={`heatmap-tile-${ticker}`} data-pnl-sign={sign}>
      <title>{`${ticker}: ${fmtPercent(pnlPct)} P&L, ${((weight ?? 0) * 100).toFixed(1)}% of positions`}</title>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#0d1117" strokeWidth={2} />
      {showLabel && (
        <text
          x={x + 6}
          y={y + 16}
          fill="#f2f5f8"
          fontSize={12.5}
          fontWeight={600}
          fontFamily='"IBM Plex Sans Condensed", sans-serif'
        >
          {ticker}
        </text>
      )}
      {showDetail && (
        <text x={x + 6} y={y + 31} fill="rgba(242,245,248,0.82)" fontSize={11} fontFamily='"IBM Plex Mono", monospace'>
          {fmtPercent(pnlPct)}
        </text>
      )}
    </g>
  );
}

function Legend() {
  return (
    <span className="flex items-center gap-1.5 text-[10.5px] text-fg-dim">
      <span className="num">-10%</span>
      <span
        className="h-1.5 w-16"
        style={{ background: "linear-gradient(90deg, rgb(229,72,77), rgb(42,52,66), rgb(38,179,107))" }}
      />
      <span className="num">+10%</span>
    </span>
  );
}
