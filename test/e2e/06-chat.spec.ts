import { test, expect } from "@playwright/test";
import { getPortfolio, getWatchlist, headerCash, openApp } from "./helpers";

// Requires LLM_MOCK=true (PLAN §10 mock mode).
test.describe("AI chat (mocked)", () => {
  test("'buy 1 AAPL' executes a trade, shows an executed chip, and survives a reload", async ({ page, request }) => {
    await openApp(page);
    const assistant = page.locator('[data-testid="chat-message"][data-role="assistant"]');
    const executed = page.locator('[data-testid="action-chip"][data-status="executed"]');
    const assistantBefore = await assistant.count();
    const executedBefore = await executed.count();
    const aaplBefore = (await getPortfolio(request)).positions.find((p) => p.ticker === "AAPL")?.quantity ?? 0;
    const cashBefore = await headerCash(page);

    await page.getByTestId("chat-input").fill("buy 1 AAPL");
    await page.getByTestId("chat-send").click();

    await expect(assistant).toHaveCount(assistantBefore + 1);
    await expect(assistant.last()).toContainText("Mock response");
    await expect(executed).toHaveCount(executedBefore + 1);
    // Chips are rendered inside their assistant message.
    await expect(
      assistant.last().locator('[data-testid="action-chip"][data-status="executed"]'),
    ).toContainText("AAPL");
    await expect(page.getByTestId("chat-loading")).toBeHidden();

    // The trade really happened and the UI refreshed the portfolio.
    const aaplAfter = (await getPortfolio(request)).positions.find((p) => p.ticker === "AAPL")?.quantity ?? 0;
    expect(aaplAfter).toBeCloseTo(aaplBefore + 1, 4);
    await expect.poll(() => headerCash(page)).toBeLessThan(cashBefore);
    await expect(page.getByTestId("position-row-AAPL")).toBeVisible();

    // History is restored on reload.
    await page.reload();
    await expect(page.getByTestId("chat-panel")).toBeVisible();
    await expect(
      page.locator('[data-testid="chat-message"][data-role="user"]', { hasText: "buy 1 AAPL" }).last(),
    ).toBeVisible();
    // (GET /api/chat returns the last 50 messages, so compare the tail, not counts.)
    await expect(assistant.last()).toContainText("Mock response");
    await expect(
      assistant.last().locator('[data-testid="action-chip"][data-status="executed"]'),
    ).toHaveCount(1);
  });

  test("a failed action shows a failed chip with its error", async ({ page }) => {
    await openApp(page);
    const failed = page.locator('[data-testid="action-chip"][data-status="failed"]');
    const failedBefore = await failed.count();

    await page.getByTestId("chat-input").fill("sell 100000 AAPL");
    await page.getByTestId("chat-send").click();

    await expect(failed).toHaveCount(failedBefore + 1);
    await expect(failed.last()).toContainText("Insufficient shares");
    await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText(
      /action.*failed/,
    );
  });

  test("multiple commands: watchlist change via chat", async ({ page, request }) => {
    const ticker = "UBER";
    if ((await getWatchlist(request)).includes(ticker)) {
      await request.delete(`/api/watchlist/${ticker}`);
    }
    await openApp(page);

    await page.getByTestId("chat-input").fill(`add ${ticker}`);
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();

    await page.getByTestId("chat-input").fill(`remove ${ticker}`);
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toHaveCount(0);
    expect(await getWatchlist(request)).not.toContain(ticker);
  });
});
