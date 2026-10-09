import { test, expect } from "@playwright/test";
import { apiTrade, getPortfolio, openApp, parseMoney } from "./helpers";

function sign(pnl: number): "positive" | "negative" | "zero" {
  return pnl > 0 ? "positive" : pnl < 0 ? "negative" : "zero";
}

test.describe("portfolio visualization", () => {
  test.beforeAll(async ({ request }) => {
    // Make sure there are several positions to draw.
    await apiTrade(request, "MSFT", "buy", 1);
    await apiTrade(request, "TSLA", "buy", 1);
  });

  test("heatmap has a tile per position colored by P&L sign", async ({ page, request }) => {
    await openApp(page);
    await expect(page.getByTestId("heatmap")).toBeVisible();

    const positions = (await getPortfolio(request)).positions;
    expect(positions.length).toBeGreaterThanOrEqual(2);
    await expect(page.locator('[data-testid^="heatmap-tile-"]')).toHaveCount(positions.length);
    for (const p of positions) {
      await expect(page.getByTestId(`heatmap-tile-${p.ticker}`)).toBeVisible();
      await expect(page.getByTestId(`position-row-${p.ticker}`)).toBeVisible();
    }

    // Prices move between the API read and the UI render, so a P&L near zero can
    // flip sign; retry until one consistent read agrees for every position.
    await expect(async () => {
      const fresh = (await getPortfolio(request)).positions;
      const mismatches: string[] = [];
      for (const p of fresh) {
        const shown = await page.getByTestId(`heatmap-tile-${p.ticker}`).getAttribute("data-pnl-sign");
        expect(["positive", "negative", "zero"]).toContain(shown);
        // Within a few cents of zero the live client price may legitimately differ in sign.
        if (Math.abs(p.unrealized_pnl) < 0.05) continue;
        if (shown !== sign(p.unrealized_pnl)) {
          mismatches.push(`${p.ticker}: tile=${shown} api=${p.unrealized_pnl}`);
        }
      }
      expect(mismatches).toEqual([]);
    }).toPass({ timeout: 30_000, intervals: [250] });
  });

  test("header total is consistent with the portfolio", async ({ page, request }) => {
    await openApp(page);
    // Client-side valuation uses live SSE prices; allow a small drift vs the API.
    await expect(async () => {
      const api = await getPortfolio(request);
      const shown = parseMoney(await page.getByTestId("header-total-value").textContent());
      expect(Math.abs(shown - api.total_value) / api.total_value).toBeLessThan(0.01);
    }).toPass({ timeout: 15_000 });
  });

  test("P&L chart has data points", async ({ page, request }) => {
    const history = await (await request.get("/api/portfolio/history")).json();
    // Startup snapshot plus one per trade so far.
    expect(history.length).toBeGreaterThanOrEqual(2);

    await openApp(page);
    await expect
      .poll(async () => Number(await page.getByTestId("pnl-chart").getAttribute("data-points")))
      .toBeGreaterThanOrEqual(2);
  });
});
