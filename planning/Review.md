# Review of PLAN.md (post-revision)

Reviewer: Reviewer agent. Date: 2026-10-08.
Scope: `planning/PLAN.md` as currently on disk (the revised version, 14 sections), checked against the existing market data code in `backend/app/market/` and the backend tests.

**Overall:** The revision is a big improvement. Most earlier gaps are now closed: error shapes, response examples, trading rules, tracked-ticker semantics, mock-mode patterns, local dev/CORS, and the static mount order. The worked numbers in the examples check out (cash 8095 = 10000 − 10×190.5; total 10012.4; P&L % 0.65; SSE `change_percent` 0.042; `session_change_percent` 0.263).

What's left is mostly:
- **(a)** places where the plan describes an extension to the market module without fixing its API;
- **(b)** a few frontend/backend contract details that an implementer would still have to guess;
- **(c)** one real data-integrity problem caused by how the simulator seeds prices.

Severity legend: **HIGH** = likely bug or two agents building incompatible things. **MEDIUM** = an implementer has to guess, with visible consequences. **LOW** = polish or clarity.

---

## 1. Findings against the existing market data code

### 1.1 [HIGH] Simulator re-seeds prices on restart and re-add, causing large fake P&L jumps (§6 Simulator, §6 Tracked Tickers)
- `simulator.py:151`: `self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))`.
- **Unknown ticker held across restarts:** a held position in an unknown ticker (e.g. bought PYPL at $120) gets a **new random price ($50–300) on every server restart**. That instantly moves the portfolio value by potentially hundreds of percent. The P&L chart and heatmap show a jump that never "happened".
- **Known tickers:** these restart from their seed price, so they also jump, though less.
- **Re-added tickers:** a ticker removed from tracking and added back starts again from its seed or a fresh random price. The sparkline/main chart line breaks, and so does the "new session open" logic in §6 Session Open Price.
- **Suggested fix (pick one, and state it in §6):**
  - derive the seed price for unknown tickers deterministically from the ticker (e.g. a hash mapped into $50–300); and/or
  - on startup, seed held tickers from their last trade price (or `avg_cost`) read from the DB. This needs the lifespan to pass seed prices into `source.start()`, which is an interface change. Say so if you choose it.
- At minimum, the plan should acknowledge that simulator prices are not persisted, so P&L is discontinuous across restarts.

### 1.2 [HIGH] The Session Open extension is under-specified at the API level (§6 Session Open Price)
- `PriceUpdate` is a frozen dataclass and `to_dict()` is defined on it. So `session_open` must become a **field of `PriceUpdate`**, not just something `PriceCache` "stores". The plan says both, but doesn't say which object owns it.
- `PriceCache.update(ticker, price, timestamp=None)` has no way to receive a previous close from Massive. The plan needs to give the new signature, e.g. `update(ticker, price, timestamp=None, session_open=None)`, where an explicit value is used only for the first write.
- **Massive field:** say which snapshot field provides the previous close (presumably `snap.prev_day.close`; the archive doc says `day.previous_close`, which looks wrong). Also say what happens when it is 0 or missing.
- **Removal:** `remove()` must also drop the stored `session_open`, so a re-add gets a new one. This is implied but not stated as a cache requirement.
- **Recommendation:** add a short "Required changes to `backend/app/market/`" checklist with the exact signatures. Also name the owner (Backend agent or Market Data agent); §4 says "Backend/Market Data agents".

### 1.3 [HIGH] The Massive ticker-lookup extension has no defined interface (§8 Ticker existence, §4)
- §4 says the market module "needs the §8 ticker-lookup extension". The `MarketDataSource` ABC (`interface.py`) has no such method.
- **Questions the plan must answer:**
  - Is it a new abstract method, e.g. `async def validate_ticker(ticker) -> bool`, where the simulator returns `True` and Massive does a one-off `get_snapshot_ticker` plus a cache write? Or is it a Massive-only helper that the route layer calls after an `isinstance` check?
  - "Synchronous one-off lookup": the Massive `RESTClient` is blocking, so the lookup must run via `asyncio.to_thread`, like `_fetch_snapshots`. Say this, so nobody blocks the event loop.
  - The lookup must run **before** `BEGIN IMMEDIATE` (§8 Atomicity). Holding the SQLite write lock across a network call is a bug.
