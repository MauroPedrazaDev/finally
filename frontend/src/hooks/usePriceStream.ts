"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";
import {
  deriveStatus,
  RECREATE_AFTER_CLOSED_MS,
  type ConnectionStatus,
} from "@/lib/connection";
import type { MarketStore } from "@/lib/marketStore";
import type { PriceEvent } from "@/lib/types";

const STATUS_POLL_MS = 500;

/**
 * Connects to /api/stream/prices, feeds events into the store and reports the
 * connection status (PLAN §11). The browser retries CONNECTING on its own; if the
 * EventSource reaches CLOSED, a new one is created after 5 seconds.
 */
export function usePriceStream(store: MarketStore): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      setStatus("disconnected");
      return;
    }
    let es: EventSource | null = null;
    let connectingSince: number | null = null;
    let recreateTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const refresh = () => {
      if (!es) {
        setStatus("disconnected");
        return;
      }
      const state = es.readyState;
      // Measures time since the stream was last OPEN, so a recreated EventSource
      // that is still failing stays red instead of flipping back to yellow.
      if (state === EventSource.OPEN) connectingSince = null;
      else connectingSince ??= Date.now();
      setStatus(deriveStatus(state, connectingSince, Date.now()));
      if (state === EventSource.CLOSED && !recreateTimer) {
        es.close();
        es = null;
        recreateTimer = setTimeout(() => {
          recreateTimer = null;
          if (!disposed) connect();
        }, RECREATE_AFTER_CLOSED_MS);
      }
    };

    const connect = () => {
      connectingSince ??= Date.now();
      const source = new EventSource(apiUrl("/api/stream/prices"));
      es = source;
      source.onopen = refresh;
      source.onerror = refresh;
      source.onmessage = (ev: MessageEvent<string>) => {
        try {
          store.applyEvent(JSON.parse(ev.data) as PriceEvent, Date.now());
        } catch {
          // Ignore malformed frames; the next event carries the full set again.
        }
      };
      refresh();
    };

    connect();
    const poll = setInterval(refresh, STATUS_POLL_MS);
    return () => {
      disposed = true;
      clearInterval(poll);
      if (recreateTimer) clearTimeout(recreateTimer);
      es?.close();
    };
  }, [store]);

  return status;
}
