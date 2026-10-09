"use client";

import { useSyncExternalStore } from "react";
import type { MarketSnapshot, MarketStore } from "@/lib/marketStore";

export function useMarket(store: MarketStore): MarketSnapshot {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
