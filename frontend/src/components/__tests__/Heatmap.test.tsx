import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ValuedPosition } from "@/lib/valuation";
import { Heatmap } from "../Heatmap";

const pos = (ticker: string, mv: number, pnl: number): ValuedPosition => ({
  ticker,
  quantity: 1,
  avg_cost: mv - pnl,
  price: mv,
  priceSource: "live",
  market_value: mv,
  unrealized_pnl: pnl,
  unrealized_pnl_percent: (pnl / (mv - pnl)) * 100,
});

describe("Heatmap", () => {
  it("shows an empty state without positions", () => {
    render(<Heatmap positions={[]} size={{ width: 400, height: 200 }} />);
    expect(screen.getByTestId("heatmap")).toHaveTextContent("No positions yet");
  });

  it("renders one tile per position with its P&L sign", () => {
    render(<Heatmap positions={[pos("AAPL", 1100, 100), pos("MSFT", 380, -20)]} size={{ width: 400, height: 200 }} />);
    expect(screen.getByTestId("heatmap-tile-AAPL")).toHaveAttribute("data-pnl-sign", "positive");
    expect(screen.getByTestId("heatmap-tile-MSFT")).toHaveAttribute("data-pnl-sign", "negative");
  });
});