- **Rate limit:** free tier is 5 calls/min and polling every 15s uses 4/min. That leaves **one lookup per minute**. A second add within a minute gets a 429. The plan doesn't say what the user sees. Proposed: 400 `"Market data rate limit reached, try again shortly"`. Also consider defaulting the Massive poll interval to 20s when lookups are expected.
- **Free-tier access (question):** please verify that the snapshot endpoint is available on the free tier at all. Historically, Polygon's free "Basic" plan did not include snapshots.

### 1.4 [MEDIUM] Massive timestamp unit may be wrong (§6 SSE payload `timestamp`)
- `massive_client.py` divides `last_trade.timestamp` by 1000, assuming milliseconds. Polygon's snapshot `lastTrade.t` is documented as a **nanosecond** SIP timestamp.
- If it really is nanoseconds, the SSE `timestamp` will be in microseconds (around year 50,000). That breaks any frontend chart that uses `timestamp` as its x-axis.
- The existing tests mock milliseconds, so they would not catch this.
- **Recommendation:** verify against a live response. Separately, decide in §11 whether the frontend chart x-axis uses the payload `timestamp` or the client receive time. Client receive time is more robust and also handles 500 ms ticks (see 2.6).

### 1.5 [LOW] SSE removal and change detection
- `PriceCache.remove()` does not bump `version`. With Massive (15s polls), a removed ticker keeps appearing in SSE events until the next poll. Fix: bump `version` in `remove()`.
- `stream.py` decorates a **module-level** `router` inside `create_stream_router()`. Calling the factory twice (e.g. one app per test) registers `/prices` twice on the same router object. Fix: create the `APIRouter` inside the factory.
- If the cache is empty, the "first event after every (re)connect is a full snapshot" guarantee (§6) does not hold: nothing is sent until there is data. That's fine in practice, but the wording should say "the first event with data".

### 1.6 [LOW] Poll interval is "configurable" but not exposed
§6 says the Massive poll interval is configurable. `create_market_data_source()` has no way to pass it, and §5 defines no env var. Either add `MASSIVE_POLL_INTERVAL` (default 15) to §5 and the factory, or drop "configurable".

---

## 2. Frontend/backend contract gaps

### 2.1 [HIGH] The SSE ticker set is not the watchlist
- SSE carries **watchlist ∪ held tickers** (§6 Tracked Tickers). If the frontend renders the watchlist from SSE keys, removed-but-held tickers stay visible.
- **State explicitly:** the watchlist rows come from `GET /api/watchlist`, and SSE only supplies prices for them. Ticker removal from the stream is not a signal.
- Also say whether the frontend should drop sparkline buffers for tickers that disappear from the stream.

### 2.2 [MEDIUM] Flash trigger and direction semantics
- The simulator ticks every 500 ms and SSE samples every 500 ms, so ticks can be skipped or doubled. The payload's `previous_price` and `direction` are relative to the previous **cache** tick, not the previous **event the client saw**.
- **Specify:** flash on `price !== lastRenderedPrice`, colored by the comparison against that last rendered price. Do not flash on `direction` alone.
- **Note:** with the simulator, nearly every ticker changes every event. With a ~500 ms fade, the whole watchlist will flash constantly. Consider a shorter flash, or only flashing when the change is ≥ $0.01 after rounding (already guaranteed by the 2-dp rounding, but worth stating).

### 2.3 [MEDIUM] Positions table and heatmap: live or refetch?
§11 makes the header total live (SSE × positions). It does not say whether the **positions table** (current price, unrealized P&L, %) and the **heatmap** also recompute live from SSE, or only update on refetch of `/api/portfolio`. Without this, the header and the table will disagree between refetches. Recommend: compute all three client-side from the same SSE prices.

### 2.4 [MEDIUM] `GET /api/chat` item shape for user messages
- The plan gives only the assistant item shape: `{message, actions, role, created_at}`. User items are not specified. Presumably `{role: "user", message, actions: null, created_at}`.
- Note that the DB column is `content` while the API field is `message`. State the mapping explicitly.
- Also: is the system-generated "⚠ N action(s) failed" note persisted inside `content`? Is `actions` `[]` or `null` when an assistant reply has no actions?

### 2.5 [MEDIUM] Chat error paths not covered
§10 covers parse failures (retry once, then an apology) and a missing API key. It does not cover **LLM transport errors**: timeout, 401, 429, 5xx from OpenRouter.
- Proposed: return 200 with an assistant message like "The AI service is unavailable right now", no actions, and still persist the turn. Or return 502. Pick one.
- Also specify an LLM call timeout (e.g. 30s) so the loading indicator can't spin forever.

