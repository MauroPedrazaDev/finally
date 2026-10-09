"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { flashDirection, type Flash } from "@/lib/flash";
import { fmtPercent, fmtPrice, toneClass } from "@/lib/format";
import type { Point } from "@/lib/priceBuffer";
import type { PriceUpdate, WatchlistItem } from "@/lib/types";
import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";

interface WatchlistProps {
  /** Rows come from GET /api/watchlist; SSE only supplies prices (PLAN §11). */
  items: WatchlistItem[];
  prices: Record<string, PriceUpdate>;
  getBuffer: (ticker: string) => Point[];
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<string | null>;
  onRemove: (ticker: string) => Promise<string | null>;
}

export function Watchlist({ items, prices, getBuffer, selected, onSelect, onAdd, onRemove }: WatchlistProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker || busy) return;
    setBusy(true);
    const err = await onAdd(ticker);
    setBusy(false);
    setError(err);
    if (!err) setDraft("");
  };

  const remove = async (ticker: string) => {
    setError(await onRemove(ticker));
  };

  return (
    <Panel
      title="Watchlist"
      aside={<span className="num text-[11px] text-fg-dim">{items.length}</span>}
      testId="watchlist"
      bodyClassName="flex flex-col"
    >
      <div className="grid grid-cols-[1fr_76px_64px_76px_18px] items-center gap-x-2 border-b border-line px-2.5 py-1 text-[10.5px] text-fg-dim">
        <span>Symbol</span>
        <span className="text-right">Last</span>
        <span className="text-right">Chg %</span>
        <span className="text-right">Since load</span>
        <span />
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {items.map((item) => (
          <WatchlistRow
            key={item.ticker}
            item={item}
            live={prices[item.ticker]}
            points={getBuffer(item.ticker)}
            selected={item.ticker === selected}
            onSelect={onSelect}
            onRemove={remove}
          />
        ))}
        {items.length === 0 && (
          <li className="px-3 py-6 text-center text-fg-dim">Add a ticker below to start watching it.</li>
        )}
      </ul>
      <form onSubmit={submit} className="shrink-0 border-t border-line p-2">
        <div className="flex gap-1.5">
          <input
            data-testid="add-ticker-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="Ticker, e.g. PYPL"
            maxLength={5}
            aria-label="Ticker to add"
            className="num min-w-0 flex-1 border border-line bg-ink-900 px-2 py-1 text-[12px] uppercase text-fg placeholder:normal-case placeholder:text-fg-dim focus:border-primary focus:outline-none"
          />
          <button
            data-testid="add-ticker-button"
            type="submit"
            disabled={busy || !draft.trim()}
            className="border border-primary/60 bg-primary/15 px-3 py-1 text-[12px] font-medium text-primary hover:bg-primary/25 disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {error && (
          <p data-testid="watchlist-error" role="alert" className="mt-1.5 text-[11.5px] text-down">
            {error}
          </p>
        )}
      </form>
    </Panel>
  );
}

interface RowProps {
  item: WatchlistItem;
  live: PriceUpdate | undefined;
  points: Point[];
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

export function WatchlistRow({ item, live, points, selected, onSelect, onRemove }: RowProps) {
  const price = live?.price ?? item.price;
  const chg = live?.session_change_percent ?? item.session_change_percent;
  const flash = usePriceFlash(price);

  return (
    <li
      data-testid={`watchlist-row-${item.ticker}`}
      data-selected={selected || undefined}
      onClick={() => onSelect(item.ticker)}
      className={`group relative grid cursor-pointer grid-cols-[1fr_76px_64px_76px_18px] items-center gap-x-2 border-b border-line/60 px-2.5 py-[5px] ${
        selected ? "bg-ink-700" : "hover:bg-ink-800"
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-[3px] bg-accent" aria-hidden />}
      <button
        type="button"
        className="text-left font-cond text-[13.5px] font-semibold text-fg focus:outline-none"
        aria-label={`Show ${item.ticker} chart`}
      >
        {item.ticker}
      </button>
      <span
        key={flash.seq}
        data-testid={`price-${item.ticker}`}
        data-flash={flash.dir ?? undefined}
        className={`num -mx-1 px-1 text-right text-[12.5px] text-fg ${
          flash.dir === "up" ? "flash-up" : flash.dir === "down" ? "flash-down" : ""
        }`}
      >
        {fmtPrice(price)}
      </span>
      <span data-testid={`chg-${item.ticker}`} className={`num text-right text-[12px] ${toneClass(chg)}`}>
        {fmtPercent(chg)}
      </span>
      <span className="flex justify-end">
        <Sparkline points={points} />
      </span>
      <button
        type="button"
        data-testid={`remove-ticker-${item.ticker}`}
        aria-label={`Remove ${item.ticker} from watchlist`}
        title="Remove from watchlist"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(item.ticker);
        }}
        className="text-[14px] leading-none text-fg-dim opacity-40 hover:text-down group-hover:opacity-100 focus:opacity-100"
      >
        ×
      </button>
    </li>
  );
}

const FLASH_MS = 500;

/** Tracks the last rendered price and returns the active flash (cleared after ~500ms). */
export function usePriceFlash(price: number | null | undefined) {
  const last = useRef<number | null | undefined>(price);
  const [flash, setFlash] = useState<{ dir: Flash; seq: number }>({ dir: null, seq: 0 });

  useEffect(() => {
    const dir = flashDirection(last.current, price);
    if (price != null) last.current = price;
    if (!dir) return;
    setFlash((f) => ({ dir, seq: f.seq + 1 }));
    const t = setTimeout(() => setFlash((f) => ({ ...f, dir: null })), FLASH_MS);
    return () => clearTimeout(t);
  }, [price]);

  return flash;
}
