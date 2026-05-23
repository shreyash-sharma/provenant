"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { PageHeader, MetricCard, Panel, DataTable, StatusBadge } from "@/components/provenant/console";
import { api, getApiError } from "@/lib/api";
import type { ModelResponse, ProjectResponse } from "@/lib/types";
import { DEFAULT_INPUT_COST_PER_M_TOKEN, estimateInputCost, formatCompact, formatCurrency, formatNumber } from "@/lib/economics";

export default function OperationsPage() {
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [modelData, setModelData] = useState<ModelResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectData, modelResp] = await Promise.all([
        api.project(),
        api.model().catch(() => null),
      ]);
      setProject(projectData);
      setModelData(modelResp);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const buildTokens = modelData
    ? (modelData.corpus.build_input_tokens ?? 0) + (modelData.corpus.build_output_tokens ?? 0)
    : Number(project?.state?.total_tokens ?? 0);
  const buildCost = estimateInputCost(buildTokens);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Runtime and Economics"
        description="Provider settings, local API state, token spend, and the cost to build the repository model."
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-outline-variant bg-surface-container px-3 text-sm text-on-surface-muted transition hover:text-on-surface"
          >
            <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refresh
          </button>
        }
      />

      {error && (
        <Panel>
          <p className="text-sm text-signal-red">{error}</p>
        </Panel>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="Build Cost" value={formatCurrency(buildCost)} detail={`${formatCompact(buildTokens)} tokens`} />
        <MetricCard label="Pages" value={formatNumber(modelData?.corpus?.pages ?? project?.counts?.pages)} />
        <MetricCard label="Avg Confidence" value={modelData?.corpus?.avg_confidence != null ? `${(modelData.corpus.avg_confidence * 100).toFixed(0)}%` : "—"} />
        <MetricCard label="Price Model" value={`$${DEFAULT_INPUT_COST_PER_M_TOKEN}/M`} detail="input-token estimate" />
      </div>

      <Panel title="System State" description="Current local Provenant server and repository metadata.">
        <DataTable
          columns={["Subsystem", "Value", "State"]}
          rows={[
            ["API", "http://localhost:7337", <StatusBadge key="api" tone={error ? "bad" : "good"}>{error ? "issue" : "connected"}</StatusBadge>],
            ["Repository", project?.name || "-", <StatusBadge key="repo" tone={project ? "good" : "warn"}>{project ? "loaded" : "unknown"}</StatusBadge>],
            ["Provider", String(project?.state?.provider || project?.settings?.provider || "-"), <StatusBadge key="provider">configured</StatusBadge>],
            ["Model", String(project?.state?.model || project?.settings?.model || "-"), <StatusBadge key="model">active</StatusBadge>],
            ["Pages", formatNumber(project?.counts?.pages ?? project?.state?.total_pages), <StatusBadge key="pages" tone={project?.counts?.pages ? "good" : "warn"}>indexed</StatusBadge>],
          ].map((row) => [
            <span key="k" className="font-medium text-on-surface">{row[0]}</span>,
            <span key="v" className="font-mono">{row[1]}</span>,
            row[2],
          ])}
        />
      </Panel>

      <Panel title="Build Economics" description="Cost to generate the repository representation. Served by /api/economics once backend aggregation is complete.">
        <DataTable
          columns={["Measure", "Tokens", "Estimated Cost", "Notes"]}
          rows={[
            ["Index build", formatCompact(buildTokens), formatCurrency(buildCost), "LLM tokens used to create all wiki pages"],
            ["Input tokens", formatCompact(modelData?.corpus?.build_input_tokens ?? 0), formatCurrency(estimateInputCost(modelData?.corpus?.build_input_tokens ?? 0)), "prompts sent during indexing"],
            ["Output tokens", formatCompact(modelData?.corpus?.build_output_tokens ?? 0), "—", "wiki page content generated"],
          ].map((row) => [
            <span key="m" className="font-medium text-on-surface">{row[0]}</span>,
            <span key="t" className="font-mono">{row[1]}</span>,
            <span key="d" className="font-mono text-signal-green">{row[2]}</span>,
            row[3],
          ])}
        />
      </Panel>
    </div>
  );
}
