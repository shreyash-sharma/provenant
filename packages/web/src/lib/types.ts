export interface AnswerResponse {
  answer: string;
  citations: string[];
  confidence: "high" | "medium" | "low";
  attribution_confidence?: number;
  fallback_targets: string[];
  retrieval: RetrievalHit[];
  note?: string;
  compression?: {
    initial_files?: number;
    final_files?: number;
    compression_pct?: number;
    pruned_files?: string[];
  };
  _meta?: {
    timing_ms?: number;
    hint?: string;
    cached?: boolean;
  };
}

export interface RetrievalHit {
  page_id: string;
  title: string;
  target_path: string;
  page_type: string;
  snippet: string;
  summary: string;
  score: number;
  confidence_score?: number;
  symbols?: CodeSymbol[];
}

export interface CodeSymbol {
  name: string;
  kind: string;
  signature: string;
  docstring?: string;
  start_line?: number;
  end_line?: number;
  _matched?: boolean;
}

export interface SearchResult {
  page_id: string;
  title: string;
  page_type: string;
  snippet: string;
  relevance_score?: number;
  confidence_score?: number;
  score?: number;
  target_path?: string;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface OverviewResponse {
  summary?: string;
  file_count?: number;
  symbol_count?: number;
  modules?: { title: string; summary: string; path: string }[];
  [key: string]: unknown;
}

export interface RiskOverviewResponse {
  files: { path: string; page_type: string; meta: string }[];
}

export interface RiskResponse {
  targets: Record<string, RiskTarget>;
  global_hotspots?: {
    file_path: string;
    hotspot_score?: number;
    primary_owner?: string | null;
  }[];
  pr_blast_radius?: Record<string, unknown>;
}

export interface RiskTarget {
  target: string;
  hotspot_score?: number;
  risk_score?: number;
  trend?: "increasing" | "stable" | "decreasing" | "unknown";
  risk_type?: string;
  risk_summary?: string;
  dependents_count?: number;
  test_gap?: boolean;
  primary_owner?: string | null;
  owner_pct?: number | null;
  recent_owner?: string | null;
  recent_owner_pct?: number | null;
  bus_factor?: number;
  contributor_count?: number;
  change_pattern?: string;
  change_magnitude?: {
    lines_added_90d?: number;
    lines_deleted_90d?: number;
    avg_commit_size?: number;
  };
  co_change_partners?: {
    file_path: string;
    count?: number;
    last_co_change?: string | null;
    has_import_link?: boolean;
  }[];
  impact_surface?: {
    file_path: string;
    pagerank?: number;
    is_entry_point?: boolean;
  }[];
  security_signals?: {
    kind: string;
    severity: string;
    snippet: string;
  }[];
  cross_repo_impact?: Record<string, unknown>;
}

export interface ContextResponse {
  targets: Record<string, ContextTarget>;
  truncated?: boolean;
  dropped_targets?: string[];
  dropped_symbols?: Record<string, string[]>;
  _meta?: {
    timing_ms?: number;
    hint?: string;
  };
}

export interface ContextTarget {
  target: string;
  type?: "file" | "module" | "symbol";
  error?: string;
  suggestions?: string[];
  docs?: {
    title?: string;
    summary?: string;
    content_md?: string;
    documentation?: string;
    human_notes?: string;
    symbols?: CodeSymbol[];
    files?: { path: string; description?: string; confidence_score?: number }[];
    file_path?: string;
    file_summary?: string;
    docstring?: string;
    used_by?: string[];
    imported_by?: string[];
    candidates?: { name: string; kind?: string; file_path?: string }[];
  };
  source?: {
    body?: string;
    start_line?: number;
    end_line?: number;
    language?: string;
    truncated?: boolean;
    error?: string;
  };
  freshness?: {
    confidence_score?: number | null;
    freshness_status?: string | null;
    is_stale?: boolean | null;
  };
  cross_repo?: Record<string, unknown>;
}

export interface DeadCodeResponse {
  summary?: {
    total_findings?: number;
    filtered_findings?: number;
    deletable_lines?: number;
    safe_to_delete_count?: number;
    by_kind?: Record<string, number>;
  };
  tiers?: Record<string, DeadCodeTier>;
  by_directory?: {
    directory: string;
    count: number;
    lines: number;
    safe_count: number;
  }[];
  by_owner?: {
    owner: string;
    count: number;
    lines: number;
    safe_count: number;
  }[];
  impact?: {
    total_lines_reclaimable?: number;
    safe_lines_reclaimable?: number;
    recommendation?: string;
  };
  limit_note?: string;
}

export interface DeadCodeTier {
  description?: string;
  count?: number;
  lines?: number;
  safe_count?: number;
  findings?: DeadCodeFinding[];
  truncated?: boolean;
}

export interface ProjectResponse {
  id: string;
  name: string;
  path: string;
  default_branch?: string;
  head_commit?: string | null;
  settings?: Record<string, unknown>;
  state?: {
    provider?: string;
    model?: string;
    total_pages?: number;
    total_tokens?: number;
    docs_enabled?: boolean;
    last_sync_commit?: string | null;
    phase_timings?: Record<string, number>;
  };
  counts?: {
    pages: number;
    files: number;
    symbols: number;
  };
}

export interface GraphResponse {
  nodes: {
    id: string;
    name: string;
    type: "FILE" | "SYMBOL";
    path?: string;
    pagerank?: number;
    community_id?: number;
    is_entry_point?: boolean;
    symbol_count?: number;
  }[];
  edges: {
    source: string;
    target: string;
    type: string;
    confidence?: number;
  }[];
}

export interface DeadCodeFinding {
  file_path: string;
  kind: string;
  name?: string;
  symbol_name?: string;
  confidence: number;
  reason: string;
  safe_to_remove?: boolean;
  safe_to_delete?: boolean;
  line?: number;
}

// /api/model response
export interface ModelResponse {
  repo: {
    id: number;
    name: string;
    path: string;
    branch: string | null;
    head_commit: string | null;
  };
  settings: Record<string, unknown>;
  state: Record<string, unknown>;
  corpus: {
    pages: number;
    files: number;
    symbols: number;
    graph_nodes: number;
    graph_edges: number;
    build_input_tokens: number;
    build_output_tokens: number;
    avg_confidence: number | null;
    freshness: { fresh: number; stale: number };
  };
  quality: {
    avg_attribution_confidence: number | null;
    total_queries: number;
    low_confidence_queries: number;
  };
  repair: {
    weak_page_count: number;
    total_repair_runs: number;
    last_repair_at: string | null;
    last_repair_page_count: number;
    weak_pages: Array<{
      page_id: number;
      title: string;
      path: string;
      citation_rate: number;
      retrieval_count: number;
    }>;
  };
}

// /api/pages response
export interface PageListResponse {
  pages: Array<{
    id: number;
    title: string;
    path: string;
    page_type: string;
    freshness: string;
    freshness_status: string | null;
    confidence: number | null;
    updated_at: string | null;
  }>;
  total: number;
  limit: number;
  offset: number;
}

// /api/pages/{id} response
export interface PageDetailResponse {
  id: number;
  title: string;
  path: string;
  page_type: string;
  content: string;
  summary: string | null;
  freshness: string;
  freshness_status: string | null;
  confidence: number | null;
  version: number | null;
  input_tokens: number;
  output_tokens: number;
  updated_at: string | null;
  history: Array<{ version: number; updated_at: string; content_snippet: string }>;
}

// /api/repair/candidates response
export interface RepairCandidatesResponse {
  candidates: Array<{
    page_id: number;
    title: string;
    path: string;
    citation_rate: number;
    retrieval_count: number;
    cited_count: number;
    last_retrieved_at: string | null;
  }>;
  summary: {
    total_weak_pages: number;
    avg_citation_rate: number;
    total_affected_queries: number;
  };
  params: {
    weak_threshold: number;
    min_retrievals: number;
    limit: number;
  };
}

export interface BlastRadiusResponse {
  seed_files: string[];
  affected: { file: string; depth: number }[];
  stats: { total_affected: number; max_depth_reached: number };
}

export interface DecisionRecord {
  id: string;
  title: string;
  status: string;
  context: string;
  decision: string;
  rationale: string;
  alternatives: string[];
  consequences: string[];
  affected_files: string[];
  tags: string[];
  source: string;
  confidence: number | null;
  staleness_score: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DecisionsResponse {
  decisions: DecisionRecord[];
  total: number;
}

export interface RiskHeatmapFile {
  file: string;
  is_hotspot: boolean;
  churn_percentile: number;
  temporal_hotspot_score: number;
  primary_owner: string | null;
  owner_pct: number | null;
  bus_factor: number;
  contributor_count: number;
  commit_count_90d: number;
  pagerank: number;
  community_id: number | null;
}

export interface RiskHeatmapResponse {
  files: RiskHeatmapFile[];
  stats: {
    total_files: number;
    hotspot_count: number;
    avg_bus_factor: number;
    solo_owned_count: number;
  };
}

// /api/repair/run request body + response
export interface RepairRunRequest {
  dry_run?: boolean;
  top_n?: number;
  weak_threshold?: number;
  min_retrievals?: number;
  selected_pages?: number[] | null;
}

export interface RepairRunResponse {
  repaired: number;
  skipped: number;
  pages: Array<{
    page_id: number;
    title: string;
    path: string;
    status: string;
    error: string | null;
  }>;
  dry_run: boolean;
  total_input_tokens: number;
  total_output_tokens: number;
}