### 2.6 [MEDIUM] Lightweight Charts and sub-second ticks
- Lightweight Charts requires strictly increasing `time` values in **seconds**. At 500 ms ticks, two points can land in the same second, and `setData` will throw on duplicates or out-of-order times.
- **Specify:** bucket points per second, keeping the last price. Feed the chart with `series.update()`, which replaces a point with the same time.
- **Sparkline buffers:** a 500 ms cadence is 7,200 points per ticker per hour. Specify a ring-buffer cap (e.g. last 300–600 points) for both sparklines and the main chart.

### 2.7 [LOW] Error message text inconsistency
§8 says an unknown ticker is rejected with `"Unknown ticker: {ticker}"`. The §9 chat example shows `"No data for ticker PYPL"`. Pick one, because E2E and frontend tests may match on it.

### 2.8 [LOW] Chat example contradicts the system-prompt guidance
- The §9 example message says "Bought 10 AAPL. Adding PYPL failed." §10 tells the LLM to phrase actions as intentions ("Buying 10 AAPL…") because it cannot know the outcomes.
- The example also omits the system-appended failure note required by §10 step 7.
- Update the example to show the real composed output, e.g. `"Buying 10 AAPL and adding PYPL to your watchlist.\n\n⚠ 1 action failed — see details below."`

### 2.9 [LOW] Smaller contract details
- **"% change" column in the positions table (§2, §11):** presumably `unrealized_pnl_percent`. Use the API field name.
- **Ordering of `GET /api/watchlist` and `GET /api/portfolio` positions:** e.g. by `added_at` ascending / by ticker. Specify it.
- **Timestamp formats are mixed:** SSE uses Unix seconds (float), REST uses ISO strings. Fine, but state it once. Also note that Python `isoformat()` emits `+00:00`, not `Z`; the examples show `Z`.
- **Quantity validation:** is `quantity <= 0` a 400 (business rule) or a 422 (Pydantic `gt=0`)? Also, is the > 0 check done before or after rounding to 4 dp? `0.00001` rounds to 0.
- **Sell tolerance:** when `quantity` exceeds `held` by less than 1e-6, is the sold quantity clamped to `held`?
- **Header fallback:** when a position has no SSE price yet, the client-side total should use `current_price` from `/api/portfolio`, or `avg_cost`. State it.
- **Connection dot:** with `retry: 1000`, a dead server keeps `EventSource` in `CONNECTING` (yellow) indefinitely. `CLOSED` (red) only happens on HTTP errors or a wrong content type, and then the browser stops retrying. Say whether the frontend should reconnect manually after `CLOSED`, and whether to show red after N seconds stuck in yellow.

---

## 3. Backend internals an implementer would have to guess

### 3.1 [MEDIUM] Database path resolution and SQLite access pattern (§4, §7, §12)
- **Path:** locally the DB is `<root>/db/finally.db`; in Docker it is `/app/db/finally.db`. Nothing says how the backend decides. Recommend a `DB_PATH` env var with a sensible default (e.g. relative to the repo root), set explicitly in the Dockerfile. The same applies to the static directory (`StaticFiles(directory="static")` is relative to the CWD).
- **Driver and concurrency:** is it `sqlite3` with a connection per request, or `aiosqlite`? Should WAL mode be used? What busy timeout? The 30s snapshot task, trade requests and chat-driven trades all write concurrently, and `BEGIN IMMEDIATE` without a `busy_timeout` will raise "database is locked".
- **Seeding rule:** seed only when the `users_profile` row is missing. Otherwise a user who deliberately empties the watchlist gets it re-seeded on restart.

### 3.2 [MEDIUM] Lifespan ordering (§3 Background Task Lifecycle, §7 snapshots)
Specify the order:
1. init/seed the DB;
2. read the tracked tickers (watchlist ∪ positions);
3. `source.start(tickers)` (the simulator writes seed prices immediately; Massive does a first poll);
4. record the startup snapshot;
5. start the 30s snapshot task.

If the snapshot runs before step 3, positions are valued at `avg_cost`. Also: on first launch, "seed snapshot" and "startup snapshot" are two points within milliseconds of each other. Drop one or say it's intended.

### 3.3 [MEDIUM] Snapshot downsampling and retention (§9 history)
- "At most 500 points": over 24h at 30s that's 2,880 rows. Name the method, e.g. evenly spaced by index, always keeping the first and last point.
- Is the `portfolio_snapshots` table ever pruned? Growth is small (~1M rows/year), but say so.

