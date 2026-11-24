"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useJob } from "@/lib/hooks";
import { formatSalary, timeAgo } from "@/lib/utils";
import { startSingleJobApply, generateResumeDocument } from "@/lib/api";
import {
  toggleSavedJob,
  isJobSaved,
  addApplication,
  getApplicationByJobId,
} from "@/lib/storage";
import {
  ArrowLeft,
  Bookmark,
  CheckCircle2,
  MapPin,
  Briefcase,
  ExternalLink,
  Sparkles,
  FileCheck,
  Send,
  Building2,
  Calendar,
  Layers,
  Zap,
  FileText,
  Download,
  Loader2,
} from "lucide-react";

export default function JobDetailPage() {
  const router = useRouter();
  const params = useParams();
  const rawId = typeof params?.id === "string" ? params.id : Array.isArray(params?.id) ? params.id[0] : "";
  const jobId = parseInt(rawId, 10);

  const { data: job, isLoading, error } = useJob(isNaN(jobId) ? null : jobId);
  const [activeTab, setActiveTab] = useState<
    "overview" | "requirements" | "company" | "insights"
  >("overview");
  const [isSaved, setIsSaved] = useState<boolean>(() =>
    isNaN(jobId) ? false : isJobSaved(jobId)
  );
  const [application, setApplication] = useState(() =>
    isNaN(jobId) ? undefined : getApplicationByJobId(jobId)
  );
  const [isGeneratingResume, setIsGeneratingResume] = useState(false);

  const handleDownloadResume = async () => {
    if (!job) return;
    setIsGeneratingResume(true);
    try {
      const data = await generateResumeDocument(job.id, true);
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      window.open(`${apiUrl}${data.pdf_url}`, "_blank");
    } catch (err: any) {
      alert(err.message || "Failed to generate tailored resume with Qwen2.5");
    } finally {
      setIsGeneratingResume(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 animate-pulse">
        <div className="h-6 w-32 bg-[#1a1130] rounded-lg" />
        <div className="h-44 bg-[#1a1130] rounded-2xl border border-purple-900/30" />
        <div className="h-60 bg-[#1a1130] rounded-2xl border border-purple-900/30" />
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="max-w-xl mx-auto text-center py-16 space-y-4">
        <p className="text-xl font-bold text-red-400">Job not found</p>
        <p className="text-sm text-gray-400">
          The requested job might have expired or does not exist.
        </p>
        <Link
          href="/jobs"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Jobs
        </Link>
      </div>
    );
  }

  const handleSave = () => {
    const res = toggleSavedJob(job.id);
    setIsSaved(res);
  };

  const handleAutoApply = async () => {
    try {
      await startSingleJobApply(job.id);
      router.push("/auto-apply");
    } catch (err: any) {
      alert(err.message || "Failed to initiate Auto-Apply");
    }
  };

  const handleApply = () => {
    const appData = {
      job_id: job.id,
      company: job.company || "Unknown Company",
      role: job.title || "Position",
      status: "applied" as const,
      applied_on: new Date().toISOString().slice(0, 10),
    };
    addApplication(appData);
    setApplication(appData);

    const target = job.apply_url || job.source_url;
    if (target) {
      window.open(target, "_blank", "noopener,noreferrer");
    }
  };

  const salaryDisplay = formatSalary(job);

  // Extract candidate bullet points from description
  const extractBulletPoints = (desc: string | null) => {
    if (!desc) return [];
    const lines = desc.split("\n");
    const bullets = lines
      .map((l) => l.trim())
      .filter((l) => l.startsWith("•") || l.startsWith("-") || l.startsWith("*") || /^\d+\./.test(l))
      .map((l) => l.replace(/^[•\-*]|\d+\.\s*/, "").trim());
    return bullets.length > 0 ? bullets : lines.filter((l) => l.length > 20).slice(0, 5);
  };

  const requirements = extractBulletPoints(job.description);

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-24">
      {/* Top Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/jobs"
          className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to jobs
        </Link>
        <button
          onClick={handleSave}
          className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
            isSaved
              ? "bg-purple-600/30 border-purple-500 text-purple-300"
              : "border-purple-900/40 text-gray-400 hover:text-white"
          }`}
        >
          <Bookmark className="h-4 w-4" />
          {isSaved ? "Saved" : "Save Job"}
        </button>
      </div>

      {/* Main Header Card */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 sm:p-8">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-gradient-to-tr from-purple-700 to-indigo-600 flex items-center justify-center font-bold text-2xl text-white shadow-lg shrink-0">
            {job.company ? job.company.charAt(0).toUpperCase() : "J"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-gray-300 text-base">
                {job.company || "Independent Employer"}
              </span>
              <CheckCircle2 className="h-4 w-4 text-purple-400" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-white mt-1">
              {job.title || "Job Listing"}
            </h1>

            {/* Tags row */}
            <div className="flex flex-wrap items-center gap-2.5 mt-3 text-xs sm:text-sm text-gray-300">
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5 text-purple-400" />
                {job.is_remote ? "Remote" : job.location || "Location Flexible"}
              </span>
              {job.job_type && (
                <span className="inline-flex items-center gap-1">
                  <Briefcase className="h-3.5 w-3.5 text-indigo-400" />
                  {job.job_type}
                </span>
              )}
              {salaryDisplay && (
                <span className="font-medium text-emerald-400 bg-emerald-950/40 px-2.5 py-0.5 rounded-md border border-emerald-800/40">
                  💰 {salaryDisplay}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* AI Match & Status Card */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6 pt-6 border-t border-purple-900/40">
          <div className="p-3.5 rounded-xl bg-[#231742] border border-purple-900/40 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/20 text-emerald-400 font-bold flex items-center justify-center text-sm">
              92%
            </div>
            <div>
              <p className="text-xs text-emerald-400 font-semibold flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> High Match!
              </p>
              <p className="text-xs text-gray-400 mt-0.5">Your profile matches 5 core skills.</p>
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-[#231742] border border-purple-900/40 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center">
              <FileCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-purple-300 font-semibold">Resume Fit</p>
              <p className="text-xs text-gray-400 mt-0.5">3 suggestions available to tailor.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-purple-900/40">
        {[
          { key: "overview", label: "Overview" },
          { key: "requirements", label: "Requirements" },
          { key: "company", label: "Company" },
          { key: "insights", label: "Insights" },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key as any)}
            className={`px-4 sm:px-6 py-3 text-sm font-medium border-b-2 transition-colors min-h-[44px] ${
              activeTab === key
                ? "border-purple-500 text-purple-400"
                : "border-transparent text-gray-400 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab Contents */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 sm:p-8 text-sm leading-relaxed text-gray-300">
        {activeTab === "overview" && (
          <div className="space-y-4">
            <h3 className="font-semibold text-white text-base">Job Description</h3>
            <p className="whitespace-pre-line text-gray-300/90">
              {job.description || "No full job description provided by the extraction engine."}
            </p>
          </div>
        )}

        {activeTab === "requirements" && (
          <div className="space-y-4">
            <h3 className="font-semibold text-white text-base">Key Requirements</h3>
            {requirements.length > 0 ? (
              <ul className="space-y-2.5">
                {requirements.map((req, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-2 shrink-0" />
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-400">See full overview for qualifications.</p>
            )}
          </div>
        )}

        {activeTab === "company" && (
          <div className="space-y-4">
            <h3 className="font-semibold text-white text-base flex items-center gap-2">
              <Building2 className="h-4 w-4 text-purple-400" />
              {job.company || "Company Information"}
            </h3>
            <p className="text-gray-400 text-xs">
              Extracted from source URL:
            </p>
            <a
              href={job.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-purple-400 hover:underline break-all"
            >
              {job.source_url} <ExternalLink className="h-3.5 w-3.5 shrink-0" />
            </a>
          </div>
        )}

        {activeTab === "insights" && (
          <div className="space-y-4 text-xs">
            <h3 className="font-semibold text-white text-sm mb-3">Crawler & Parser Metadata</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-[#231742] border border-purple-900/40">
                <span className="text-gray-400 block mb-1">Method</span>
                <span className="font-medium text-purple-300 uppercase">
                  {job.extraction_method || "standard"}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-[#231742] border border-purple-900/40">
                <span className="text-gray-400 block mb-1">Status</span>
                <span className="font-medium text-emerald-400">
                  {job.is_active ? "Active" : "Archived"}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-[#231742] border border-purple-900/40">
                <span className="text-gray-400 block mb-1">Discovered</span>
                <span className="font-medium text-gray-200">
                  {job.first_seen_at || job.extracted_at}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-[#231742] border border-purple-900/40">
                <span className="text-gray-400 block mb-1">Last Seen</span>
                <span className="font-medium text-gray-200">
                  {job.last_seen_at || job.extracted_at}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Floating Bottom Bar (Pi-friendly / Sticky) */}
      <div className="fixed bottom-0 left-0 right-0 z-40 bg-[#160d2e]/95 backdrop-blur-md border-t border-purple-900/50 p-3 sm:p-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
          <div>
            {application ? (
              <span className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-emerald-400">
                <CheckCircle2 className="h-4 w-4" /> Applied on {application.applied_on}
              </span>
            ) : (
              <span className="text-xs text-gray-400 hidden sm:inline">
                Direct submission via verified link
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              className={`px-4 py-2.5 rounded-xl border text-sm font-medium transition-colors min-h-[44px] ${
                isSaved
                  ? "bg-purple-600/30 border-purple-500 text-purple-300"
                  : "border-purple-900/50 hover:bg-purple-900/30 text-gray-300"
              }`}
            >
              {isSaved ? "Saved" : "Save"}
            </button>

            <button
              onClick={handleDownloadResume}
              disabled={isGeneratingResume}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-purple-500/50 bg-purple-900/30 hover:bg-purple-800/40 text-purple-200 text-sm font-medium transition-all min-h-[44px] disabled:opacity-50"
              title="Tailor resume with Qwen2.5-3B-Instruct and download PDF"
            >
              {isGeneratingResume ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-purple-400" />
                  Generating...
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4 text-purple-400" />
                  Tailored PDF
                </>
              )}
            </button>

            <button
              onClick={handleAutoApply}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-sm font-bold transition-all shadow-lg min-h-[44px]"
            >
              <Zap className="h-4 w-4 text-amber-300" />
              Auto-Apply with AI
            </button>

            <button
              onClick={handleApply}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-purple-800/80 hover:bg-purple-900/30 text-purple-300 text-sm font-medium transition-colors min-h-[44px]"
            >
              <Send className="h-4 w-4" />
              {application ? "Apply Again" : "Manual Apply"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
