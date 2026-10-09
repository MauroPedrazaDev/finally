import { fmtMoney, fmtPercent, fmtPrice, fmtQty, fmtSignedMoney, toneClass } from "@/lib/format";
import type { ValuedPosition } from "@/lib/valuation";

interface PositionsTableProps {
  positions: ValuedPosition[];
  onSelect?: (ticker: string) => void;
}

export function PositionsTable({ positions, onSelect }: PositionsTableProps) {
  return (
    <table data-testid="positions-table" className="w-full border-collapse text-[12px]">
      <thead className="sticky top-0 bg-ink-850 text-[10.5px] text-fg-dim">
        <tr className="border-b border-line">
          <th className="px-2.5 py-1 text-left font-normal">Symbol</th>
          <th className="px-2 py-1 text-right font-normal">Qty</th>
          <th className="px-2 py-1 text-right font-normal">Avg cost</th>
          <th className="px-2 py-1 text-right font-normal">Last</th>
          <th className="px-2 py-1 text-right font-normal">Market value</th>
          <th className="px-2 py-1 text-right font-normal">Unrealized P&amp;L</th>
          <th className="px-2.5 py-1 text-right font-normal">P&amp;L %</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr
            key={p.ticker}
            data-testid={`position-row-${p.ticker}`}
            onClick={() => onSelect?.(p.ticker)}
            className="cursor-pointer border-b border-line/60 hover:bg-ink-800"
          >
            <td className="px-2.5 py-1 font-cond text-[13px] font-semibold">{p.ticker}</td>
            <td className="num px-2 py-1 text-right">{fmtQty(p.quantity)}</td>
            <td className="num px-2 py-1 text-right text-fg-muted">{fmtPrice(p.avg_cost)}</td>
            <td className="num px-2 py-1 text-right" title={p.priceSource === "live" ? undefined : "No live price yet"}>
              {fmtPrice(p.price)}
            </td>
            <td className="num px-2 py-1 text-right">{fmtMoney(p.market_value)}</td>
            <td className={`num px-2 py-1 text-right ${toneClass(p.unrealized_pnl)}`}>
              {fmtSignedMoney(p.unrealized_pnl)}
            </td>
            <td className={`num px-2.5 py-1 text-right ${toneClass(p.unrealized_pnl_percent)}`}>
              {fmtPercent(p.unrealized_pnl_percent)}
            </td>
          </tr>
        ))}
        {positions.length === 0 && (
          <tr>
            <td colSpan={7} className="px-3 py-5 text-center text-fg-dim">
              No open positions. Use the trade bar above, or ask the assistant.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
