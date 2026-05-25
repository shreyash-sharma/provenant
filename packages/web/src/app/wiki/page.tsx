"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, getApiError } from "@/lib/api";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { PageDetailResponse, PageListResponse } from "@/lib/types";

type PageItem = PageListResponse["pages"][number];

function FreshnessBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    fresh: "bg-signal-green/20 text-signal-green",
    stale: "bg-signal-yellow/20 text-signal-yellow",
  };
  const cls = map[status] ?? "bg-white/10 text-on-surface-muted";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${cls}`}>
      {status}
    </span>
  );
}

function PageTypeSection({
  type,
  pages,
  selectedId,
  onSelect,
}: {
  type: string;
  pages: PageItem[];
  selectedId: number | null;
  onSelect: (page: PageItem) => void;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-on-surface-muted hover:text-on-surface"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {type.replace(/_/g, " ")}
        <span className="ml-auto font-normal normal-case tabular-nums">{pages.length}</span>
      </button>
      {open && (
        <div className="ml-2 space-y-px">
          {pages.map((page) => {
            const active = selectedId === page.id;
            return (
              <button
                key={page.id}
                type="button"
                onClick={() => onSelect(page)}
                className={`w-full rounded-lg px-3 py-2 text-left transition ${
                  active
                    ? "bg-white/[0.08] text-on-surface"
                    : "text-on-surface-muted hover:bg-white/[0.04] hover:text-on-surface"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm">{page.title}</span>
                  <FreshnessBadge status={page.freshness_status ?? "unknown"} />
                </div>
                {page.confidence != null && (
                  <div className="mt-0.5 text-[11px] text-on-surface-muted">
                    conf {(page.confidence * 100).toFixed(0)}%
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function WikiPage() {
  const [pages, setPages] = useState<PageItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PageDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    setListLoading(true);
    api
      .pages({ limit: 2000 })
      .then((data) => setPages(data.pages))
      .catch((err) => setListError(getApiError(err)))
      .finally(() => setListLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return q ? pages.filter((p) => p.title.toLowerCase().includes(q)) : pages;
  }, [pages, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, PageItem[]>();
    for (const p of filtered) {
      const key = p.page_type || "other";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(p);
    }
    return map;
  }, [filtered]);

  const handleSelect = async (page: PageItem) => {
    setSelectedId(page.id);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const d = await api.pageDetail(page.id);
      setDetail(d);
    } catch (err) {
      setDetailError(getApiError(err));
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-0 overflow-hidden rounded-xl border border-white/[0.08]">
      {/* Sidebar */}
      <div className="flex w-80 shrink-0 flex-col border-r border-white/[0.08]">
        <div className="border-b border-white/[0.08] p-3">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search pages..."
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.035] px-3 py-2 text-sm text-on-surface placeholder:text-on-surface-muted focus:outline-none focus:ring-1 focus:ring-white/20"
          />
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {listLoading && (
            <div className="flex justify-center py-8">
              <LoadingSpinner size={6} />
            </div>
          )}
          {listError && <ErrorBanner message={listError} />}
          {!listLoading &&
            Array.from(grouped.entries()).map(([type, typePages]) => (
              <PageTypeSection
                key={type}
                type={type}
                pages={typePages}
                selectedId={selectedId}
                onSelect={handleSelect}
              />
            ))}
          {!listLoading && filtered.length === 0 && !listError && (
            <p className="px-3 py-8 text-center text-sm text-on-surface-muted">No pages found.</p>
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {!selectedId && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-on-surface-muted">
            <FileText className="h-10 w-10 opacity-30" />
            <p className="text-sm">Select a page from the list</p>
          </div>
        )}
        {selectedId && detailLoading && (
          <div className="flex flex-1 items-center justify-center">
            <LoadingSpinner size={8} />
          </div>
        )}
        {selectedId && detailError && (
          <div className="p-6">
            <ErrorBanner message={detailError} />
          </div>
        )}
        {selectedId && !detailLoading && detail && (
          <div className="flex-1 overflow-y-auto p-8">
            <h1 className="mb-2 text-2xl font-semibold text-on-surface">{detail.title}</h1>
            {detail.summary && (
              <p className="mb-4 italic text-on-surface-muted">{detail.summary}</p>
            )}
            {/* Metadata row */}
            <div className="mb-6 flex flex-wrap items-center gap-3 text-xs text-on-surface-muted">
              <FreshnessBadge status={detail.freshness_status ?? "unknown"} />
              {detail.confidence != null && (
                <span>Confidence: {(detail.confidence * 100).toFixed(0)}%</span>
              )}
              {detail.updated_at && (
                <span>Updated: {new Date(detail.updated_at).toLocaleDateString()}</span>
              )}
              {detail.version != null && <span>v{detail.version}</span>}
            </div>
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.content || ""}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
