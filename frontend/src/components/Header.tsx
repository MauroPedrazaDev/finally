import type { ConnectionStatus } from "@/lib/connection";
import { fmtMoney, fmtSignedMoney, toneClass } from "@/lib/format";
import type { Valuation } from "@/lib/valuation";

const STATUS_STYLE: Record<ConnectionStatus, { dot: string; label: string }> = {
  connected: { dot: "bg-up", label: "Live" },
  reconnecting: { dot: "bg-accent pulse-dot", label: "Reconnecting" },
  disconnected: { dot: "bg-down", label: "Offline" },
};

export function Header({ valuation, status }: { valuation: Valuation | null; status: ConnectionStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <header className="flex h-12 shrink-0 items-center gap-8 border-b border-line bg-ink-950 px-4">
      <div className="flex items-baseline gap-2">
        <span className="font-cond text-[19px] font-semibold tracking-tight text-fg">
          Fin<span className="text-accent">Ally</span>
        </span>
        <span className="text-[11px] text-fg-dim">AI trading workstation</span>
      </div>

      <div className="ml-auto flex items-center gap-7">
        <Stat label="Portfolio value">
          <span data-testid="header-total-value" className="num text-[18px] font-medium text-fg">
            {fmtMoney(valuation?.totalValue)}
          </span>
        </Stat>
        <Stat label="Unrealized P&L">
          <span className={`num text-[14px] ${toneClass(valuation?.unrealizedPnl)}`}>
            {fmtSignedMoney(valuation?.unrealizedPnl)}
          </span>
        </Stat>
        <Stat label="Cash">
          <span data-testid="header-cash" className="num text-[14px] text-fg">
            {fmtMoney(valuation?.cash)}
          </span>
        </Stat>
        <div
          data-testid="connection-status"
          data-status={status}
          title={`Price stream: ${s.label}`}
          className="flex items-center gap-2 border-l border-line pl-5 text-[11px] text-fg-muted"
        >
          <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden />
          <span>{s.label}</span>
        </div>
      </div>
    </header>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10.5px] text-fg-dim">{label}</span>
      {children}
    </div>
  );
}
