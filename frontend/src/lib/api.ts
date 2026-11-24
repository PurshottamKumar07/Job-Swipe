// ---------------------------------------------------------------------------
// API client for the crwlr FastAPI backend
// ---------------------------------------------------------------------------

import type {
  RunResponse,
  RunCreatedResponse,
  PaginatedJobLinks,
  PaginatedJobs,
  ExtractedJobResponse,
  StatsResponse,
  SeedsResponse,
  CrawlRequest,
  ExtractRequest,
  JobAlert,
  JobAlertCreate,
  AnalyticsResponse,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Health ──────────────────────────────────────────────────────────────────

export const healthCheck = () => request<{ status: string }>("/health");

// ── Stats ───────────────────────────────────────────────────────────────────

export const getStats = () => request<StatsResponse>("/api/stats");

// ── Runs ────────────────────────────────────────────────────────────────────

export const listRuns = () => request<RunResponse[]>("/api/runs");

export const getRun = (id: number) =>
  request<RunResponse>(`/api/runs/${id}`);

export const startCrawl = (data: CrawlRequest) =>
  request<RunCreatedResponse>("/api/crawl", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const startExtract = (data: ExtractRequest) =>
  request<RunCreatedResponse>("/api/extract", {
    method: "POST",
    body: JSON.stringify(data),
  });

// ── Links ───────────────────────────────────────────────────────────────────

export interface LinksParams {
  run_id?: number;
  limit?: number;
  offset?: number;
}

export const listLinks = (params: LinksParams = {}) => {
  const qs = new URLSearchParams();
  if (params.run_id != null) qs.set("run_id", String(params.run_id));
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<PaginatedJobLinks>(`/api/links${q ? `?${q}` : ""}`);
};

// ── Jobs ────────────────────────────────────────────────────────────────────

export interface JobsParams {
  company?: string;
  method?: string;
  is_remote?: boolean;
  min_salary?: number;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}

export const listJobs = (params: JobsParams = {}) => {
  const qs = new URLSearchParams();
  if (params.company) qs.set("company", params.company);
  if (params.method) qs.set("method", params.method);
  if (params.is_remote != null)
    qs.set("is_remote", String(params.is_remote));
  if (params.min_salary != null)
    qs.set("min_salary", String(params.min_salary));
  if (params.active_only != null)
    qs.set("active_only", String(params.active_only));
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<PaginatedJobs>(`/api/jobs${q ? `?${q}` : ""}`);
};

export const getJob = (id: number) =>
  request<ExtractedJobResponse>(`/api/jobs/${id}`);

export interface SearchParams {
  q: string;
  is_remote?: boolean;
  min_salary?: number;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}

export const searchJobs = (params: SearchParams) => {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.is_remote != null)
    qs.set("is_remote", String(params.is_remote));
  if (params.min_salary != null)
    qs.set("min_salary", String(params.min_salary));
  if (params.active_only != null)
    qs.set("active_only", String(params.active_only));
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  return request<PaginatedJobs>(`/api/jobs/search?${qs.toString()}`);
};

// ── Seeds ───────────────────────────────────────────────────────────────────

export const getSeeds = () => request<SeedsResponse>("/api/seeds");

export const updateSeeds = (urls: string[]) =>
  request<SeedsResponse>("/api/seeds", {
    method: "PUT",
    body: JSON.stringify({ urls }),
  });

export const importExistingData = () =>
  request<{
    success: boolean;
    imported_links: number;
    imported_jobs: number;
    message: string;
  }>("/api/import-existing", {
    method: "POST",
  });

// ── Adzuna API ───────────────────────────────────────────────────────────────

export interface AdzunaRequest {
  query: string;
  country?: string;
  where?: string;
  pages?: number;
  salary_min?: number;
  salary_max?: number;
  full_time?: boolean;
  max_days_old?: number;
  concurrency?: number;
}

export const startAdzunaFetch = (params: AdzunaRequest) =>
  request<RunCreatedResponse>("/api/adzuna", {
    method: "POST",
    body: JSON.stringify(params),
  });

// ── Free Jobs API (Remotive + Himalayas) ─────────────────────────────────────

export interface FreeJobsRequest {
  source?: "remotive" | "himalayas" | "all";
  search?: string;
  category?: string;
  limit?: number;
}

export function startFreeJobsFetch(params: FreeJobsRequest) {
  return request<RunCreatedResponse>("/api/free-jobs", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ── JobSpy Multi-Board Scraper ───────────────────────────────────────────────

export interface JobSpyRequest {
  search_term?: string;
  location?: string;
  sites?: string[];
  results_wanted?: number;
  hours_old?: number;
  is_remote?: boolean;
  job_type?: string;
  country_indeed?: string;
  fetch_description?: boolean;
}

export function startJobSpyScrape(params: JobSpyRequest) {
  return request<RunCreatedResponse>("/api/jobspy", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ── Auto-Apply (Playwright Automation) ──────────────────────────────────────

import type {
  AutoApplyMatchResponse,
  AutoApplySessionResponse,
  AutoApplyLogResponse,
  AutoApplyStartRequest,
  AutoApplyActionRequest,
} from "@/types";

export function getAutoApplyProfile() {
  return request<any>("/api/auto-apply/profile");
}

export function updateAutoApplyProfile(data: any) {
  return request<{ success: boolean; message: string }>("/api/auto-apply/profile", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function getJobMatch(jobId: number) {
  return request<AutoApplyMatchResponse>(`/api/auto-apply/match/${jobId}`, {
    method: "POST",
  });
}

export function startAutoApply(params: AutoApplyStartRequest = {}) {
  return request<{ success: boolean; message: string }>("/api/auto-apply/start", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function startSingleJobApply(jobId: number) {
  return request<{ success: boolean; message: string }>(`/api/auto-apply/single/${jobId}`, {
    method: "POST",
  });
}

export function getAutoApplySession() {
  return request<AutoApplySessionResponse>("/api/auto-apply/session");
}

export function submitAutoApplyAction(params: AutoApplyActionRequest) {
  return request<{ success: boolean; action: string; message: string }>("/api/auto-apply/action", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function stopAutoApplySession() {
  return request<{ success: boolean; message: string }>("/api/auto-apply/stop", {
    method: "POST",
  });
}

export function getAutoApplyLogs(limit: number = 50) {
  return request<AutoApplyLogResponse[]>(`/api/auto-apply/logs?limit=${limit}`);
}

// ── Analytics & Alerts ─────────────────────────────────────────────────────

export function getAnalytics() {
  return request<AnalyticsResponse>("/api/analytics");
}

export function getAlerts() {
  return request<JobAlert[]>("/api/alerts");
}

export function createAlert(params: JobAlertCreate) {
  return request<JobAlert>("/api/alerts", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function toggleAlert(alertId: number) {
  return request<{ success: boolean; id: number; is_active: boolean; message: string }>(
    `/api/alerts/${alertId}/toggle`,
    { method: "PATCH" }
  );
}

export function deleteAlert(alertId: number) {
  return request<{ success: boolean; message: string }>(`/api/alerts/${alertId}`, {
    method: "DELETE",
  });
}

export function getAlertMatches(alertId: number, limit: number = 20) {
  return request<ExtractedJobResponse[]>(`/api/alerts/${alertId}/matches?limit=${limit}`);
}

// ── Qwen2.5-3B-Instruct Resume Maker ──────────────────────────────────────

export function tailorResume(jobId: number) {
  return request<{
    job_id: number;
    job_title: string;
    company: string;
    match_score: number;
    matched_skills: string[];
    missing_skills: string[];
    tailored_summary: string;
    tailored_experience: any[];
    cover_letter: string;
    model_used: string;
  }>(`/api/auto-apply/tailor/${jobId}`, { method: "POST" });
}

export function generateResumeDocument(jobId: number, useAi: boolean = true) {
  return request<{
    job_id: number;
    job_title: string;
    company: string;
    pdf_filename: string;
    pdf_url: string;
    tex_filename: string;
    tex_url: string;
    summary_used: string;
    cover_letter: string;
  }>(`/api/auto-apply/generate-resume/${jobId}?use_ai=${useAi}`, { method: "POST" });
}




