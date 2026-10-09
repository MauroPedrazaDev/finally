import { test, expect } from "@playwright/test";
import { getPortfolio } from "./helpers";

// PLAN §9 shapes and status codes, exercised against the running container.
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

test.describe("API contract", () => {
  test("GET /api/portfolio shape", async ({ request }) => {
    const p = await getPortfolio(request);
    expect(typeof p.cash_balance).toBe("number");
    expect(typeof p.total_value).toBe("number");
    expect(typeof p.unrealized_pnl).toBe("number");
    const tickers = p.positions.map((x) => x.ticker);
    expect(tickers).toEqual([...tickers].sort());
    for (const pos of p.positions) {
      expect(Object.keys(pos).sort()).toEqual(
        ["avg_cost", "current_price", "market_value", "quantity", "ticker", "unrealized_pnl", "unrealized_pnl_percent"],
      );
    }
  });

  test("trade: success shape and error codes", async ({ request }) => {
    const ok = await request.post("/api/portfolio/trade", { data: { ticker: "v", quantity: 1, side: "buy" } });
    expect(ok.status()).toBe(200);
    const body = await ok.json();
    expect(body).toMatchObject({ ticker: "V", side: "buy", quantity: 1 });
    expect(body.price).toBeGreaterThan(0);
    expect(typeof body.cash_balance).toBe("number");
    expect(body.executed_at).toMatch(ISO_UTC);

    const post = (data: object) => request.post("/api/portfolio/trade", { data });
    expect((await post({ ticker: "V", quantity: 0, side: "buy" })).status()).toBe(422);
    expect((await post({ ticker: "V", quantity: -1, side: "buy" })).status()).toBe(422);
    expect((await post({ ticker: "V", quantity: 1, side: "hold" })).status()).toBe(422);

    const tiny = await post({ ticker: "V", quantity: 0.00001, side: "buy" });
    expect(tiny.status()).toBe(400);
    expect((await tiny.json()).detail).toBe("Quantity too small");

    const badFormat = await post({ ticker: "BRK.B", quantity: 1, side: "buy" });
    expect(badFormat.status()).toBe(400);

    const broke = await post({ ticker: "V", quantity: 10_000_000, side: "buy" });
    expect(broke.status()).toBe(400);
    expect((await broke.json()).detail).toMatch(/^Insufficient cash: need \$[\d,.]+, have \$[\d,.]+$/);

    const oversell = await post({ ticker: "V", quantity: 10_000_000, side: "sell" });
    expect(oversell.status()).toBe(400);
    expect((await oversell.json()).detail).toMatch(/^Insufficient shares: have [\d.]+ V$/);
  });

  test("GET /api/portfolio/history shape", async ({ request }) => {
    const res = await request.get("/api/portfolio/history");
    expect(res.status()).toBe(200);
    const history = await res.json();
    expect(history.length).toBeGreaterThanOrEqual(1);
    expect(history.length).toBeLessThanOrEqual(500);
    for (const point of history) {
      expect(point.recorded_at).toMatch(ISO_UTC);
      expect(typeof point.total_value).toBe("number");
    }
    const times = history.map((h: { recorded_at: string }) => h.recorded_at);
    expect(times).toEqual([...times].sort());
  });

  test("watchlist: add 201, duplicate 200, remove 204, missing 404", async ({ request }) => {
    const ticker = "SNOW";
    await request.delete(`/api/watchlist/${ticker}`);

    const created = await request.post("/api/watchlist", { data: { ticker: ticker.toLowerCase() } });
    expect(created.status()).toBe(201);
    const item = await created.json();
    expect(item.ticker).toBe(ticker);
    for (const key of ["price", "previous_price", "direction", "session_open", "session_change_percent"]) {
      expect(item).toHaveProperty(key);
    }

    const dup = await request.post("/api/watchlist", { data: { ticker } });
    expect(dup.status()).toBe(200);

    const list = await (await request.get("/api/watchlist")).json();
    expect(list.filter((x: { ticker: string }) => x.ticker === ticker)).toHaveLength(1);
    expect(list[list.length - 1].ticker).toBe(ticker); // ordered by added_at

    expect((await request.delete(`/api/watchlist/${ticker}`)).status()).toBe(204);
    expect((await request.delete(`/api/watchlist/${ticker}`)).status()).toBe(404);
    expect((await request.post("/api/watchlist", { data: { ticker: "TOOLONG" } })).status()).toBe(400);
    expect((await request.post("/api/watchlist", { data: {} })).status()).toBe(422);
  });

  test("removing a held ticker from the watchlist keeps it priced", async ({ request }) => {
    const ticker = "AMD";
    await request.post("/api/portfolio/trade", { data: { ticker, quantity: 1, side: "buy" } });
    expect((await request.delete(`/api/watchlist/${ticker}`)).status()).toBe(204);

    const pos = (await getPortfolio(request)).positions.find((p) => p.ticker === ticker);
    expect(pos).toBeDefined();
    expect(pos!.current_price).not.toBeNull();

    // Clean up: selling the last share is allowed and the position disappears.
    const sell = await request.post("/api/portfolio/trade", { data: { ticker, quantity: pos!.quantity, side: "sell" } });
    expect(sell.status()).toBe(200);
    expect((await getPortfolio(request)).positions.map((p) => p.ticker)).not.toContain(ticker);
  });

  test("chat: GET history shape and POST response shape", async ({ request }) => {
    const post = await request.post("/api/chat", { data: { message: "hello there" } });
    expect(post.status()).toBe(200);
    const reply = await post.json();
    expect(reply).toEqual({ message: "Mock response: how can I help?", actions: [] });

    const history = await (await request.get("/api/chat")).json();
    expect(history.length).toBeLessThanOrEqual(50);
    const [user, assistant] = history.slice(-2);
    expect(user).toMatchObject({ role: "user", message: "hello there", actions: null });
    expect(assistant).toMatchObject({ role: "assistant", message: reply.message, actions: [] });
    expect(user.created_at).toMatch(ISO_UTC);
  });

  test("SSE stream sends retry and a full snapshot", async ({ request }) => {
    // Read the first chunk of the stream via fetch in Node.
    const base = test.info().project.use.baseURL!;
    const controller = new AbortController();
    const res = await fetch(`${base}/api/stream/prices`, { signal: controller.signal });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/event-stream");
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let text = "";
    const deadline = Date.now() + 10_000;
    while (!text.includes("data:") || !text.slice(text.indexOf("data:")).includes("\n\n")) {
      if (Date.now() > deadline) break;
      const { value, done } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
    }
    controller.abort();

    expect(text).toMatch(/retry: ?1000/);
    const dataLine = text.split("\n").find((l) => l.startsWith("data:"))!;
    const payload = JSON.parse(dataLine.slice(5).trim());
    const watchlist = (await (await request.get("/api/watchlist")).json()).map((x: { ticker: string }) => x.ticker);
    for (const t of watchlist) expect(Object.keys(payload)).toContain(t);
    const aapl = payload.AAPL;
    for (const key of [
      "ticker", "price", "previous_price", "timestamp", "change", "change_percent",
      "direction", "session_open", "session_change_percent",
    ]) {
      expect(aapl).toHaveProperty(key);
    }
    expect(typeof aapl.timestamp).toBe("number");
  });
});
