// ---------------------------------------------------------------------------
// localStorage helpers for saved jobs, applications, and swipe state
// ---------------------------------------------------------------------------

import type { Application, ApplicationStatus } from "@/types";

const SAVED_KEY = "jobswipe_saved";
const APPS_KEY = "jobswipe_applications";
const SWIPED_KEY = "jobswipe_swiped";

// ── Saved Jobs ──────────────────────────────────────────────────────────────

export function getSavedJobIds(): number[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]");
  } catch {
    return [];
  }
}

export function toggleSavedJob(id: number): boolean {
  const ids = getSavedJobIds();
  const idx = ids.indexOf(id);
  if (idx >= 0) {
    ids.splice(idx, 1);
    localStorage.setItem(SAVED_KEY, JSON.stringify(ids));
    return false; // removed
  }
  ids.push(id);
  localStorage.setItem(SAVED_KEY, JSON.stringify(ids));
  return true; // added
}

export function isJobSaved(id: number): boolean {
  return getSavedJobIds().includes(id);
}

// ── Applications ────────────────────────────────────────────────────────────

export function getApplications(): Application[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(APPS_KEY) || "[]");
  } catch {
    return [];
  }
}

export function addApplication(app: Application): void {
  const apps = getApplications();
  const existing = apps.findIndex((a) => a.job_id === app.job_id);
  if (existing >= 0) {
    apps[existing] = app;
  } else {
    apps.push(app);
  }
  localStorage.setItem(APPS_KEY, JSON.stringify(apps));
}

export function updateApplicationStatus(
  jobId: number,
  status: ApplicationStatus
): void {
  const apps = getApplications();
  const app = apps.find((a) => a.job_id === jobId);
  if (app) {
    app.status = status;
    localStorage.setItem(APPS_KEY, JSON.stringify(apps));
  }
}

export function removeApplication(jobId: number): void {
  const apps = getApplications().filter((a) => a.job_id !== jobId);
  localStorage.setItem(APPS_KEY, JSON.stringify(apps));
}

export function getApplicationByJobId(
  jobId: number
): Application | undefined {
  return getApplications().find((a) => a.job_id === jobId);
}

// ── Swiped (skip tracking for swipe view) ───────────────────────────────────

export function getSwipedIds(): number[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(SWIPED_KEY) || "[]");
  } catch {
    return [];
  }
}

export function markSwiped(id: number): void {
  const ids = getSwipedIds();
  if (!ids.includes(id)) {
    ids.push(id);
    localStorage.setItem(SWIPED_KEY, JSON.stringify(ids));
  }
}

export function resetSwiped(): void {
  localStorage.removeItem(SWIPED_KEY);
}

