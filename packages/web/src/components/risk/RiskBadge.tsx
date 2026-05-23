import { clsx } from "clsx";

export function RiskBadge({ score }: { score: number }) {
  const label = score > 0.7 ? "High" : score > 0.4 ? "Medium" : "Low";

  return (
    <span
      className={clsx(
        "rounded-full border px-2 py-0.5 text-xs font-medium",
        score > 0.7 && "border-red-900/60 bg-red-950/40 text-red-300",
        score > 0.4 && score <= 0.7 && "border-yellow-900/60 bg-yellow-950/40 text-yellow-300",
        score <= 0.4 && "border-green-900/60 bg-green-950/40 text-green-300",
      )}
    >
      {label}
    </span>
  );
}
