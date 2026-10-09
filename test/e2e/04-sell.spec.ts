import { test, expect } from "@playwright/test";
import { apiTrade, getPortfolio, headerCash, openApp } from "./helpers";

const TICKER = "JPM";

test.describe("sell", () => {
  test.beforeEach(async ({ request }) => {
    // Hold at least 3 shares to sell from.
    await apiTrade(request, TICKER, "buy", 3);
  });

  test("partial sell raises cash and reduces the position; full sell removes it", async ({ page, request }) => {
    await openApp(page);
    const row = page.getByTestId(`position-row-${TICKER}`);
    await expect(row).toBeVisible();
    const held = (await getPortfolio(request)).positions.find((p) => p.ticker === TICKER)!.quantity;
    const cashBefore = await headerCash(page);

    // Partial sell.
    await page.getByTestId("trade-ticker").fill(TICKER);
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("trade-sell").click();

    await expect.poll(() => headerCash(page)).toBeGreaterThan(cashBefore);
    await expect(row).toBeVisible();
    await expect
      .poll(async () => (await getPortfolio(request)).positions.find((p) => p.ticker === TICKER)?.quantity)
      .toBeCloseTo(held - 1, 4);

    // Sell the rest: the row disappears.
    const cashMid = await headerCash(page);
    await page.getByTestId("trade-ticker").fill(TICKER);
    await page.getByTestId("trade-quantity").fill(String(held - 1));
    await page.getByTestId("trade-sell").click();

    await expect(row).toHaveCount(0);
    await expect.poll(() => headerCash(page)).toBeGreaterThan(cashMid);
    expect((await getPortfolio(request)).positions.map((p) => p.ticker)).not.toContain(TICKER);
    await expect(page.getByTestId("trade-error")).toBeHidden();
  });

  test("selling more than held shows an inline error", async ({ page, request }) => {
    await openApp(page);
    const held = (await getPortfolio(request)).positions.find((p) => p.ticker === TICKER)!.quantity;

    await page.getByTestId("trade-ticker").fill(TICKER);
    await page.getByTestId("trade-quantity").fill(String(held + 100));
    await page.getByTestId("trade-sell").click();

    await expect(page.getByTestId("trade-error")).toContainText("Insufficient shares");
    expect((await getPortfolio(request)).positions.find((p) => p.ticker === TICKER)?.quantity).toBeCloseTo(held, 4);
  });
});
