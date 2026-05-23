export const DEFAULT_INPUT_COST_PER_M_TOKEN = 2.5;

export function estimateInputCost(tokens: number, costPerMTokens = DEFAULT_INPUT_COST_PER_M_TOKEN): number {
  if (!Number.isFinite(tokens) || tokens <= 0) return 0;
  return (tokens / 1_000_000) * costPerMTokens;
}

export function formatCurrency(value: number): string {
  if (!Number.isFinite(value)) return "$0.00";
  if (Math.abs(value) < 0.01 && value !== 0) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return Math.round(value).toLocaleString();
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${Math.round(value)}%`;
}
