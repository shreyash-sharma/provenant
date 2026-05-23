import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.12em] text-signal-cyan">
            {eyebrow}
          </div>
        )}
        <h1 className="truncate text-xl font-semibold text-on-surface">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-muted">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  description,
  children,
  action,
  className = "",
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-md border border-outline-variant bg-surface-container-low ${className}`}>
      {(title || description || action) && (
        <div className="flex items-start justify-between gap-3 border-b border-outline-variant px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-medium text-on-surface">{title}</h2>}
            {description && <p className="mt-0.5 text-xs leading-5 text-on-surface-subtle">{description}</p>}
          </div>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad" | "info";
}) {
  const toneClass = {
    neutral: "text-on-surface",
    good: "text-signal-green",
    warn: "text-signal-amber",
    bad: "text-signal-red",
    info: "text-signal-cyan",
  }[tone];

  return (
    <div className="min-h-[88px] rounded-md border border-outline-variant bg-surface-container px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-[0.1em] text-on-surface-subtle">
        {label}
      </div>
      <div className={`mt-2 truncate font-mono text-2xl font-semibold ${toneClass}`}>
        {value}
      </div>
      {detail && <div className="mt-1 truncate text-xs text-on-surface-muted">{detail}</div>}
    </div>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad" | "info";
}) {
  const classes = {
    neutral: "border-outline-variant bg-surface-container-high text-on-surface-muted",
    good: "border-signal-green/30 bg-signal-green/10 text-signal-green",
    warn: "border-signal-amber/30 bg-signal-amber/10 text-signal-amber",
    bad: "border-signal-red/30 bg-signal-red/10 text-signal-red",
    info: "border-signal-cyan/30 bg-signal-cyan/10 text-signal-cyan",
  }[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${classes}`}>
      {children}
    </span>
  );
}

export function DataTable({
  columns,
  rows,
  empty,
}: {
  columns: string[];
  rows: ReactNode[][];
  empty?: string;
}) {
  if (!rows.length) {
    return (
      <div className="rounded-md border border-dashed border-outline-variant px-4 py-8 text-center text-sm text-on-surface-subtle">
        {empty || "No rows yet."}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-xs">
        <thead>
          <tr className="border-b border-outline-variant">
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-medium uppercase tracking-[0.08em] text-on-surface-subtle">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-outline-variant/70 last:border-0">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2.5 align-top text-on-surface-muted">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProgressBar({ value, tone = "info" }: { value: number; tone?: "good" | "warn" | "bad" | "info" }) {
  const fill = {
    good: "bg-signal-green",
    warn: "bg-signal-amber",
    bad: "bg-signal-red",
    info: "bg-signal-cyan",
  }[tone];
  return (
    <div className="h-2 overflow-hidden rounded-full bg-surface-container-high">
      <div className={`h-full ${fill}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
