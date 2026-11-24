"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { getSavedJobIds, toggleSavedJob } from "@/lib/storage";
import { getJob } from "@/lib/api";
import { formatSalary } from "@/lib/utils";
import type { ExtractedJobResponse } from "@/types";
import {
  Bookmark,
  MapPin,
  Briefcase,
  ExternalLink,
  Trash2,
  Send,
  Plus,
} from "lucide-react";

export default function SavedJobsPage() {
  const [savedJobs, setSavedJobs] = useState<ExtractedJobResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadSaved() {
      const ids = getSavedJobIds();
      if (ids.length === 0) {
        setLoading(false);
        return;
      }

      const fetched: ExtractedJobResponse[] = [];
      for (const id of ids) {
        try {
          const j = await getJob(id);
          fetched.push(j);
        } catch {
          // job might have been pruned
        }
      }
      setSavedJobs(fetched);
      setLoading(false);
    }

    loadSaved();
  }, []);

  const handleRemove = (id: number) => {
    toggleSavedJob(id);
    setSavedJobs((prev) => prev.filter((j) => j.id !== id));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">Saved Jobs</h1>
        <p className="text-gray-400 text-sm mt-1">
          Positions you bookmarked while swiping or exploring listings.
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-44 rounded-xl bg-[#1a1130] border border-purple-900/30 animate-pulse p-4"
            />
          ))}
        </div>
      ) : savedJobs.length === 0 ? (
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-12 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-blue-600/20 flex items-center justify-center text-blue-400 mx-auto">
            <Bookmark className="h-6 w-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg text-white">No saved jobs yet</h3>
            <p className="text-gray-400 text-sm mt-1 max-w-sm mx-auto">
              Tap the bookmark icon on any job card to save it for later review.
            </p>
          </div>
          <Link
            href="/swipe"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-medium text-sm transition-colors min-h-[44px]"
          >
            <Plus className="h-4 w-4" /> Start Swiping Jobs
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {savedJobs.map((job) => {
            const sal = formatSalary(job);
            return (
              <div
                key={job.id}
                className="flex flex-col justify-between rounded-xl bg-[#1a1130] border border-purple-900/40 p-5 hover:border-purple-600/70 transition-all"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-tr from-purple-700 to-indigo-600 flex items-center justify-center font-bold text-white text-base">
                        {job.company ? job.company.charAt(0).toUpperCase() : "J"}
                      </div>
                      <div>
                        <span className="text-xs text-gray-400 font-medium">
                          {job.company || "Company"}
                        </span>
                        <h3 className="font-semibold text-white line-clamp-1">
                          {job.title || "Job Listing"}
                        </h3>
                      </div>
                    </div>

                    <button
                      onClick={() => handleRemove(job.id)}
                      aria-label="Remove from saved"
                      className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mt-4 text-xs text-gray-300">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3 text-purple-400" />
                      {job.is_remote ? "Remote" : job.location || "Flexible"}
                    </span>
                    {job.job_type && (
                      <span className="flex items-center gap-1">
                        <Briefcase className="h-3 w-3 text-indigo-400" />
                        {job.job_type}
                      </span>
                    )}
                  </div>

                  {sal && (
                    <div className="mt-3 inline-block text-xs font-semibold px-2.5 py-1 rounded-md bg-emerald-950/40 border border-emerald-800/40 text-emerald-300">
                      {sal}
                    </div>
                  )}
                </div>

                <div className="mt-5 pt-3 border-t border-purple-900/30 flex items-center justify-between">
                  <Link
                    href={`/jobs/${job.id}`}
                    className="text-xs text-purple-400 hover:underline font-medium inline-flex items-center gap-1"
                  >
                    View Details <ExternalLink className="h-3 w-3" />
                  </Link>

                  <a
                    href={job.apply_url || job.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold transition-colors"
                  >
                    <Send className="h-3 w-3" /> Apply
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

