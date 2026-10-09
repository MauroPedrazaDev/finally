"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { fmtPrice, fmtQty } from "@/lib/format";
import type { ChatAction, ChatMessage } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  onSend: (message: string) => void;
  collapsed: boolean;
  onToggle: () => void;
}

export function ChatPanel({ messages, loading, error, onSend, collapsed, onToggle }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, loading, collapsed]);

  const send = (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    onSend(text);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  if (collapsed) {
    return (
      <aside data-testid="chat-panel" data-collapsed="true" className="flex w-9 shrink-0 flex-col border-l border-line bg-ink-950">
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Open assistant"
          className="flex flex-1 flex-col items-center gap-3 pt-3 text-fg-muted hover:bg-ink-800 hover:text-fg"
        >
          <span className="text-[13px]">‹</span>
          <span className="font-cond text-[12px] font-semibold [writing-mode:vertical-rl]">Assistant</span>
        </button>
      </aside>
    );
  }

  return (
    <aside data-testid="chat-panel" className="flex w-[360px] shrink-0 flex-col border-l border-line bg-ink-950">
      <header className="flex h-7 shrink-0 items-center justify-between border-b border-line bg-ink-800 px-2.5">
        <h2 className="font-cond text-[12px] font-semibold text-fg-muted">
          Assistant <span className="font-normal text-fg-dim">can trade and edit your watchlist</span>
        </h2>
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Collapse assistant"
          className="px-1 text-[13px] text-fg-muted hover:text-fg"
        >
          ›
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && !loading && (
          <div className="space-y-2 text-[12px] text-fg-dim">
            <p>Ask about your portfolio, or tell FinAlly what to do.</p>
            <ul className="space-y-1 text-fg-muted">
              <li>“How concentrated is my portfolio?”</li>
              <li>“Buy 5 NVDA and add PYPL to my watchlist”</li>
            </ul>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={`${m.created_at}-${i}`} message={m} />
        ))}
        {loading && (
          <div data-testid="chat-loading" className="flex items-center gap-2 text-[12px] text-fg-muted" aria-live="polite">
            <span className="flex gap-1">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-primary" />
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-primary [animation-delay:150ms]" />
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-primary [animation-delay:300ms]" />
            </span>
            FinAlly is thinking
          </div>
        )}
        {error && (
          <p data-testid="chat-error" role="alert" className="text-[12px] text-down">
            {error}
          </p>
        )}
      </div>

      <form onSubmit={send} className="shrink-0 border-t border-line p-2">
        <textarea
          data-testid="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Message FinAlly"
          aria-label="Message FinAlly"
          className="block w-full resize-none border border-line bg-ink-900 px-2 py-1.5 text-[12.5px] text-fg placeholder:text-fg-dim focus:border-primary focus:outline-none"
        />
        <div className="mt-1.5 flex items-center justify-between">
          <span className="text-[10.5px] text-fg-dim">Enter to send, Shift+Enter for a new line</span>
          <button
            data-testid="chat-send"
            type="submit"
            disabled={loading || !draft.trim()}
            className="bg-secondary px-4 py-1 text-[12px] font-semibold text-white hover:bg-[#8a45a8] disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </aside>
  );
}

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div data-testid="chat-message" data-role={message.role} className={isUser ? "pl-8" : "pr-4"}>
      <div
        className={`whitespace-pre-wrap break-words px-2.5 py-1.5 text-[12.5px] leading-relaxed ${
          isUser ? "border border-primary/30 bg-primary/10 text-fg" : "border-l-2 border-accent/70 bg-ink-850 text-fg"
        }`}
      >
        {message.message}
      </div>
      {message.actions && message.actions.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {message.actions.map((a, i) => (
            <ActionChip key={i} action={a} />
          ))}
        </div>
      )}
    </div>
  );
}

export function describeAction(a: ChatAction): string {
  if (a.type === "trade") {
    const verb = a.side === "buy" ? "Buy" : "Sell";
    const at = a.status === "executed" && a.price != null ? ` @ ${fmtPrice(a.price)}` : "";
    return `${verb} ${fmtQty(a.quantity)} ${a.ticker}${at}`;
  }
  return `${a.action === "add" ? "Watch" : "Unwatch"} ${a.ticker}`;
}

export function ActionChip({ action }: { action: ChatAction }) {
  const ok = action.status === "executed";
  return (
    <span
      data-testid="action-chip"
      data-status={action.status}
      title={action.error ?? undefined}
      className={`num inline-flex max-w-full items-center gap-1.5 border px-1.5 py-0.5 text-[11px] ${
        ok ? "border-up/50 bg-up/10 text-up" : "border-down/50 bg-down/10 text-down"
      }`}
    >
      <span aria-hidden>{ok ? "✓" : "✕"}</span>
      <span>{describeAction(action)}</span>
      {!ok && action.error && <span className="font-sans text-down/90">: {action.error}</span>}
    </span>
  );
}
