import axios from "axios";
import type {
  AnswerResponse,
  BlastRadiusResponse,
  ContextResponse,
  DeadCodeResponse,
  DecisionsResponse,
  GraphResponse,
  ModelResponse,
  OverviewResponse,
  PageDetailResponse,
  PageListResponse,
  ProjectResponse,
  RepairCandidatesResponse,
  RepairRunRequest,
  RepairRunResponse,
  RiskHeatmapResponse,
  RiskResponse,
  RiskOverviewResponse,
  SearchResponse,
} from "./types";

// Use relative URLs so the API and the web UI can live on the same origin
// without any hard-coded port.
//
// Dev:  Next.js rewrites /api/* → http://localhost:7337/api/* (see next.config.js)
// Prod: FastAPI serves both the static app and /api/* on the same port, so
//       relative paths work out of the box — Node.js not required at runtime.
const client = axios.create({
  baseURL: "",
  timeout: 60_000,
});

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
    if (error.message) return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Request failed";
}

export const api = {
  ask: async (question: string): Promise<AnswerResponse> => {
    const { data } = await client.post("/api/ask", {
      question,
      force_synthesize: true,
    });
    return data;
  },

  search: async (
    q: string,
    limit = 10,
    page_type?: string,
  ): Promise<SearchResponse> => {
    const { data } = await client.get("/api/search", {
      params: { q, limit, page_type },
    });
    return data;
  },

  overview: async (): Promise<OverviewResponse> => {
    const { data } = await client.get("/api/overview");
    return data;
  },

  project: async (): Promise<ProjectResponse> => {
    const { data } = await client.get("/api/project");
    return data;
  },

  graph: async (): Promise<GraphResponse> => {
    const { data } = await client.get("/api/graph");
    return data;
  },

  context: async (
    targets: string[],
    include = ["docs", "freshness"],
    compact = true,
  ): Promise<ContextResponse> => {
    const { data } = await client.post("/api/context", {
      targets,
      include,
      compact,
    });
    return data;
  },

  risk: async (
    targets: string[],
    changed_files?: string[],
  ): Promise<RiskResponse> => {
    const { data } = await client.post("/api/risk", {
      targets,
      changed_files,
    });
    return data;
  },

  riskOverview: async (): Promise<RiskOverviewResponse> => {
    const { data } = await client.get("/api/risk/overview");
    return data;
  },

  deadCode: async (params: {
    kind?: string;
    min_confidence?: number;
    safe_only?: boolean;
    group_by?: string;
  }): Promise<DeadCodeResponse> => {
    const { data } = await client.post("/api/dead-code", params);
    return data;
  },

  model: (): Promise<ModelResponse> =>
    client.get('/api/model').then(r => r.data),

  pages: (params?: { limit?: number; offset?: number; page_type?: string; freshness?: string; q?: string }): Promise<PageListResponse> =>
    client.get('/api/pages', { params }).then(r => r.data),

  pageDetail: (id: number | string): Promise<PageDetailResponse> =>
    client.get(`/api/pages/${id}`).then(r => r.data),

  repairCandidates: (params?: { limit?: number; weak_threshold?: number; min_retrievals?: number }): Promise<RepairCandidatesResponse> =>
    client.get('/api/repair/candidates', { params }).then(r => r.data),

  repairRun: (body: RepairRunRequest): Promise<RepairRunResponse> =>
    client.post('/api/repair/run', body).then(r => r.data),

  blastRadius: (files: string[], max_depth: number = 3): Promise<BlastRadiusResponse> =>
    client.post('/api/blast-radius', { files, max_depth }).then(r => r.data),

  decisions: (status?: string): Promise<DecisionsResponse> =>
    client.get('/api/decisions', { params: status ? { status } : {} }).then(r => r.data),

  riskHeatmap: (): Promise<RiskHeatmapResponse> =>
    client.get('/api/risk/heatmap').then(r => r.data),
};
