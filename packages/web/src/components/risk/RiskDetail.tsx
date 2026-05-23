import { Minus, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";
import { clsx } from "clsx";
import type { RiskResponse, RiskTarget } from "@/lib/types";
import { FilePath } from "@/components/shared/FilePath";
import { RiskBadge } from "./RiskBadge";

export function RiskDetail({ data, path }: { data: RiskResponse; path: string }) {
  const file = data.targets?.[path] ?? Object.values(data.targets ?? {})[0];
  if (!file) {
    return <p className="text-sm text-gray-500">No risk profile returned for this file.</p>;
  }

  const score = Number(file.hotspot_score ?? file.risk_score ?? 0);
  const trend = file.trend ?? "stable";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilePath path={path} className="text-sm" />
        <div className="flex items-center gap-2">
          <TrendIcon trend={trend} />
          <RiskBadge score={score} />
        </div>
      </div>

      {file.risk_summary && (
        <p className="rounded-lg border border-gray-800 bg-gray-950 px-4 py-3 text-sm leading-relaxed text-gray-300">
          {file.risk_summary}
        </p>
      )}

      <ScoreBar score={score} />
      <RiskFacts file={file} trend={trend} />
      <SecuritySignals signals={file.security_signals ?? []} />
      <PathList title="Co-change partners" paths={file.co_change_partners ?? []} />
      <PathList title="Impact surface" paths={file.impact_surface ?? []} />
      <PathList title="Global hotspots" paths={data.global_hotspots ?? []} />
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-gray-500">
        <span>Hotspot score</span>
        <span className="font-mono">{score.toFixed(2)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-gray-800">
        <div
          className={clsx(
            "h-full",
            score > 0.7 ? "bg-red-500" : score > 0.4 ? "bg-yellow-500" : "bg-green-500",
          )}
          style={{ width: `${Math.min(Math.max(score, 0) * 100, 100)}%` }}
        />
      </div>
    </div>
  );
}

function RiskFacts({ file, trend }: { file: RiskTarget; trend: string }) {
  const facts = [
    ["Risk type", file.risk_type],
    ["Dependents", file.dependents_count],
    ["Test gap", file.test_gap ? "No tests found" : "Covered"],
    ["Trend", trend],
    ["Primary owner", file.primary_owner],
    ["Bus factor", file.bus_factor],
    ["Change pattern", file.change_pattern],
    ["Avg commit size", file.change_magnitude?.avg_commit_size],
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {facts.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-gray-800 bg-gray-950 p-3">
          <p className="mb-0.5 text-xs text-gray-500">{label}</p>
          <p className="truncate text-sm text-white">{String(value ?? "-")}</p>
        </div>
      ))}
    </div>
  );
}

function SecuritySignals({
  signals,
}: {
  signals: NonNullable<RiskTarget["security_signals"]>;
}) {
  if (!signals.length) return null;

  return (
    <div className="space-y-2 rounded-lg border border-red-900/60 bg-red-950/30 p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-red-300">
        <ShieldAlert className="h-4 w-4" />
        Security signals
      </div>
      {signals.map((signal, index) => (
        <div key={`${signal.kind}-${index}`} className="text-xs text-red-200">
          <span className="mr-2 rounded bg-red-900/40 px-1.5 font-mono">
            {signal.severity}
          </span>
          <span className="font-mono text-red-300">{signal.kind}</span>
          <span className="text-red-200/80"> {signal.snippet}</span>
        </div>
      ))}
    </div>
  );
}

function PathList({
  title,
  paths,
}: {
  title: string;
  paths: { file_path: string; count?: number; hotspot_score?: number; pagerank?: number }[];
}) {
  if (!paths.length) return null;

  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
        {title}
      </p>
      <div className="space-y-2">
        {paths.map((item) => (
          <div
            key={item.file_path}
            className="flex items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-950 px-3 py-2"
          >
            <FilePath path={item.file_path} />
            <span className="font-mono text-xs text-gray-600">
              {item.count ?? item.hotspot_score?.toFixed(2) ?? item.pagerank?.toFixed(4)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "increasing") return <TrendingUp className="h-4 w-4 text-red-400" />;
  if (trend === "decreasing") return <TrendingDown className="h-4 w-4 text-green-400" />;
  return <Minus className="h-4 w-4 text-gray-500" />;
}
