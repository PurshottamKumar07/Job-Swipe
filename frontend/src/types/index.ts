// ---------------------------------------------------------------------------
// TypeScript interfaces matching the FastAPI backend schemas
// ---------------------------------------------------------------------------

export interface RunResponse {
  id: number;
  run_type: string;
  seed_urls: string | null;
  max_pages: number | null;
  pages_crawled: number;
  links_inspected: number;
  errors: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  error_message?: string | null;
}

export interface RunCreatedResponse {
  run_id: number;
  status: string;
  message: string;
}

export interface JobLinkResponse {
  id: number;
  crawl_run_id: number;
  url: string;
  anchor_text: string | null;
  found_on: string | null;
  match_reason: string | null;
  discovered_at: string;
}

export interface ExtractedJobResponse {
  id: number;
  crawl_run_id: number | null;
  source_job_link_id: number | null;
  source_url: string;
  title: string | null;
  company: string | null;
  location: string | null;
  salary: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  job_type: string | null;
  is_remote: boolean;
  description: string | null;
  apply_url: string | null;
  posted_at: string | null;
  extraction_method: string | null;
  extracted_at: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  is_active: boolean;
  apply_status?: string;
  applied_at?: string | null;
  apply_notes?: string | null;
}

export interface AutoApplyMatchResponse {
  job_id: number;
  job_title: string;
  company: string;
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];
  all_user_skills: string[];
  recommended_projects: Array<{
    id?: string;
    title: string;
    tags?: string[];
    bullets?: string[];
    link?: string;
  }>;
  cover_letter_preview: string;
}

export interface AutoApplySessionResponse {
  id: number | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  total_jobs: number;
  applied_jobs: number;
  failed_jobs: number;
  skipped_jobs: number;
  current_job_id: number | null;
  current_job: ExtractedJobResponse | null;
  pause_data: {
    type: "skill_review" | "captcha";
    job_id?: number;
    job_title?: string;
    company?: string;
    location?: string;
    match_score?: number;
    matched_skills?: string[];
    missing_skills?: string[];
    all_user_skills?: string[];
    apply_url?: string;
    details?: string;
    cover_letter?: string;
  } | null;
  daily_applied_today: number;
  daily_cap: number;
}

export interface AutoApplyLogResponse {
  id: number;
  session_id: number | null;
  job_id: number | null;
  title: string | null;
  company: string | null;
  timestamp: string;
  event_type: string;
  message: string;
  metadata?: string | null;
}

export interface AutoApplyStartRequest {
  job_ids?: number[];
  max_applications?: number;
}

export interface AutoApplyActionRequest {
  action: "approve" | "skip" | "solved_captcha";
  approved_skills?: string[];
}

export interface StatsResponse {
  total_crawl_runs: number;
  total_job_links: number;
  total_extracted_jobs: number;
  active_jobs: number;
  remote_jobs: number;
  unique_companies: number;
  by_method: Record<string, number>;
  top_companies: Record<string, number>;
}

export interface PaginatedJobLinks {
  total: number;
  limit: number;
  offset: number;
  items: JobLinkResponse[];
}

export interface PaginatedJobs {
  total: number;
  limit: number;
  offset: number;
  items: ExtractedJobResponse[];
}

export interface SeedsResponse {
  urls: string[];
  file_path: string;
}

export interface JobAlert {
  id: number;
  keyword: string;
  location?: string | null;
  frequency: string;
  email: string;
  is_active: boolean;
  created_at: string;
  last_sent_at?: string | null;
  match_count: number;
}

export interface JobAlertCreate {
  keyword: string;
  location?: string;
  frequency?: string;
  email: string;
}

export interface AnalyticsResponse {
  total_jobs: number;
  active_jobs: number;
  remote_jobs: number;
  total_crawl_runs: number;
  total_job_links: number;
  unique_companies: number;
  funnel: {
    unapplied: number;
    pending_approval: number;
    applied: number;
    interview: number;
    offer: number;
    rejected: number;
    skipped: number;
    failed: number;
  };
  daily_applications: { date: string; count: number }[];
  by_method: Record<string, number>;
  top_companies: {
    company: string;
    total_jobs: number;
    remote_count: number;
    applied_count: number;
  }[];
  salary_stats: {
    avg_min: number | null;
    avg_max: number | null;
    disclosed_count: number;
  };
  top_locations: { location: string; count: number }[];
}

// ---------------------------------------------------------------------------
// Client-side types (localStorage-backed features)
// ---------------------------------------------------------------------------

export type ApplicationStatus =
  | "applied"
  | "in_progress"
  | "interview"
  | "offer"
  | "rejected";

export interface Application {
  job_id: number;
  company: string;
  role: string;
  status: ApplicationStatus;
  applied_on: string;
  notes?: string;
}

export interface CrawlRequest {
  seed_urls: string[];
  max_pages?: number;
  concurrency?: number;
  delay?: number;
  timeout?: number;
  respect_robots?: boolean;
}

export interface ExtractRequest {
  crawl_run_id: number;
  concurrency?: number;
  timeout?: number;
}

export interface FreeJobsRequest {
  source?: "remotive" | "himalayas" | "all";
  search?: string;
  category?: string;
  limit?: number;
}

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

