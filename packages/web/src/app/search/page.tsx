"use client";

import { useState } from "react";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { SearchBar } from "@/components/search/SearchBar";
import { ResultCard } from "@/components/search/ResultCard";
import { api, getApiError } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [pageType, setPageType] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.search(q, 20, pageType || undefined);
      setResults(response.results || []);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <SearchBar
        query={query}
        pageType={pageType}
        loading={loading}
        onQueryChange={setQuery}
        onPageTypeChange={setPageType}
        onSubmit={submit}
      />
      {error && <ErrorBanner message={error} />}
      <div className="space-y-3">
        {results.map((result) => (
          <ResultCard key={result.page_id} result={result} />
        ))}
      </div>
      {!loading && !error && query && results.length === 0 && (
        <p className="py-12 text-center text-sm text-gray-600">No results found.</p>
      )}
    </div>
  );
}
