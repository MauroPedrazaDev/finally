"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Side } from "@/lib/types";

interface TradeBarProps {
  /** Pre-fills the ticker when the selection changes. */
  selected: string | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<string | null>;
}

export function TradeBar({ selected, onTrade }: TradeBarProps) {
  const [ticker, setTicker] = useState(selected ?? "");
  const [qty, setQty] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<string | null>(null);
  const [busy, setBusy] = useState<Side | null>(null);

  useEffect(() => {
    if (selected) setTicker(selected);
  }, [selected]);

  const submit = async (side: Side, e?: FormEvent) => {
    e?.preventDefault();
    const t = ticker.trim().toUpperCase();
    const q = Number(qty);
    if (!t) return setError("Enter a ticker.");
    if (!qty.trim() || !Number.isFinite(q) || q <= 0) return setError("Enter a quantity greater than 0.");
    setBusy(side);
    setError(null);
    setLast(null);
    const err = await onTrade(t, q, side);
    setBusy(null);
    if (err) setError(err);
    else setLast(`${side === "buy" ? "Bought" : "Sold"} ${q} ${t}`);
  };

  return (
    <form
      onSubmit={(e) => submit("buy", e)}
      className="flex shrink-0 flex-wrap items-center gap-2 border-b border-line bg-ink-800/60 px-2.5 py-1.5"
    >
      <span className="font-cond text-[12px] font-semibold text-fg-muted">Market order</span>
      <input
        data-testid="trade-ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="Ticker"
        aria-label="Ticker"
        maxLength={5}
        className="num w-20 border border-line bg-ink-900 px-2 py-1 text-[12px] uppercase text-fg placeholder:normal-case placeholder:text-fg-dim focus:border-primary focus:outline-none"
      />
      <input
        data-testid="trade-quantity"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="Qty"
        aria-label="Quantity"
        inputMode="decimal"
        className="num w-20 border border-line bg-ink-900 px-2 py-1 text-[12px] text-fg placeholder:text-fg-dim focus:border-primary focus:outline-none"
      />
      <button
        data-testid="trade-buy"
        type="submit"
        disabled={busy != null}
        className="min-w-[56px] bg-up/85 px-3 py-1 text-[12px] font-semibold text-ink-950 hover:bg-up disabled:opacity-50"
      >
        {busy === "buy" ? "…" : "Buy"}
      </button>
      <button
        data-testid="trade-sell"
        type="button"
        disabled={busy != null}
        onClick={() => submit("sell")}
        className="min-w-[56px] bg-down/85 px-3 py-1 text-[12px] font-semibold text-white hover:bg-down disabled:opacity-50"
      >
        {busy === "sell" ? "…" : "Sell"}
      </button>
      {error && (
        <span data-testid="trade-error" role="alert" className="text-[11.5px] text-down">
          {error}
        </span>
      )}
      {!error && last && <span className="text-[11.5px] text-fg-muted">{last}</span>}
    </form>
  );
}
