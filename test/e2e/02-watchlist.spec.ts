import { test, expect } from "@playwright/test";
import { getWatchlist, openApp } from "./helpers";

const TICKER = "PYPL";

test.describe("watchlist", () => {
  test.beforeEach(async ({ request }) => {
    if ((await getWatchlist(request)).includes(TICKER)) {
      expect((await request.delete(`/api/watchlist/${TICKER}`)).status()).toBe(204);
    }
  });

  test("add and remove a ticker", async ({ page, request }) => {
    await openApp(page);
    const rows = page.locator('[data-testid^="watchlist-row-"]');
    const before = await rows.count();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toHaveCount(0);

    // Add (lowercase input is normalized by the backend).
    await page.getByTestId("add-ticker-input").fill(TICKER.toLowerCase());
    await page.getByTestId("add-ticker-button").click();

    const row = page.getByTestId(`watchlist-row-${TICKER}`);
    await expect(row).toBeVisible();
    await expect(rows).toHaveCount(before + 1);
    await expect(page.getByTestId(`price-${TICKER}`)).toHaveText(/\d/);
    expect(await getWatchlist(request)).toContain(TICKER);

    // Survives a reload (rows come from the API).
    await page.reload();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toBeVisible();

    // Remove.
    await page.getByTestId(`remove-ticker-${TICKER}`).click();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toHaveCount(0);
    await expect(rows).toHaveCount(before);
    expect(await getWatchlist(request)).not.toContain(TICKER);
  });

  test("an invalid ticker is rejected", async ({ page }) => {
    await openApp(page);
    const rows = page.locator('[data-testid^="watchlist-row-"]');
    const before = await rows.count();

    await page.getByTestId("add-ticker-input").fill("BRK.B");
    await page.getByTestId("add-ticker-button").click();

    // Give the request time to come back, then check nothing was added.
    await page.waitForTimeout(1_000);
    await expect(rows).toHaveCount(before);
  });
});