### 3.4 [MEDIUM] LLM structured-output schema vs. strict JSON schema
- OpenAI-style `response_format: json_schema` with `strict: true` requires **every property to be required** and `additionalProperties: false`. Optional `trades`/`watchlist_changes` don't fit.
- **Recommendation:** make both arrays required (empty when unused). Use `side: enum["buy","sell"]`, `action: enum["add","remove"]`, `quantity: number > 0`. Define the Pydantic model once and reuse it for mock mode and validation.
- **Execution order:** "In order" is ambiguous across two arrays. Specify: watchlist changes first, then trades, or the other way round.
- **LLM context:** should the last-20-messages context include prior action results, so the LLM knows a trade failed? Recommended.

### 3.5 [LOW] Mock-mode edge cases (§10)
- Multiple commands in one message ("buy 1 AAPL and add PYPL"): first match only, or all matches?
- Are fractional quantities accepted ("buy 0.5 AAPL")?
- Does mock mode still persist messages to `chat_messages`? Presumably yes, but say so.

### 3.6 [LOW] Dependencies and Docker details
- `pyproject.toml` lacks `litellm` and `python-dotenv`. `rich` is a runtime dependency used only by the demo; move it to `dev`.
- Name the app entrypoint (e.g. `app.main:app`), the `uv sync --frozen --no-dev` flags, and the copy destination of the Next export (`frontend/out` → `/app/static`).
- `docker run --env-file .env` **fails if `.env` is missing**. Now that `OPENROUTER_API_KEY` is optional, the start scripts should create `.env` from `.env.example` (or omit `--env-file`) when it is absent. Otherwise the first-launch promise in §2 breaks. Note that `.env.example` and `db/.gitkeep` don't exist in the repo yet.
- Optional: a Docker `HEALTHCHECK` against `/api/health`. The slim image has no curl, so use Python.

### 3.7 [LOW] Ticker regex
`^[A-Z]{1,5}$` rejects share-class tickers such as `BRK.B`. That's fine for a demo, but it is a deliberate limitation. Note it so agents don't "fix" it inconsistently.

---

## 4. Testing

- **[MEDIUM] E2E isolation:** "Fresh start: $10k balance" only holds on a fresh DB. `docker-compose.test.yml` should use no volume (or a tmpfs), and tests must not depend on each other's state. Either order them carefully or add a test-only reset path. State which.
- **[LOW] Heatmap "correct colors":** prices are random, so the P&L sign isn't known in advance. Assert on the presence of a colored tile, or read the sign from the API and compare.
- **[LOW] SSE resilience:** specify how disconnection is simulated, e.g. Playwright `page.route` abort, or restarting the app container. `context.setOffline` does not reliably close an open `EventSource`.
- **Unit tests:** add backend tests for:
  - `PriceCache.remove` clearing `session_open`;
  - deterministic seeding (if adopted, see 1.1);
  - the rate-limited lookup path;
  - snapshot downsampling.

---

## 5. Internal consistency and wording

- §10: "There is an OPENROUTER_API_KEY in the .env file" contradicts §5, which makes it optional. Reword to "if present".
- §2 says "a browser opens"; §12 says the scripts open it best-effort. Fine, but §2 could say "the start script opens a browser".
- §6 SSE: "whenever anything changed" means essentially every 500 ms with the simulator, and every poll with Massive (because `update()` bumps `version` even when the price is unchanged). Worth stating, so the frontend expects identical-price events.
- §14 says "None at present", but sections 1.3, 2.5, 3.1 and 3.4 raise open decisions. Move the unresolved ones into §14 so agents have a single place to record answers.

---

## 6. Questions for the plan owner

1. Simulator persistence: should held tickers resume from their last known price after a restart (1.1)?
2. Ticker lookup: is it a new `MarketDataSource` method, or a Massive-only helper? What does the user see on a 429 (1.3)?
3. Is the Massive snapshot endpoint actually available on the free tier, and is `last_trade.timestamp` in ms or ns (1.3, 1.4)?
4. Do the positions table and heatmap recompute live from SSE (2.3)?
5. On an LLM transport failure, return 200 with an apology or a 5xx (2.5)?
6. Which agent owns the `backend/app/market/` extensions (1.2)?
7. Default DB path and static path resolution: env vars or hardcoded (3.1)?
