import { test, expect } from "@playwright/test";
import { DEFAULT_TICKERS, getPortfolio, headerCash, openApp, parseMoney } from "./helpers";

// Runs first, against a fresh database (tmpfs in the compose stack).
test.describe("fresh start", () => {
  test("API reports the seeded state", async ({ request }) => {
    const health = await request.get("/api/health");
    expect(health.status()).toBe(200);
    expect(await health.json()).toEqual({ status: "ok" });

    const portfolio = await getPortfolio(request);
    expect(portfolio.cash_balance).toBe(10000);
    expect(portfolio.positions).toEqual([]);
  });

  test("shows the default watchlist, $10k cash, streaming prices and an initial P&L point", async ({ page }) => {
    await openApp(page);

    // Ten default tickers, rows from GET /api/watchlist.
    const rows = page.locator('[data-testid^="watchlist-row-"]');
    await expect(rows).toHaveCount(DEFAULT_TICKERS.length);
    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    }

    // $10,000 virtual cash; total value equals cash with no positions.
    await expect.poll(() => headerCash(page)).toBe(10000);
    await expect
      .poll(async () => parseMoney(await page.getByTestId("header-total-value").textContent()))
      .toBe(10000);

    // Prices are streaming: every row gets a price, and prices keep changing.
    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`price-${ticker}`)).toHaveText(/\d/);
      await expect(page.getByTestId(`chg-${ticker}`)).toHaveText(/\d/);
    }
    const snapshot = async () =>
      Promise.all(DEFAULT_TICKERS.map((t) => page.getByTestId(`price-${t}`).textContent()));
    const first = await snapshot();
    await expect.poll(async () => (await snapshot()).join("|"), { timeout: 10_000 }).not.toBe(first.join("|"));

    // The startup snapshot gives the P&L chart at least one point.
    await expect
      .poll(async () => Number(await page.getByTestId("pnl-chart").getAttribute("data-points")))
      .toBeGreaterThanOrEqual(1);

    // No positions yet: heatmap shows its empty state, positions table has no rows.
    await expect(page.getByTestId("heatmap")).toBeVisible();
    await expect(page.locator('[data-testid^="heatmap-tile-"]')).toHaveCount(0);
    await expect(page.locator('[data-testid^="position-row-"]')).toHaveCount(0);

    // Chat panel is ready.
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toBeVisible();
  });

  test("clicking a ticker shows the main chart", async ({ page }) => {
    await openApp(page);
    await page.getByTestId("watchlist-row-MSFT").click();
    await expect(page.getByTestId("main-chart")).toBeVisible();
    const chart = page.getByTestId("main-chart");
    await expect(chart).toHaveAttribute("data-ticker", "MSFT");
    // The chart fills from the since-page-load SSE buffer.
    await expect.poll(async () => Number(await chart.getAttribute("data-points"))).toBeGreaterThanOrEqual(2);
  });
});
