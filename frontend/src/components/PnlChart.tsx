"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { baseChartOptions, toChartTime } from "@/lib/chartTheme";
import { fmtSignedMoney, toneClass } from "@/lib/format";
import { historyToPoints } from "@/lib/history";
import type { HistoryPoint } from "@/lib/types";
import { Panel } from "./Panel";

export function PnlChart({ history }: { history: HistoryPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Baseline"> | null>(null);
  const points = useMemo(() => historyToPoints(history), [history]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      ...baseChartOptions,
      timeScale: { ...baseChartOptions.timeScale, secondsVisible: false },
    });
    seriesRef.current = chart.addBaselineSeries({
      baseValue: { type: "price", price: 10000 },
      topLineColor: "#26b36b",
      topFillColor1: "rgba(38, 179, 107, 0.22)",
      topFillColor2: "rgba(38, 179, 107, 0.02)",
      bottomLineColor: "#e5484d",
      bottomFillColor1: "rgba(229, 72, 77, 0.02)",
      bottomFillColor2: "rgba(229, 72, 77, 0.22)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const base = points[0]?.value ?? 10000;
    series.applyOptions({ baseValue: { type: "price", price: base } });
    series.setData(points.map((p) => ({ time: toChartTime(p.time), value: p.value })));
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  const change = points.length ? points[points.length - 1].value - points[0].value : null;
  return (
    <Panel
      title="Portfolio value"
      aside={
        <span className="flex items-baseline gap-1.5 text-[10.5px] text-fg-dim">
          last 24h
          <span className={`num text-[11.5px] ${toneClass(change)}`}>{fmtSignedMoney(change)}</span>
        </span>
      }
      bodyClassName="relative"
    >
      <div ref={containerRef} data-testid="pnl-chart" data-points={points.length} className="absolute inset-0" />
      {points.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-fg-dim">
          No snapshots yet
        </div>
      )}
    </Panel>
  );
}
