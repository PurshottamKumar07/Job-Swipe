import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format salary range for display.
 * Returns e.g. "₹14 – 20 LPA" or "$120K – $150K / year"
 */
export function formatSalary(job: {
  salary?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  salary_period?: string | null;
}): string | null {
  // If there's a raw salary string, prefer it
  if (job.salary) return job.salary;

  if (job.salary_min == null && job.salary_max == null) return null;

  const cur = job.salary_currency || "";
  const period = job.salary_period ? ` / ${job.salary_period}` : "";

  const fmt = (n: number) => {
    if (n >= 100000) return `${(n / 100000).toFixed(n % 100000 === 0 ? 0 : 1)} LPA`;
    if (n >= 1000) return `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}K`;
    return n.toLocaleString();
  };

  if (job.salary_min != null && job.salary_max != null) {
    return `${cur}${fmt(job.salary_min)} – ${cur}${fmt(job.salary_max)}${period}`;
  }
  if (job.salary_min != null) return `${cur}${fmt(job.salary_min)}+${period}`;
  return `Up to ${cur}${fmt(job.salary_max!)}${period}`;
}

/**
 * Relative time string e.g. "2 hours ago"
 */
export function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;

  const secs = Math.floor(diff / 1000);
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

