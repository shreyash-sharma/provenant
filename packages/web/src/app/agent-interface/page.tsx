import { PageHeader, Panel, DataTable, StatusBadge } from "@/components/provenant/console";

const endpoints = [
  ["GET", "/api/project", "Repository model metadata and corpus counts"],
  ["GET", "/api/search", "Search representation pages"],
  ["POST", "/api/context", "Emit compact/full context for targets"],
  ["GET", "/api/graph", "Graph nodes and edges"],
  ["POST", "/api/risk", "Risk diagnostics for targets"],
  ["POST", "/api/dead-code", "Dead-code findings"],
  ["GET", "/api/model", "Snapshot, quality, repair, and economics summary"],
  ["GET", "/api/pages", "List representation pages with freshness and confidence"],
  ["GET", "/api/pages/{id}", "Full page detail including content and history"],
  ["GET", "/api/repair/candidates", "Weak pages from attribution logs"],
  ["POST", "/api/repair/run", "Dry-run or execute targeted repairs"],
];

const planned = [
  ["GET", "/api/economics", "Repository-level token and money savings"],
];

export default function AgentInterfacePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agent Interface"
        title="Context Contract"
        description="The interface downstream coding agents consume. Provenant should make the emitted context packet inspectable and measurable."
      />

      <Panel title="Current REST Surface" description="Available from the local Provenant server today. Includes model, pages, and repair endpoints.">
        <DataTable
          columns={["Method", "Endpoint", "Purpose", "State"]}
          rows={endpoints.map((row) => [
            <span key="m" className="font-mono text-on-surface">{row[0]}</span>,
            <span key="e" className="font-mono">{row[1]}</span>,
            row[2],
            <StatusBadge key="s" tone="good">available</StatusBadge>,
          ])}
        />
      </Panel>

      <Panel title="Planned API Targets" description="Endpoints still needed to make the UI wiki fully backend-backed.">
        <DataTable
          columns={["Method", "Endpoint", "Purpose", "State"]}
          rows={planned.map((row) => [
            <span key="m" className="font-mono text-on-surface">{row[0]}</span>,
            <span key="e" className="font-mono">{row[1]}</span>,
            row[2],
            <StatusBadge key="s" tone="warn">next backend pass</StatusBadge>,
          ])}
        />
      </Panel>

      <Panel title="Context Packet Shape" description="The primary object Provenant hands to agents.">
        <pre className="overflow-auto rounded-md border border-outline-variant bg-surface-dim p-4 text-xs leading-6 text-on-surface-muted">
{`{
  "query": "agent task or target",
  "pages": [
    {
      "page_id": "file:src/auth/session.py",
      "target_path": "src/auth/session.py",
      "summary": "...",
      "content": "...",
      "source_hash": "abc123",
      "confidence": 0.87
    }
  ],
  "metrics": {
    "emitted_tokens": 4200,
    "raw_source_equivalent_tokens": 180000,
    "tokens_saved": 175800,
    "estimated_dollars_saved": 0.44
  }
}`}
        </pre>
      </Panel>
    </div>
  );
}
