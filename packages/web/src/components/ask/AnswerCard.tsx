"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AnswerResponse } from "@/lib/types";
import { CitationList } from "./CitationList";
import { ConfidenceBadge } from "./ConfidenceBadge";

export function AnswerCard({ data }: { data: AnswerResponse }) {
  const compression = data.compression;

  return (
    <section className="space-y-4 rounded-lg border border-gray-800 bg-gray-900 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ConfidenceBadge confidence={data.confidence} />
        <div className="flex items-center gap-3 font-mono text-xs text-gray-500">
          {compression?.compression_pct !== undefined && (
            <span>{compression.compression_pct.toFixed(0)}% compressed</span>
          )}
          {data._meta?.timing_ms !== undefined && (
            <span>{data._meta.timing_ms.toFixed(0)} ms</span>
          )}
        </div>
      </div>

      {data.answer ? (
        <div className="prose-provenant text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.answer}</ReactMarkdown>
        </div>
      ) : (
        <p className="text-sm text-gray-400">{data.note || "No synthesized answer."}</p>
      )}

      {data.note && data.answer && (
        <div className="rounded-md border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-500">
          {data.note}
        </div>
      )}

      <CitationList citations={data.citations || []} />

      {data.fallback_targets?.length > 0 && (
        <details className="text-xs text-gray-500">
          <summary className="cursor-pointer hover:text-gray-300">
            Fallback targets
          </summary>
          <ul className="mt-2 space-y-1 font-mono">
            {data.fallback_targets.map((target) => (
              <li key={target}>{target}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
