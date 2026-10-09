import { vi } from "vitest";
import type { PriceUpdate } from "@/lib/types";

export function priceUpdate(ticker: string, price: number, extra: Partial<PriceUpdate> = {}): PriceUpdate {
  return {
    ticker,
    price,
    previous_price: price,
    timestamp: 1760000000,
    change: 0,
    change_percent: 0,
    direction: "flat",
    session_open: price,
    session_change_percent: 0,
    ...extra,
  };
}

/** Minimal EventSource stand-in; tests push frames with `emit`. */
export class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }
  fail(state = FakeEventSource.CONNECTING) {
    this.readyState = state;
    this.onerror?.();
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
  static latest() {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }
}

export function mockChartModule() {
  const series = { setData: vi.fn(), update: vi.fn(), applyOptions: vi.fn() };
  const chart = {
    addAreaSeries: vi.fn(() => series),
    addBaselineSeries: vi.fn(() => series),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    remove: vi.fn(),
  };
  return {
    createChart: vi.fn(() => chart),
    ColorType: { Solid: "solid" },
    CrosshairMode: { Magnet: 1 },
  };
}

type Handler = (init: RequestInit | undefined, path: string) => { status?: number; body?: unknown };

/** Routes `fetch` by "METHOD path" (e.g. "GET /api/watchlist") to handlers. */
export function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/^https?:\/\/[^/]+/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    const handler = routes[`${method} ${path}`];
    if (!handler) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 500 });
    const { status = 200, body } = handler(init, path);
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
