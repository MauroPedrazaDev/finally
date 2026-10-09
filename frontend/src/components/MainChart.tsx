"use client";

import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { baseChartOptions, toChartTime } from "@/lib/chartTheme";
import { fmtPercent, fmtPrice, toneClass } from "@/lib/format";
import { BUFFER_CAP, type Point } from "@/lib/priceBuffer";
import type { PriceUpdate } from "@/lib/types";
import { Panel } from "./Panel";

interface MainChartProps {
  ticker: string | null;
  /** The shared since-page-load buffer for `ticker` (mutated in place by the store). */
  points: Point[];
  /** Store version; bumps on every SSE event. */
  version: number;
  live: PriceUpdate | undefined;
}

export function MainChart({ ticker, points, version, live }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const fed = useRef({ ticker: null as string | null, lastTime: -1, count: 0 });

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, baseChartOptions);
    seriesRef.current = chart.addAreaSeries({
      lineColor: "#209dd7",
      lineWidth: 2,
      topColor: "rgba(32, 157, 215, 0.28)",
      bottomColor: "rgba(32, 157, 215, 0.02)",
      priceLineColor: "#ecad0a",
      priceLineStyle: 2,
      lastValueVisible: true,
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      fed.current = { ticker: null, lastTime: -1, count: 0 };
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const f = fed.current;
    // New ticker, or the chart drifted well past the buffer cap: reload from the buffer.
    if (f.ticker !== ticker || f.count > BUFFER_CAP + 60) {
      series.setData(points.map((p) => ({ time: toChartTime(p.time), value: p.value })));
      fed.current = { ticker, lastTime: points.at(-1)?.time ?? -1, count: points.length };
      chartRef.current?.timeScale().fitContent();
      return;
    }
    // Feed the latest bucket(s); update() replaces a point with the same time.
    for (const p of points) {
      if (p.time < f.lastTime) continue;
      series.update({ time: toChartTime(p.time), value: p.value });
      if (p.time > f.lastTime) f.count += 1;
      f.lastTime = p.time;
    }
  }, [ticker, points, version]);

  const chg = live?.session_change_percent;
  return (
    <Panel
      title={
        <span className="flex items-baseline gap-3">
          <span className="font-cond text-[14px] font-semibold text-accent">{ticker ?? "No ticker selected"}</span>
          <span className="num text-[13px] text-fg">{fmtPrice(live?.price)}</span>
          <span className={`num text-[12px] ${toneClass(chg)}`}>{fmtPercent(chg)}</span>
        </span>
      }
      aside={
        <span className="flex gap-3 text-[10.5px] text-fg-dim">
          <span>Since page load</span>
          {/* Lightweight Charts licence attribution (the in-chart logo is turned off). */}
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="hover:text-fg-muted">
            Charts by TradingView
          </a>
        </span>
      }
      bodyClassName="relative"
      testId="main-chart"
      data={{ "data-ticker": ticker ?? "", "data-points": points.length }}
    >
      <div ref={containerRef} className="absolute inset-0" />
      {points.length < 2 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-fg-dim">
          {ticker ? `Collecting ${ticker} prices…` : "Select a ticker in the watchlist"}
        </div>
      )}
    </Panel>
  );
}
