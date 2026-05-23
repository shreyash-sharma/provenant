"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, getApiError } from "@/lib/api";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { RiskDetail } from "@/components/risk/RiskDetail";
import { RiskTable } from "@/components/risk/RiskTable";
import { useRiskOverview } from "@/hooks/useProvenant";
import type { RiskResponse } from "@/lib/types";

export default function RiskPage() {
  const overview = useRiskOverview();
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RiskResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async (path: string) => {
    setSelected(path);
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await api.risk([path]));
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setDetailLoading(false);
    }
  };

  if (overview.isLoading) {
    return <div className="flex justify-center py-20"><LoadingSpinner size={8} /></div>;
  }

  const files = overview.data?.files || [];

  return (
    <div className="space-y-4">
      {overview.error && <ErrorBanner message={getApiError(overview.error)} />}
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-[24rem_1fr] gap-6">
        <RiskTable files={files} selected={selected} onSelect={loadDetail} />
        <div className="min-h-96 rounded-lg border border-gray-800 bg-gray-900 p-5">
          {!selected && (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-gray-600">
              <AlertTriangle className="h-8 w-8 opacity-40" />
              <p className="text-sm">Select a file to inspect risk.</p>
            </div>
          )}
          {selected && detailLoading && (
            <div className="flex justify-center py-20"><LoadingSpinner size={6} /></div>
          )}
          {selected && !detailLoading && detail && <RiskDetail data={detail} path={selected} />}
        </div>
      </div>
    </div>
  );
}
