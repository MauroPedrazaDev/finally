import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = [
  "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX",
];

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

/** Parse the first money-like number in a string: "Cash $10,000.00" -> 10000. */
export function parseMoney(text: string | null): number {
  const match = (text ?? "").replace(/−/g, "-").match(/-?\$?\s*-?[\d,]+(?:\.\d+)?/);
  if (!match) throw new Error(`No number in ${JSON.stringify(text)}`);
  const n = Number(match[0].replace(/[$,\s]/g, ""));
  if (Number.isNaN(n)) throw new Error(`Bad number in ${JSON.stringify(text)}`);
  return n;
}

/** Cash as shown in the header. */
export async function headerCash(page: Page): Promise<number> {
  return parseMoney(await page.getByTestId("header-cash").textContent());
}

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.get("/api/portfolio");
  expect(res.status()).toBe(200);
  return res.json();
}

export async function getWatchlist(request: APIRequestContext): Promise<string[]> {
  const res = await request.get("/api/watchlist");
  expect(res.status()).toBe(200);
  return (await res.json()).map((item: { ticker: string }) => item.ticker);
}

export async function apiTrade(
  request: APIRequestContext,
  ticker: string,
  side: "buy" | "sell",
  quantity: number,
) {
  const res = await request.post("/api/portfolio/trade", { data: { ticker, side, quantity } });
  expect(res.status(), await res.text()).toBe(200);
  return res.json();
}

/** Open the app and wait until the SSE stream is connected and prices have rendered. */
export async function openApp(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("watchlist")).toBeVisible();
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
}
