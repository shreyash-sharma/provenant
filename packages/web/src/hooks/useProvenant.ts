import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    retry: false,
  });
}

export function useAsk() {
  return useMutation({
    mutationFn: (question: string) => api.ask(question),
  });
}

export function useSearch(q: string, pageType: string, enabled: boolean) {
  return useQuery({
    queryKey: ["search", q, pageType],
    queryFn: () => api.search(q, 20, pageType || undefined),
    enabled,
    retry: false,
  });
}

export function useRiskOverview() {
  return useQuery({
    queryKey: ["risk-overview"],
    queryFn: api.riskOverview,
    retry: false,
  });
}

export function useDeadCode(safeOnly: boolean) {
  return useQuery({
    queryKey: ["dead-code", safeOnly],
    queryFn: () => api.deadCode({ safe_only: safeOnly, group_by: "directory" }),
    retry: false,
  });
}

