import { Trash2 } from "lucide-react";
import { clsx } from "clsx";
import type { DeadCodeFinding } from "@/lib/types";
import { FilePath } from "@/components/shared/FilePath";

export function DeadCodeTable({
  tier,
  count,
  lines,
  safeCount,
  truncated,
  findings,
}: {
  tier: string;
  count?: number;
  lines?: number;
  safeCount?: number;
  truncated?: boolean;
  findings: DeadCodeFinding[];
}) {
  if (!findings.length && !count) return null;

  return (
    <section>
      <p
        className={clsx(
          "mb-2 text-xs font-semibold uppercase tracking-wider",
          tier === "high" && "text-red-400",
          tier === "medium" && "text-yellow-400",
          tier === "low" && "text-gray-500",
        )}
      >
        {tier} confidence - {count ?? findings.length}
        {lines !== undefined && (
          <span className="ml-2 font-mono text-gray-600">{lines} lines</span>
        )}
        {safeCount !== undefined && (
          <span className="ml-2 font-mono text-gray-600">{safeCount} safe</span>
        )}
        {truncated && <span className="ml-2 text-gray-600">truncated</span>}
      </p>
      <div className="space-y-2">
        {findings.map((finding, index) => {
          const safe = finding.safe_to_remove ?? finding.safe_to_delete ?? false;
          const name = finding.name || finding.symbol_name || finding.file_path;
          return (
            <article
              key={`${finding.file_path}-${name}-${index}`}
              className="flex items-start justify-between gap-4 rounded-lg border border-gray-800 bg-gray-900 px-4 py-3"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex min-w-0 items-center gap-2">
                  <Trash2 className="h-3.5 w-3.5 shrink-0 text-gray-500" />
                  <span className="truncate font-mono text-sm text-white">{name}</span>
                  <span className="rounded bg-gray-800 px-1.5 text-xs text-gray-500">
                    {finding.kind}
                  </span>
                </div>
                <FilePath path={finding.file_path} />
                <p className="text-xs text-gray-500">{finding.reason}</p>
              </div>
              {safe && (
                <span className="shrink-0 rounded border border-green-900/60 bg-green-950/40 px-2 py-0.5 text-xs text-green-300">
                  Safe
                </span>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
