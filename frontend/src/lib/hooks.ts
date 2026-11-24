// ---------------------------------------------------------------------------
// SWR hooks for data fetching
// ---------------------------------------------------------------------------

"use client";

import useSWR from "swr";
import * as api from "./api";
import type { JobsParams, SearchParams, LinksParams } from "./api";

// Generic fetcher wrapper
const swrOpts = { revalidateOnFocus: false, dedupingInterval: 5000 };

export function useStats() {
  return useSWR("stats", () => api.getStats(), swrOpts);
}

export function useRuns() {
  return useSWR("runs", () => api.listRuns(), {
    ...swrOpts,
    refreshInterval: 10000, // poll runs for status updates
  });
}

export function useRun(id: number | null) {
  return useSWR(id != null ? `run-${id}` : null, () => api.getRun(id!), {
    ...swrOpts,
    refreshInterval: 5000,
  });
}

export function useJobs(params: JobsParams = {}) {
  const key = `jobs-${JSON.stringify(params)}`;
  return useSWR(key, () => api.listJobs(params), swrOpts);
}

export function useJob(id: number | null) {
  return useSWR(id != null ? `job-${id}` : null, () => api.getJob(id!), swrOpts);
}

export function useSearchJobs(params: SearchParams | null) {
  const key = params ? `search-${JSON.stringify(params)}` : null;
  return useSWR(key, () => api.searchJobs(params!), swrOpts);
}

export function useLinks(params: LinksParams = {}) {
  const key = `links-${JSON.stringify(params)}`;
  return useSWR(key, () => api.listLinks(params), swrOpts);
}

export function useSeeds() {
  return useSWR("seeds", () => api.getSeeds(), swrOpts);
}

export function useAnalytics() {
  return useSWR("analytics", () => api.getAnalytics(), {
    ...swrOpts,
    refreshInterval: 15000,
  });
}

export function useAlerts() {
  return useSWR("alerts", () => api.getAlerts(), swrOpts);
}


