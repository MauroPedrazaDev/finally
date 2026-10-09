import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarketStore } from "@/lib/marketStore";
import { FakeEventSource, priceUpdate } from "@/test/fakes";
import { usePriceStream } from "../usePriceStream";

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

describe("usePriceStream", () => {
  it("is green when OPEN and feeds events into the store", () => {
    const store = new MarketStore();
    const { result } = renderHook(() => usePriceStream(store));
    expect(result.current).toBe("reconnecting");
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().emit({ AAPL: priceUpdate("AAPL", 190) });
    });
    expect(result.current).toBe("connected");
    expect(store.getSnapshot().prices.AAPL.price).toBe(190);
  });

  it("turns red after 10s of CONNECTING", () => {
    const store = new MarketStore();
    const { result } = renderHook(() => usePriceStream(store));
    act(() => FakeEventSource.latest().fail());
    advance(9_000);
    expect(result.current).toBe("reconnecting");
    advance(2_000);
    expect(result.current).toBe("disconnected");
  });

  it("recreates a CLOSED EventSource after 5s and stays red until it opens again", () => {
    const store = new MarketStore();
    const { result } = renderHook(() => usePriceStream(store));
    act(() => FakeEventSource.latest().fail(FakeEventSource.CLOSED));
    expect(result.current).toBe("disconnected");
    expect(FakeEventSource.instances).toHaveLength(1);
    advance(5_100);
    expect(FakeEventSource.instances).toHaveLength(2);
    // The 10s clock runs from the last OPEN, not from the new EventSource.
    advance(5_500);
    expect(result.current).toBe("disconnected");
    act(() => FakeEventSource.latest().open());
    expect(result.current).toBe("connected");
  });
});
