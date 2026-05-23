import { clsx } from "clsx";
import type { AnswerResponse } from "@/lib/types";

const styles = {
  high: "border-green-900/60 bg-green-950/40 text-green-300",
  medium: "border-yellow-900/60 bg-yellow-950/40 text-yellow-300",
  low: "border-red-900/60 bg-red-950/40 text-red-300",
};

export function ConfidenceBadge({
  confidence,
}: {
  confidence: AnswerResponse["confidence"];
}) {
  return (
    <span
      className={clsx(
        "rounded-full border px-2 py-0.5 text-xs font-medium",
        styles[confidence],
      )}
    >
      {confidence}
    </span>
  );
}
