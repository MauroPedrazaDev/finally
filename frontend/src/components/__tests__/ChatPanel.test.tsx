import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "@/lib/types";
import { ChatPanel } from "../ChatPanel";

const messages: ChatMessage[] = [
  { role: "user", message: "buy 10 AAPL and watch PYPL", actions: null, created_at: "2026-10-07T14:03:10Z" },
  {
    role: "assistant",
    message: "Buying 10 AAPL.\n\n⚠ 1 action failed — see details below.",
    actions: [
      { type: "trade", ticker: "AAPL", side: "buy", quantity: 10, price: 190.5, status: "executed", error: null },
      { type: "watchlist", ticker: "PYPL", action: "add", status: "failed", error: "Unknown ticker: PYPL" },
    ],
    created_at: "2026-10-07T14:03:11Z",
  },
];

const base = { error: null, onSend: vi.fn(), collapsed: false, onToggle: vi.fn() };

describe("ChatPanel", () => {
  it("renders messages as plain text with action chips", () => {
    render(<ChatPanel {...base} messages={messages} loading={false} />);
    const items = screen.getAllByTestId("chat-message");
    expect(items.map((m) => m.dataset.role)).toEqual(["user", "assistant"]);
    const chips = screen.getAllByTestId("action-chip");
    expect(chips[0]).toHaveAttribute("data-status", "executed");
    expect(chips[0]).toHaveTextContent("Buy 10 AAPL @ 190.50");
    expect(chips[1]).toHaveAttribute("data-status", "failed");
    expect(chips[1]).toHaveTextContent("Unknown ticker: PYPL");
  });

  it("shows a loading indicator and blocks sending while waiting", () => {
    render(<ChatPanel {...base} messages={[]} loading />);
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-send")).toBeDisabled();
  });

  it("sends on Enter and clears the input", () => {
    const onSend = vi.fn();
    render(<ChatPanel {...base} onSend={onSend} messages={[]} loading={false} />);
    const input = screen.getByTestId("chat-input");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(input).toHaveValue("");
  });
});
