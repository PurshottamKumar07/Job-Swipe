"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useJobs } from "@/lib/hooks";
import { formatSalary } from "@/lib/utils";
import {
  getSwipedIds,
  markSwiped,
  toggleSavedJob,
  isJobSaved,
  addApplication,
  resetSwiped,
} from "@/lib/storage";
import {
  X,
  Bookmark,
  Heart,
  MapPin,
  Briefcase,
  ExternalLink,
  RotateCcw,
  Sparkles,
  SlidersHorizontal,
  CheckCircle2,
} from "lucide-react";

export default function SwipePage() {
  const [filterRemote, setFilterRemote] = useState<boolean | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [swipedLocal, setSwipedLocal] = useState<number[]>(() => getSwipedIds());
  const [animationClass, setAnimationClass] = useState<string>("");
  const [savedStatus, setSavedStatus] = useState<Record<number, boolean>>({});

  const { data, isLoading, error } = useJobs({
    is_remote: filterRemote ?? undefined,
    limit: 100,
    active_only: true,
  });

  const availableJobs = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter((job) => !swipedLocal.includes(job.id));
  }, [data?.items, swipedLocal]);

  const currentJob = availableJobs[0];

  const handleSkip = () => {
    if (!currentJob) return;
    setAnimationClass("translate-x-[-120%] rotate-[-15deg] opacity-0");
    setTimeout(() => {
      markSwiped(currentJob.id);
      setSwipedLocal((prev) => [...prev, currentJob.id]);
      setAnimationClass("");
    }, 250);
  };

  const handleSave = () => {
    if (!currentJob) return;
    const isNowSaved = toggleSavedJob(currentJob.id);
    setSavedStatus((prev) => ({ ...prev, [currentJob.id]: isNowSaved }));
  };

  const handleApply = () => {
    if (!currentJob) return;
    addApplication({
      job_id: currentJob.id,
      company: currentJob.company || "Unknown Company",
      role: currentJob.title || "Job Listing",
      status: "applied",
      applied_on: new Date().toISOString().slice(0, 10),
    });

    setAnimationClass("translate-x-[120%] rotate-[15deg] opacity-0");
    setTimeout(() => {
      markSwiped(currentJob.id);
      setSwipedLocal((prev) => [...prev, currentJob.id]);
      setAnimationClass("");

      const targetUrl = currentJob.apply_url || currentJob.source_url;
      if (targetUrl) {
        window.open(targetUrl, "_blank", "noopener,noreferrer");
      }
    }, 250);
  };

  const handleReset = () => {
    resetSwiped();
    setSwipedLocal([]);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">Swipe Jobs</h1>
        <p className="text-gray-400 text-sm mt-1">
          Like Tinder, but for your career! Swipe right or tap Apply to advance.
        </p>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none text-xs sm:text-sm">
        <button
          onClick={() => {
            setFilterRemote(null);
            setActiveCategory("all");
          }}
          className={`px-3 py-1.5 rounded-full border transition-colors flex items-center gap-1.5 whitespace-nowrap min-h-[38px] ${
            activeCategory === "all"
              ? "bg-purple-600 border-purple-500 text-white"
              : "border-purple-900/60 bg-[#1a1130] text-gray-300 hover:border-purple-600"
          }`}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" /> All Jobs
        </button>
        <button
          onClick={() => {
            setFilterRemote(true);
            setActiveCategory("remote");
          }}
          className={`px-3 py-1.5 rounded-full border transition-colors whitespace-nowrap min-h-[38px] ${
            activeCategory === "remote"
              ? "bg-purple-600 border-purple-500 text-white"
              : "border-purple-900/60 bg-[#1a1130] text-gray-300 hover:border-purple-600"
          }`}
        >
          🌍 Remote Only
        </button>
        <button
          onClick={() => {
            setFilterRemote(false);
            setActiveCategory("onsite");
          }}
          className={`px-3 py-1.5 rounded-full border transition-colors whitespace-nowrap min-h-[38px] ${
            activeCategory === "onsite"
              ? "bg-purple-600 border-purple-500 text-white"
              : "border-purple-900/60 bg-[#1a1130] text-gray-300 hover:border-purple-600"
          }`}
        >
          🏢 On-site / Hybrid
        </button>
      </div>

      {/* Card area */}
      {isLoading ? (
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-8 text-center min-h-[420px] flex flex-col items-center justify-center space-y-4">
          <div className="h-12 w-12 rounded-full border-4 border-purple-500 border-t-transparent animate-spin" />
          <p className="text-gray-400 text-sm">Fetching discovered opportunities...</p>
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-900/40 bg-[#1a1130] p-8 text-center space-y-4">
          <p className="text-red-400">Failed to load jobs from API.</p>
          <p className="text-xs text-gray-500">Ensure crwlr backend is running on http://localhost:8000</p>
        </div>
      ) : !currentJob ? (
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-10 text-center space-y-5">
          <div className="mx-auto w-16 h-16 rounded-full bg-purple-600/20 flex items-center justify-center text-purple-400">
            <Sparkles className="h-8 w-8" />
          </div>
          <div>
            <h3 className="text-xl font-bold">You’re all caught up!</h3>
            <p className="text-gray-400 text-sm mt-1 max-w-sm mx-auto">
              You’ve reviewed all available jobs in this filter or crawl queue.
            </p>
          </div>
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-medium text-sm transition-colors min-h-[44px]"
          >
            <RotateCcw className="h-4 w-4" /> Reset Swiped Jobs
          </button>
        </div>
      ) : (
        <div className="relative">
          {/* Deck background effect */}
          {availableJobs.length > 1 && (
            <div className="absolute inset-0 translate-y-3 scale-[0.96] rounded-2xl bg-[#140c26] border border-purple-900/30 -z-10" />
          )}

          {/* Active Card */}
          <div
            className={`rounded-2xl border border-purple-800/40 bg-[#1a1130] shadow-2xl p-6 sm:p-8 transition-all duration-300 transform ${animationClass}`}
          >
            {/* Top row: Company icon & title & save toggle */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-purple-700 to-indigo-600 flex items-center justify-center font-bold text-lg text-white shadow-md">
                  {currentJob.company ? currentJob.company.charAt(0).toUpperCase() : "J"}
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-base sm:text-lg text-white">
                      {currentJob.company || "Direct Listing"}
                    </span>
                    <CheckCircle2 className="h-4 w-4 text-purple-400 inline" />
                  </div>
                  <h2 className="text-lg sm:text-xl font-bold text-white mt-0.5">
                    {currentJob.title || "Job Opening"}
                  </h2>
                </div>
              </div>

              <button
                onClick={handleSave}
                aria-label="Save Job"
                className={`p-2.5 rounded-xl border transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center ${
                  savedStatus[currentJob.id] || isJobSaved(currentJob.id)
                    ? "bg-purple-600/30 border-purple-500 text-purple-300"
                    : "border-purple-900/50 hover:bg-purple-900/20 text-gray-400"
                }`}
              >
                <Bookmark className="h-5 w-5" />
              </button>
            </div>

            {/* Badges & Meta */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mt-4 text-xs sm:text-sm text-gray-300">
              <span className="inline-flex items-center gap-1 bg-[#251744] px-3 py-1 rounded-full border border-purple-900/50">
                <MapPin className="h-3.5 w-3.5 text-purple-400" />
                {currentJob.is_remote
                  ? "Remote"
                  : currentJob.location || "Location Flexible"}
              </span>

              {currentJob.job_type && (
                <span className="inline-flex items-center gap-1 bg-[#251744] px-3 py-1 rounded-full border border-purple-900/50">
                  <Briefcase className="h-3.5 w-3.5 text-indigo-400" />
                  {currentJob.job_type}
                </span>
              )}

              {formatSalary(currentJob) && (
                <span className="bg-emerald-950/40 text-emerald-300 border border-emerald-800/40 px-3 py-1 rounded-full font-medium">
                  💰 {formatSalary(currentJob)}
                </span>
              )}
            </div>

            {/* Snippet / Description */}
            <div className="mt-5 text-sm text-gray-300/90 leading-relaxed max-h-48 overflow-y-auto pr-1">
              <p className="line-clamp-4 whitespace-pre-line">
                {currentJob.description
                  ? currentJob.description.slice(0, 320) + (currentJob.description.length > 320 ? "..." : "")
                  : "No extended description provided. Check official job posting link for full qualifications and application requirements."}
              </p>
            </div>

            {/* Link to details */}
            <div className="mt-5 pt-4 border-t border-purple-900/30 flex justify-between items-center text-xs text-gray-400">
              <span>{availableJobs.length} jobs remaining</span>
              <Link
                href={`/jobs/${currentJob.id}`}
                className="text-purple-400 hover:text-purple-300 font-medium inline-flex items-center gap-1 hover:underline"
              >
                View Details <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>

          {/* Swipe Buttons Bar */}
          <div className="flex items-center justify-center gap-6 mt-8">
            {/* Skip */}
            <button
              onClick={handleSkip}
              aria-label="Skip"
              className="w-16 h-16 rounded-full bg-[#1e1338] border-2 border-red-500/40 hover:border-red-500 hover:bg-red-500/10 text-red-400 flex items-center justify-center transition-all duration-200 shadow-lg hover:scale-105 active:scale-95"
            >
              <X className="h-7 w-7" />
            </button>

            {/* Save */}
            <button
              onClick={handleSave}
              aria-label="Save for later"
              className={`w-14 h-14 rounded-full bg-[#1e1338] border-2 transition-all duration-200 flex items-center justify-center shadow-lg hover:scale-105 active:scale-95 ${
                savedStatus[currentJob.id] || isJobSaved(currentJob.id)
                  ? "border-blue-400 bg-blue-500/20 text-blue-300"
                  : "border-blue-500/40 hover:border-blue-400 text-blue-400"
              }`}
            >
              <Bookmark className="h-6 w-6" />
            </button>

            {/* Apply (Swipe Right) */}
            <button
              onClick={handleApply}
              aria-label="Apply Now"
              className="w-16 h-16 rounded-full bg-[#1e1338] border-2 border-emerald-500/50 hover:border-emerald-400 hover:bg-emerald-500/10 text-emerald-400 flex items-center justify-center transition-all duration-200 shadow-lg hover:scale-105 active:scale-95"
            >
              <Heart className="h-7 w-7 fill-emerald-400/20" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

