import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource, mockFetch, priceUpdate } from "@/test/fakes";
import type { ChatMessage, Portfolio, WatchlistItem } from "@/lib/types";
import { Terminal } from "../Terminal";

vi.mock("lightweight-charts", async () => (await import("@/test/fakes")).mockChartModule());

const wl = (ticker: string): WatchlistItem => ({
  ticker,
  price: null,
  previous_price: null,
  direction: null,
  session_open: null,
  session_change_percent: null,
});

let watchlist: WatchlistItem[];
let portfolio: Portfolio;
let chat: ChatMessage[];

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  watchlist = [wl("AAPL"), wl("MSFT")];
  portfolio = {
    cash_balance: 8000,
    total_value: 10000,
    unrealized_pnl: 0,
    positions: [
      // Held but not on the watchlist: no SSE price yet, valued at current_price.
      { ticker: "TSLA", quantity: 5, avg_cost: 200, current_price: 210, market_value: 1050, unrealized_pnl: 50, unrealized_pnl_percent: 5 },
      { ticker: "AAPL", quantity: 10, avg_cost: 100, current_price: 100, market_value: 1000, unrealized_pnl: 0, unrealized_pnl_percent: 0 },
    ],
  };
  chat = [{ role: "user", message: "earlier question", actions: null, created_at: "2026-10-07T14:00:00Z" }];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function installApi(extra: Parameters<typeof mockFetch>[0] = {}) {
  return mockFetch({
    "GET /api/watchlist": () => ({ body: watchlist }),
    "GET /api/portfolio": () => ({ body: portfolio }),
    "GET /api/portfolio/history": () => ({ body: [{ recorded_at: "2026-10-07T14:00:00Z", total_value: 10000 }] }),
    "GET /api/chat": () => ({ body: chat }),
    ...extra,
  });
}

describe("Terminal", () => {
  it("restores chat history and renders watchlist rows from the API", async () => {
    installApi();
    render(<Terminal />);
    expect(await screen.findByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-MSFT")).toBeInTheDocument();
    expect(await screen.findByText("earlier question")).toBeInTheDocument();
    expect(FakeEventSource.latest().url).toBe("/api/stream/prices");

    // The first ticker is selected; clicking another row moves the main chart to it.
    expect(screen.getByTestId("main-chart")).toHaveTextContent("AAPL");
    fireEvent.click(screen.getByTestId("watchlist-row-MSFT"));
    expect(screen.getByTestId("main-chart")).toHaveTextContent("MSFT");
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-ticker", "MSFT");
  });

  it("header, positions table and live prices agree, with the price fallback order", async () => {
    installApi();
    render(<Terminal />);
    await screen.findByTestId("position-row-TSLA");

    // Before SSE: AAPL at current_price 100, TSLA at 210 → 8000 + 1000 + 1050.
    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,050.00");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,000.00");

    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().emit({ AAPL: priceUpdate("AAPL", 110), MSFT: priceUpdate("MSFT", 400) });
    });
    // AAPL now valued at the SSE price: 8000 + 1100 + 1050.
    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,150.00");
    const aapl = within(screen.getByTestId("position-row-AAPL"));
    expect(aapl.getByText("$1,100.00")).toBeInTheDocument();
    expect(aapl.getByText("+$100.00")).toBeInTheDocument();
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  });

  it("adds and removes watchlist tickers and refetches", async () => {
    const fetchMock = installApi({
      "POST /api/watchlist": (init) => {
        const { ticker } = JSON.parse(String(init?.body));
        watchlist = [...watchlist, wl(ticker)];
        return { status: 201, body: wl(ticker) };
      },
      "DELETE /api/watchlist/MSFT": () => {
        watchlist = watchlist.filter((w) => w.ticker !== "MSFT");
        return { status: 204 };
      },
    });
    render(<Terminal />);
    await screen.findByTestId("watchlist-row-AAPL");

    fireEvent.change(screen.getByTestId("add-ticker-input"), { target: { value: "pypl" } });
    fireEvent.click(screen.getByTestId("add-ticker-button"));
    expect(await screen.findByTestId("watchlist-row-PYPL")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("remove-ticker-MSFT"));
    await waitFor(() => expect(screen.queryByTestId("watchlist-row-MSFT")).toBeNull());
    expect(fetchMock).toHaveBeenCalledWith("/api/watchlist/MSFT", expect.objectContaining({ method: "DELETE" }));
  });

  it("shows trade errors inline", async () => {
    installApi({
      "POST /api/portfolio/trade": () => ({ status: 400, body: { detail: "Insufficient cash: need $1905.00, have $500.00" } }),
    });
    render(<Terminal />);
    await screen.findByTestId("watchlist-row-AAPL");
    fireEvent.change(screen.getByTestId("trade-ticker"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("trade-quantity"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("trade-buy"));
    expect(await screen.findByTestId("trade-error")).toHaveTextContent("Insufficient cash: need $1905.00, have $500.00");
  });

  it("sends a chat message, shows loading, then the reply with chips, and refetches the portfolio", async () => {
    let resolveReply: () => void = () => {};
    const gate = new Promise<void>((r) => (resolveReply = r));
    const fetchMock = installApi();
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === "/api/chat" && init?.method === "POST") {
        await gate;
        return new Response(
          JSON.stringify({
            message: "Mock response: buy 1 AAPL",
            actions: [{ type: "trade", ticker: "AAPL", side: "buy", quantity: 1, price: 190, status: "executed", error: null }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return base(input, init);
    });

    render(<Terminal />);
    await screen.findByText("earlier question");
    const portfolioCalls = () => fetchMock.mock.calls.filter(([u]) => String(u) === "/api/portfolio").length;
    const before = portfolioCalls();

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "buy 1 AAPL" } });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("chat-loading")).toBeInTheDocument();

    resolveReply();
    expect(await screen.findByTestId("action-chip")).toHaveAttribute("data-status", "executed");
    expect(screen.queryByTestId("chat-loading")).toBeNull();
    await waitFor(() => expect(portfolioCalls()).toBeGreaterThan(before));
  });
});
