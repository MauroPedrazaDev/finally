import { test, expect } from "@playwright/test";
import { getPortfolio, getWatchlist, headerCash, openApp } from "./helpers";

test.describe("buy", () => {
  test("buying shares lowers cash and shows the position", async ({ page, request }) => {
    await openApp(page);
    const cashBefore = await headerCash(page);
    const qtyBefore = (await getPortfolio(request)).positions.find((p) => p.ticker === "AAPL")?.quantity ?? 0;

    await page.getByTestId("trade-ticker").fill("AAPL");
    await page.getByTestId("trade-quantity").fill("2");
    await page.getByTestId("trade-buy").click();

    await expect.poll(() => headerCash(page)).toBeLessThan(cashBefore);
    const row = page.getByTestId("position-row-AAPL");
    await expect(row).toBeVisible();
    await expect(page.getByTestId("trade-error")).toBeHidden();

    const portfolio = await getPortfolio(request);
    const position = portfolio.positions.find((p) => p.ticker === "AAPL");
    expect(position?.quantity).toBeCloseTo(qtyBefore + 2, 4);
    expect(portfolio.cash_balance).toBeLessThan(cashBefore);
    // The UI shows the same cash as the API (both rounded to cents).
    await expect.poll(() => headerCash(page)).toBeCloseTo(portfolio.cash_balance, 2);
  });

  test("buying an unwatched ticker adds it to the watchlist", async ({ page, request }) => {
    const ticker = "ORCL";
    if ((await getWatchlist(request)).includes(ticker)) {
      await request.delete(`/api/watchlist/${ticker}`);
    }
    await openApp(page);
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toHaveCount(0);

    await page.getByTestId("trade-ticker").fill(ticker);
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId(`position-row-${ticker}`)).toBeVisible();
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    expect(await getWatchlist(request)).toContain(ticker);
  });

  test("buying with insufficient cash shows an inline error", async ({ page }) => {
    await openApp(page);
    const cashBefore = await headerCash(page);

    await page.getByTestId("trade-ticker").fill("NVDA");
    await page.getByTestId("trade-quantity").fill("1000000");
    await page.getByTestId("trade-buy").click();

    await expect(page.getByTestId("trade-error")).toContainText("Insufficient cash");
    expect(await headerCash(page)).toBe(cashBefore);
  });
});
