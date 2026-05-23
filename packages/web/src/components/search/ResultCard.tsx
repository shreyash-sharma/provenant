import type { SearchResult } from "@/lib/types";
import { FilePath } from "@/components/shared/FilePath";

export function ResultCard({ result }: { result: SearchResult }) {
  const score =
    result.relevance_score ?? result.confidence_score ?? result.score ?? 0;

  return (
    <article className="space-y-2 rounded-lg border border-gray-800 bg-gray-900 p-4 transition hover:border-gray-700">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-medium text-white">{result.title}</h2>
          {result.target_path && <FilePath path={result.target_path} />}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
            {result.page_type}
          </span>
          <span className="font-mono text-xs text-gray-600">{score.toFixed(2)}</span>
        </div>
      </div>
      <p className="line-clamp-3 text-xs leading-relaxed text-gray-400">
        {result.snippet}
      </p>
    </article>
  );
}
