import type { ReactNode } from "react";

interface PanelProps {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  testId?: string;
  /** Extra data-* attributes for the section element. */
  data?: Record<`data-${string}`, string | number | undefined>;
}

export function Panel({ title, aside, children, className = "", bodyClassName = "", testId, data }: PanelProps) {
  return (
    <section
      data-testid={testId}
      {...data}
      className={`flex min-h-0 min-w-0 flex-col border border-line bg-ink-850 ${className}`}
    >
      <header className="flex h-7 shrink-0 items-center justify-between gap-2 border-b border-line bg-ink-800 px-2.5">
        <h2 className="font-cond text-[12px] font-semibold tracking-wide text-fg-muted">{title}</h2>
        {aside}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
