import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { priceUpdate } from "@/test/fakes";
import type { PriceUpdate, WatchlistItem } from "@/lib/types";
import { Watchlist } from "../Watchlist";

const item = (ticker: string, price: number | null = null): WatchlistItem => ({
  ticker,
  price,
  previous_price: price,
  direction: null,
  session_open: price,
  session_change_percent: price == null ? null : 0,
});

function setup(prices: Record<string, PriceUpdate>, items = [item("AAPL"), item("MSFT")]) {
  const props = {
    items,
    prices,
    getBuffer: () => [],
    selected: "AAPL",
    onSelect: vi.fn(),
    onAdd: vi.fn(async (): Promise<string | null> => null),
    onRemove: vi.fn(async (): Promise<string | null> => null),
  };
  const utils = render(<Watchlist {...props} />);
  return {
    props,
    rerender: (p: Record<string, PriceUpdate>) => utils.rerender(<Watchlist {...props} prices={p} />),
  };
}

describe("Watchlist", () => {
  it("renders rows from the API list, not from SSE keys", () => {
    setup({ AAPL: priceUpdate("AAPL", 190), HELD: priceUpdate("HELD", 50) });
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-MSFT")).toBeInTheDocument();
    expect(screen.queryByTestId("watchlist-row-HELD")).toBeNull();
  });

  it("shows session_change_percent in the Chg % column", () => {
    setup({ AAPL: priceUpdate("AAPL", 190.5, { session_change_percent: 0.263, change_percent: 9.99 }) });
    expect(screen.getByTestId("chg-AAPL")).toHaveTextContent("+0.26%");
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("190.50");
  });

  it("falls back to the API price when SSE has none", () => {
    setup({}, [item("AAPL", 189.25)]);
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("189.25");
  });

  it("flashes when the price differs from the last rendered one, not on identical events", () => {
    vi.useFakeTimers();
    const { rerender } = setup({ AAPL: priceUpdate("AAPL", 190) });
    expect(screen.getByTestId("price-AAPL")).not.toHaveAttribute("data-flash");

    // Payload says "down", but the price rose vs. what we rendered: green.
    rerender({ AAPL: priceUpdate("AAPL", 191, { direction: "down" }) });
    expect(screen.getByTestId("price-AAPL")).toHaveAttribute("data-flash", "up");
    expect(screen.getByTestId("price-AAPL")).toHaveClass("flash-up");

    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByTestId("price-AAPL")).not.toHaveAttribute("data-flash");

    // Same price in a new event (direction "up"): no flash.
    rerender({ AAPL: priceUpdate("AAPL", 191, { direction: "up" }) });
    expect(screen.getByTestId("price-AAPL")).not.toHaveAttribute("data-flash");

    rerender({ AAPL: priceUpdate("AAPL", 189) });
    expect(screen.getByTestId("price-AAPL")).toHaveAttribute("data-flash", "down");
    vi.useRealTimers();
  });

  it("adds a ticker (uppercased) and shows errors inline", async () => {
    const { props } = setup({});
    props.onAdd.mockResolvedValueOnce("Unknown ticker: ZZZZ");
    fireEvent.change(screen.getByTestId("add-ticker-input"), { target: { value: "zzzz" } });
    fireEvent.click(screen.getByTestId("add-ticker-button"));
    expect(props.onAdd).toHaveBeenCalledWith("ZZZZ");
    expect(await screen.findByTestId("watchlist-error")).toHaveTextContent("Unknown ticker: ZZZZ");
  });

  it("removes a ticker without selecting the row", async () => {
    const { props } = setup({});
    fireEvent.click(screen.getByTestId("remove-ticker-MSFT"));
    await waitFor(() => expect(props.onRemove).toHaveBeenCalledWith("MSFT"));
    expect(props.onSelect).not.toHaveBeenCalled();
  });
});
