import { test, expect } from "@playwright/test";
import { openApp } from "./helpers";

// page.route only intercepts new requests, not the already-open stream, so the
// stream is blocked and the page reloaded: the client then has to recover by
// itself (EventSource retry / re-create) once the route is lifted.
test("connection status leaves green while the stream is blocked and recovers after", async ({ page }) => {
  await openApp(page);
  const status = page.getByTestId("connection-status");
  await expect(status).toHaveAttribute("data-status", "connected");

  const block = (route: import("@playwright/test").Route) => route.abort();
  await page.route("**/api/stream/prices", block);
  await page.reload();

  await expect(page.getByTestId("watchlist")).toBeVisible();
  await expect(status).not.toHaveAttribute("data-status", "connected");
  // Hold the block a few seconds and confirm it never claims to be connected.
  for (let i = 0; i < 6; i++) {
    await page.waitForTimeout(500);
    await expect(status).not.toHaveAttribute("data-status", "connected");
  }
  // Watchlist rows still render (they come from the REST API).
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();

  await page.unroute("**/api/stream/prices", block);
  // Browser retry is 1s; a CLOSED source is re-created after 5s.
  await expect(status).toHaveAttribute("data-status", "connected", { timeout: 20_000 });
  await expect(page.getByTestId("price-AAPL")).toHaveText(/\d/);
});

test("a stream blocked for over 10 seconds shows disconnected", async ({ page }) => {
  await page.route("**/api/stream/prices", (route) => route.abort());
  await page.goto("/");
  const status = page.getByTestId("connection-status");
  await expect(status).toHaveAttribute("data-status", "disconnected", { timeout: 15_000 });

  await page.unrouteAll();
  await expect(status).toHaveAttribute("data-status", "connected", { timeout: 20_000 });
});
