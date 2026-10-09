"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useMarket } from "@/hooks/useMarket";
import { usePriceStream } from "@/hooks/usePriceStream";
import { api, ApiError } from "@/lib/api";
import { MarketStore } from "@/lib/marketStore";
import type { ChatMessage, HistoryPoint, Portfolio, Side, WatchlistItem } from "@/lib/types";
import { computeValuation } from "@/lib/valuation";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { MainChart } from "./MainChart";
import { Panel } from "./Panel";
import { PnlChart } from "./PnlChart";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { Watchlist } from "./Watchlist";

const REFRESH_MS = 30_000;

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong. Try again.";
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function Terminal() {
  const [store] = useState(() => new MarketStore());
  const status = usePriceStream(store);
  const market = useMarket(store);

  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const loadWatchlist = useCallback(async () => {
    try {
      setWatchlist(await api.getWatchlist());
    } catch {
      // Keep the last good list; the next refresh retries.
    }
  }, []);
  const loadPortfolio = useCallback(async () => {
    try {
      setPortfolio(await api.getPortfolio());
    } catch {
      /* retried on the next refresh */
    }
  }, []);
  const loadHistory = useCallback(async () => {
    try {
      setHistory(await api.getHistory());
    } catch {
      /* retried on the next refresh */
    }
  }, []);
  const refreshAfterAction = useCallback(
    () => Promise.all([loadPortfolio(), loadWatchlist(), loadHistory()]),
    [loadPortfolio, loadWatchlist, loadHistory],
  );

  useEffect(() => {
    refreshAfterAction();
    api
      .getChat()
      .then(setChat)
      .catch(() => setChatError("Couldn't load the conversation history."));
    const t = setInterval(() => {
      loadPortfolio();
      loadHistory();
    }, REFRESH_MS);
    return () => clearInterval(t);
  }, [refreshAfterAction, loadPortfolio, loadHistory]);

  // Sparkline/chart buffers exist only for watchlist tickers.
  useEffect(() => {
    store.setWatched(watchlist.map((w) => w.ticker));
    setSelected((cur) => (cur && watchlist.some((w) => w.ticker === cur) ? cur : (watchlist[0]?.ticker ?? null)));
  }, [store, watchlist]);

  const livePrices = useMemo(() => {
    const out: Record<string, number> = {};
    for (const [t, u] of Object.entries(market.prices)) out[t] = u.price;
    return out;
  }, [market.prices]);
  const valuation = useMemo(() => computeValuation(portfolio, livePrices), [portfolio, livePrices]);

  const onTrade = useCallback(
    async (ticker: string, quantity: number, side: Side) => {
      try {
        await api.trade(ticker, quantity, side);
      } catch (err) {
        return errorText(err);
      }
      await refreshAfterAction();
      return null;
    },
    [refreshAfterAction],
  );

  const onAdd = useCallback(
    async (ticker: string) => {
      try {
        await api.addToWatchlist(ticker);
      } catch (err) {
        return errorText(err);
      }
      await loadWatchlist();
      return null;
    },
    [loadWatchlist],
  );

  const onRemove = useCallback(
    async (ticker: string) => {
      // Optimistic: drop the row immediately, then reconcile with the server.
      setWatchlist((w) => w.filter((x) => x.ticker !== ticker));
      let err: string | null = null;
      try {
        await api.removeFromWatchlist(ticker);
      } catch (e) {
        err = errorText(e);
      }
      await loadWatchlist();
      return err;
    },
    [loadWatchlist],
  );

  const onSend = useCallback(
    async (message: string) => {
      setChatError(null);
      setChat((c) => [...c, { role: "user", message, actions: null, created_at: nowIso() }]);
      setChatLoading(true);
      try {
        const reply = await api.sendChat(message);
        setChat((c) => [
          ...c,
          { role: "assistant", message: reply.message, actions: reply.actions ?? [], created_at: nowIso() },
        ]);
        if (reply.actions?.length) await refreshAfterAction();
      } catch (err) {
        setChatError(`Message not delivered: ${errorText(err)}`);
      } finally {
        setChatLoading(false);
      }
    },
    [refreshAfterAction],
  );

  const getBuffer = useCallback((t: string) => store.getBuffer(t), [store]);
  const positions = valuation?.positions ?? [];

  return (
    <div className="flex h-screen min-w-[1280px] flex-col overflow-hidden">
      <Header valuation={valuation} status={status} />
      <div className="flex min-h-0 flex-1">
        <main className="grid min-h-0 min-w-0 flex-1 grid-cols-[330px_minmax(0,1fr)] gap-1.5 p-1.5">
          <Watchlist
            items={watchlist}
            prices={market.prices}
            getBuffer={getBuffer}
            selected={selected}
            onSelect={setSelected}
            onAdd={onAdd}
            onRemove={onRemove}
          />
          <div className="grid min-h-0 min-w-0 grid-rows-[minmax(220px,1.15fr)_minmax(190px,0.85fr)_minmax(170px,0.8fr)] gap-1.5">
            <MainChart
              ticker={selected}
              points={selected ? store.getBuffer(selected) : []}
              version={market.version}
              live={selected ? market.prices[selected] : undefined}
            />
            <div className="grid min-h-0 grid-cols-2 gap-1.5">
              <Heatmap positions={positions} />
              <PnlChart history={history} />
            </div>
            <Panel
              title="Positions"
              aside={<span className="num text-[11px] text-fg-dim">{positions.length}</span>}
              bodyClassName="flex flex-col"
            >
              <TradeBar selected={selected} onTrade={onTrade} />
              <div className="min-h-0 flex-1 overflow-y-auto">
                <PositionsTable positions={positions} onSelect={(t) => watchlist.some((w) => w.ticker === t) && setSelected(t)} />
              </div>
            </Panel>
          </div>
        </main>
        <ChatPanel
          messages={chat}
          loading={chatLoading}
          error={chatError}
          onSend={onSend}
          collapsed={chatCollapsed}
          onToggle={() => setChatCollapsed((c) => !c)}
        />
      </div>
    </div>
  );
}
