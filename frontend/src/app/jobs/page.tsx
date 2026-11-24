"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useJobs, useSearchJobs } from "@/lib/hooks";
import { formatSalary, timeAgo } from "@/lib/utils";
import { toggleSavedJob, isJobSaved } from "@/lib/storage";
import {
  Search,
  MapPin,
  Briefcase,
  Bookmark,
  CheckCircle2,
  ExternalLink,
  Filter,
} from "lucide-react";

export default function JobsPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [, startTransition] = useTransition();

  const [remoteOnly, setRemoteOnly] = useState(false);
  const [activeOnly, setActiveOnly] = useState(true);
  const [page, setPage] = useState(0);
  const [savedMap, setSavedMap] = useState<Record<number, boolean>>({});

  const limit = 20;

  const handleSearchChange = (val: string) => {
    setSearchTerm(val);
    startTransition(() => {
      setDebouncedQuery(val.trim());
      setPage(0);
    });
  };

  // If debouncedQuery has content, use searchJobs; else listJobs
  const searchResult = useSearchJobs(
    debouncedQuery.length > 0
      ? {
          q: debouncedQuery,
          is_remote: remoteOnly ? true : undefined,
          active_only: activeOnly,
          limit,
          offset: page * limit,
        }
      : null
  );

  const listResult = useJobs(
    debouncedQuery.length === 0
      ? {
          is_remote: remoteOnly ? true : undefined,
          active_only: activeOnly,
          limit,
          offset: page * limit,
        }
      : {}
  );

  const activeData = debouncedQuery.length > 0 ? searchResult.data : listResult.data;
  const isLoading = debouncedQuery.length > 0 ? searchResult.isLoading : listResult.isLoading;
  const error = debouncedQuery.length > 0 ? searchResult.error : listResult.error;

  const handleSaveToggle = (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const res = toggleSavedJob(id);
    setSavedMap((prev) => ({ ...prev, [id]: res }));
  };

  const total = activeData?.total ?? 0;
  const items = activeData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">Browse Jobs</h1>
        <p className="text-gray-400 text-sm mt-1">
          Explore all parsed opportunities discovered by the crawler.
        </p>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search by title, company, skills, or location..."
            className="w-full rounded-xl bg-[#1a1130] border border-purple-900/50 pl-10 pr-4 py-3 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setRemoteOnly(!remoteOnly);
              setPage(0);
            }}
            className={`px-3.5 py-2.5 rounded-xl border text-sm font-medium transition-colors flex items-center gap-2 min-h-[44px] ${
              remoteOnly
                ? "bg-purple-600 border-purple-500 text-white"
                : "border-purple-900/50 bg-[#1a1130] text-gray-300 hover:border-purple-600"
            }`}
          >
            <Filter className="h-4 w-4" />
            {remoteOnly ? "Remote Only ✓" : "Remote Only"}
          </button>

          <button
            onClick={() => {
              setActiveOnly(!activeOnly);
              setPage(0);
            }}
            className={`px-3.5 py-2.5 rounded-xl border text-sm font-medium transition-colors min-h-[44px] ${
              activeOnly
                ? "bg-emerald-600/30 border-emerald-500 text-emerald-300"
                : "border-purple-900/50 bg-[#1a1130] text-gray-300"
            }`}
          >
            {activeOnly ? "Active Only" : "All (incl. Inactive)"}
          </button>
        </div>
      </div>

      {/* Results Count */}
      <div className="text-xs sm:text-sm text-gray-400">
        Found <span className="font-semibold text-white">{total}</span> positions
      </div>

      {/* Grid of jobs */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="h-44 rounded-xl bg-[#1a1130] border border-purple-900/30 animate-pulse p-4"
            />
          ))}
        </div>
      ) : error ? (
        <div className="p-8 rounded-xl bg-[#1a1130] border border-red-900/40 text-center">
          <p className="text-red-400">Failed to load jobs.</p>
        </div>
      ) : items.length === 0 ? (
        <div className="p-12 rounded-xl bg-[#1a1130] border border-purple-900/40 text-center space-y-2">
          <p className="text-lg font-semibold">No positions found</p>
          <p className="text-sm text-gray-400">
            Try adjusting your search query or trigger a fresh crawl.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((job) => {
            const isSaved = savedMap[job.id] || isJobSaved(job.id);
            const sal = formatSalary(job);
            return (
              <Link
                key={job.id}
                href={`/jobs/${job.id}`}
                className="group flex flex-col justify-between rounded-xl bg-[#1a1130] border border-purple-900/40 p-5 hover:border-purple-600/70 hover:shadow-lg transition-all"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-purple-700/30 border border-purple-600/40 flex items-center justify-center font-bold text-white text-base">
                        {job.company ? job.company.charAt(0).toUpperCase() : "J"}
                      </div>
                      <div>
                        <span className="text-xs text-gray-400 font-medium flex items-center gap-1">
                          {job.company || "Company"}
                          <CheckCircle2 className="h-3 w-3 text-purple-400" />
                        </span>
                        <h3 className="font-semibold text-white group-hover:text-purple-300 transition-colors line-clamp-1">
                          {job.title || "Job Opening"}
                        </h3>
                      </div>
                    </div>

                    <button
                      onClick={(e) => handleSaveToggle(job.id, e)}
                      aria-label="Save Job"
                      className={`p-2 rounded-lg border transition-colors ${
                        isSaved
                          ? "bg-purple-600/30 border-purple-500 text-purple-300"
                          : "border-purple-900/40 text-gray-400 hover:text-white"
                      }`}
                    >
                      <Bookmark className="h-4 w-4" />
                    </button>
                  </div>

                  {/* Location & Details */}
                  <div className="flex flex-wrap items-center gap-2 mt-4 text-xs text-gray-300">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3 text-purple-400" />
                      {job.is_remote ? "Remote" : job.location || "Location not specified"}
                    </span>
                    {job.job_type && (
                      <span className="flex items-center gap-1">
                        <Briefcase className="h-3 w-3 text-indigo-400" />
                        {job.job_type}
                      </span>
                    )}
                  </div>

                  {/* Salary if present */}
                  {sal && (
                    <div className="mt-3 inline-block text-xs font-semibold px-2.5 py-1 rounded-md bg-emerald-950/40 border border-emerald-800/40 text-emerald-300">
                      {sal}
                    </div>
                  )}
                </div>

                <div className="mt-5 pt-3 border-t border-purple-900/30 flex items-center justify-between text-xs text-gray-500">
                  <span>{timeAgo(job.extracted_at)}</span>
                  <span className="text-purple-400 group-hover:text-purple-300 font-medium flex items-center gap-1">
                    Details <ExternalLink className="h-3 w-3" />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between pt-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-4 py-2 rounded-lg border border-purple-900/50 bg-[#1a1130] text-sm disabled:opacity-40 disabled:cursor-not-allowed min-h-[44px]"
          >
            Previous
          </button>
          <span className="text-xs text-gray-400">
            Page {page + 1} of {Math.ceil(total / limit)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={(page + 1) * limit >= total}
            className="px-4 py-2 rounded-lg border border-purple-900/50 bg-[#1a1130] text-sm disabled:opacity-40 disabled:cursor-not-allowed min-h-[44px]"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

