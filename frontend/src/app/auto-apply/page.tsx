"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Zap,
  Play,
  Square,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  ShieldAlert,
  ArrowRight,
  RefreshCw,
  ExternalLink,
  Sliders,
  Check,
  Plus,
  X,
  FileText,
  Clock,
  Eye,
} from "lucide-react";
import {
  getAutoApplySession,
  submitAutoApplyAction,
  startAutoApply,
  stopAutoApplySession,
  getAutoApplyLogs,
  listJobs,
  startSingleJobApply,
} from "@/lib/api";
import type {
  AutoApplySessionResponse,
  AutoApplyLogResponse,
  ExtractedJobResponse,
} from "@/types";

export default function AutoApplyPage() {
  const [session, setSession] = useState<AutoApplySessionResponse | null>(null);
  const [logs, setLogs] = useState<AutoApplyLogResponse[]>([]);
  const [unappliedJobs, setUnappliedJobs] = useState<ExtractedJobResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [maxApps, setMaxApps] = useState(10);
  const [showCoverLetter, setShowCoverLetter] = useState(false);
  const [showLiveBrowser, setShowLiveBrowser] = useState(false);

  // Skill editing state when paused
  const [reviewedJobId, setReviewedJobId] = useState<number | null>(null);
  const [editedSkills, setEditedSkills] = useState<string[]>([]);
  const [customSkillInput, setCustomSkillInput] = useState("");

  const novncUrl =
    process.env.NEXT_PUBLIC_NOVNC_URL ||
    "http://localhost:6080/vnc.html?autoconnect=true&resize=scale";

  const fetchData = useCallback(async () => {
    try {
      const [sessData, logsData, jobsData] = await Promise.all([
        getAutoApplySession().catch(() => null),
        getAutoApplyLogs(30).catch(() => []),
        listJobs({ active_only: true, limit: 15 }).catch(() => ({ items: [] })),
      ]);

      if (sessData) {
        setSession(sessData);
        // Only initialize edited skills when a new job pauses for review
        const currentPauseJobId = sessData.pause_data?.job_id;
        if (
          sessData.status === "paused_skill_review" &&
          currentPauseJobId &&
          currentPauseJobId !== reviewedJobId
        ) {
          setReviewedJobId(currentPauseJobId);
          setEditedSkills(sessData.pause_data?.matched_skills || []);
        } else if (sessData.status !== "paused_skill_review" && reviewedJobId !== null) {
          setReviewedJobId(null);
        }
      }
      setLogs(logsData || []);
      setUnappliedJobs(
        (jobsData.items || []).filter(
          (j) => !j.apply_status || j.apply_status === "unapplied"
        )
      );
    } catch (e) {
      console.error("Fetch error:", e);
    } finally {
      setIsLoading(false);
    }
  }, [reviewedJobId]);

  useEffect(() => {
    fetchData();
    // Poll dynamically: 2.5s when active/paused, 8s when idle to reduce overhead
    const isSessionActive =
      session?.status === "running" ||
      session?.status === "paused_skill_review" ||
      session?.status === "paused_captcha";
    const pollInterval = isSessionActive ? 2500 : 8000;

    const interval = setInterval(() => {
      fetchData();
    }, pollInterval);
    return () => clearInterval(interval);
  }, [fetchData, session?.status]);

  const handleStartSession = async () => {
    setIsSubmitting(true);
    try {
      await startAutoApply({ max_applications: maxApps });
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Could not start session");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStopSession = async () => {
    try {
      await stopAutoApplySession();
      await fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleApproveSkills = async () => {
    setIsSubmitting(true);
    try {
      await submitAutoApplyAction({
        action: "approve",
        approved_skills: editedSkills,
      });
      setEditedSkills([]);
      await fetchData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSkipJob = async () => {
    setIsSubmitting(true);
    try {
      await submitAutoApplyAction({ action: "skip" });
      setEditedSkills([]);
      await fetchData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSolvedCaptcha = async () => {
    setIsSubmitting(true);
    try {
      await submitAutoApplyAction({ action: "solved_captcha" });
      await fetchData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApplySingle = async (jobId: number) => {
    try {
      await startSingleJobApply(jobId);
      await fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const toggleSkill = (skill: string) => {
    if (editedSkills.includes(skill)) {
      setEditedSkills(editedSkills.filter((s) => s !== skill));
    } else {
      setEditedSkills([...editedSkills, skill]);
    }
  };

  const addCustomSkill = () => {
    const trimmed = customSkillInput.trim();
    if (trimmed && !editedSkills.includes(trimmed)) {
      setEditedSkills([...editedSkills, trimmed]);
      setCustomSkillInput("");
    }
  };

  const isRunning =
    session?.status === "running" ||
    session?.status === "paused_skill_review" ||
    session?.status === "paused_captcha";

  const dailyPercent = session
    ? Math.min(
        100,
        Math.round((session.daily_applied_today / session.daily_cap) * 100)
      )
    : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-20">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-2.5">
            <Zap className="h-7 w-7 text-purple-400" />
            Playwright Auto-Applier
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Automate job applications across LinkedIn, Indeed, and company ATS portals
            with AI skill-matching and human-in-the-loop CAPTCHA assistance.
          </p>
        </div>

        {/* Daily Safety Counter */}
        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-3 sm:px-5 flex items-center gap-4">
          <div>
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>Daily Safety Cap</span>
              <span className="font-semibold text-purple-300 ml-2">
                {session?.daily_applied_today ?? 0} / {session?.daily_cap ?? 15}
              </span>
            </div>
            <div className="w-32 bg-[#251744] h-2 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  dailyPercent > 80 ? "bg-amber-400" : "bg-purple-500"
                }`}
                style={{ width: `${dailyPercent}%` }}
              />
            </div>
          </div>
          <button
            onClick={() => fetchData()}
            className="p-2 rounded-lg bg-[#251744] hover:bg-purple-800/40 text-gray-300 transition-colors"
            title="Refresh status"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────── */}
      {/* 1. INTERACTIVE ALERT BANNER: CAPTCHA DETECTED               */}
      {/* ─────────────────────────────────────────────────────────── */}
      {session?.status === "paused_captcha" && (
        <div className="rounded-2xl border-2 border-amber-500/80 bg-amber-950/40 p-6 sm:p-7 shadow-2xl animate-in fade-in duration-200">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 border border-amber-500/40">
              <ShieldAlert className="h-6 w-6 animate-pulse" />
            </div>
            <div className="flex-1">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-amber-500 text-black">
                Action Required
              </span>
              <h2 className="text-xl font-bold text-white mt-1.5">
                CAPTCHA or Bot Check Detected
              </h2>
              <p className="text-sm text-amber-200/90 mt-1 leading-relaxed">
                The target website ({session.pause_data?.company || "Employer"}) has presented a security verification challenge.
                Please bring the open headed Chrome window to the front, complete the verification manually, and then click continue below.
              </p>

              <div className="flex flex-wrap items-center gap-3 mt-5">
                <button
                  onClick={handleSolvedCaptcha}
                  disabled={isSubmitting}
                  className="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-bold text-sm transition-colors shadow-lg flex items-center gap-2 min-h-[44px]"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  I Solved It — Continue Automation
                </button>
                <button
                  onClick={() => setShowLiveBrowser(!showLiveBrowser)}
                  className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-sm transition-colors shadow-lg flex items-center gap-2 min-h-[44px]"
                >
                  <Eye className="h-4 w-4" />
                  {showLiveBrowser ? "Hide Live Browser" : "Open In-Browser Screen (noVNC)"}
                </button>
                <button
                  onClick={handleSkipJob}
                  disabled={isSubmitting}
                  className="px-4 py-2.5 rounded-xl border border-amber-800 text-amber-300 hover:bg-amber-900/30 font-medium text-sm transition-colors min-h-[44px]"
                >
                  Skip this Job
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Embedded Live Container Browser Stream */}
      {showLiveBrowser && (
        <div className="rounded-2xl border-2 border-purple-500/80 bg-[#120a22] overflow-hidden shadow-2xl space-y-2 p-4">
          <div className="flex items-center justify-between px-2">
            <span className="text-xs font-bold uppercase tracking-wider text-purple-300 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              Live Container Display Stream (Interactive noVNC)
            </span>
            <div className="flex items-center gap-3">
              <a
                href={novncUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-purple-400 hover:underline inline-flex items-center gap-1"
              >
                Open in new tab <ExternalLink className="h-3 w-3" />
              </a>
              <button
                onClick={() => setShowLiveBrowser(false)}
                className="text-gray-400 hover:text-white text-xs px-2.5 py-1 rounded bg-[#231742]"
              >
                Close
              </button>
            </div>
          </div>
          <div className="rounded-xl overflow-hidden border border-purple-900/60 bg-black aspect-[16/10] w-full min-h-[450px]">
            <iframe
              src={novncUrl}
              className="w-full h-full border-0"
              title="Interactive Container Browser Stream"
              allow="clipboard-read; clipboard-write"
            />
          </div>
          <p className="text-[11px] text-gray-400 px-2">
            Interactive virtual screen: Click inside the browser to solve CAPTCHAs, enter verification codes, or inspect form fills in real-time.
          </p>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────── */}
      {/* 2. INTERACTIVE MODAL/CARD: ONE-BY-ONE SKILL VERIFICATION   */}
      {/* ─────────────────────────────────────────────────────────── */}
      {session?.status === "paused_skill_review" && session.pause_data && (
        <div className="rounded-2xl border-2 border-purple-500/70 bg-[#1a1130] p-6 sm:p-7 shadow-2xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-purple-900/40 pb-4">
            <div>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                <Sparkles className="h-3.5 w-3.5" /> Skill Review & Tailoring
              </span>
              <h2 className="text-xl font-bold text-white mt-2">
                {session.pause_data.job_title}
              </h2>
              <p className="text-sm text-gray-400 mt-0.5">
                {session.pause_data.company} • {session.pause_data.location || "Location Flexible"}
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-xs text-gray-400">Match Fit</div>
                <div className="text-2xl font-black text-emerald-400">
                  {session.pause_data.match_score ?? 85}%
                </div>
              </div>
            </div>
          </div>

          {/* Matched Skills Selection */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold uppercase tracking-wider text-purple-300">
                Skills to Highlight in Tailored Resume & LaTeX (Click to toggle)
              </label>
              <span className="text-xs text-gray-400">
                {editedSkills.length} selected
              </span>
            </div>

            <div className="flex flex-wrap gap-2">
              {editedSkills.map((skill) => (
                <button
                  key={skill}
                  onClick={() => toggleSkill(skill)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-600 border border-purple-400 text-white flex items-center gap-1.5 shadow-sm transition-all"
                >
                  <Check className="h-3.5 w-3.5" />
                  {skill}
                </button>
              ))}

              {/* Show missing skills that user might want to add */}
              {(session.pause_data.missing_skills || [])
                .filter((s) => !editedSkills.includes(s))
                .map((missing) => (
                  <button
                    key={missing}
                    onClick={() => toggleSkill(missing)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#231742] border border-purple-900/60 text-gray-400 hover:text-purple-300 hover:border-purple-600 flex items-center gap-1.5 transition-all"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {missing}
                  </button>
                ))}
            </div>

            {/* Custom skill add */}
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                placeholder="Add custom skill to resume..."
                value={customSkillInput}
                onChange={(e) => setCustomSkillInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addCustomSkill()}
                className="flex-1 rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[40px]"
              />
              <button
                onClick={addCustomSkill}
                className="px-4 py-2 rounded-xl bg-[#2b1b50] hover:bg-purple-700 text-purple-200 text-sm font-medium transition-colors"
              >
                Add Skill
              </button>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-purple-900/40">
            <button
              onClick={() => setShowCoverLetter(!showCoverLetter)}
              className="inline-flex items-center gap-2 text-xs text-purple-300 hover:text-white transition-colors"
            >
              <FileText className="h-3.5 w-3.5" />
              {showCoverLetter ? "Hide Cover Letter" : "Preview AI Cover Letter"}
            </button>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSkipJob}
                disabled={isSubmitting}
                className="px-4 py-2.5 rounded-xl border border-purple-900/60 hover:bg-purple-900/20 text-gray-400 hover:text-white text-sm transition-colors min-h-[44px]"
              >
                Skip Job
              </button>
              <button
                onClick={handleApproveSkills}
                disabled={isSubmitting}
                className="px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-sm shadow-lg flex items-center gap-2 transition-all min-h-[44px]"
              >
                <CheckCircle2 className="h-4 w-4" />
                Approve & Generate Tailored Resume
              </button>
            </div>
          </div>

          {/* Collapsible Cover Letter Drawer */}
          {showCoverLetter && (
            <div className="p-4 rounded-xl bg-[#120a22] border border-purple-900/50 text-xs text-gray-300 font-mono whitespace-pre-line leading-relaxed">
              {session.pause_data.cover_letter ||
                `Dear Hiring Team at ${session.pause_data.company},\n\nI am thrilled to submit my application for the ${session.pause_data.job_title} role. With hands-on proficiency in ${editedSkills.slice(0, 5).join(", ")}, I look forward to contributing to your team's development objectives.\n\nThank you for your consideration.`}
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────── */}
      {/* 3. SESSION STATUS & RUN CONTROLS                           */}
      {/* ─────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Engine Status
            </span>
            <div className="flex items-center gap-2.5 mt-1">
              <span
                className={`w-3 h-3 rounded-full ${
                  isRunning
                    ? "bg-emerald-400 animate-ping"
                    : "bg-gray-500"
                }`}
              />
              <span className="text-lg font-bold text-white capitalize">
                {session?.status === "paused_skill_review"
                  ? "Paused (Awaiting Skill Approval)"
                  : session?.status === "paused_captcha"
                  ? "Paused (Awaiting CAPTCHA Solution)"
                  : session?.status || "Idle"}
              </span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            {!isRunning ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 bg-[#231742] px-3 py-1.5 rounded-xl border border-purple-900/40 text-xs">
                  <Sliders className="h-3.5 w-3.5 text-purple-400" />
                  <span className="text-gray-400">Batch:</span>
                  <select
                    value={maxApps}
                    onChange={(e) => setMaxApps(Number(e.target.value))}
                    className="bg-transparent text-purple-300 font-bold focus:outline-none cursor-pointer"
                  >
                    <option value={5}>5 jobs</option>
                    <option value={10}>10 jobs</option>
                    <option value={15}>15 jobs</option>
                  </select>
                </div>

                <button
                  onClick={handleStartSession}
                  disabled={isSubmitting}
                  className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-sm shadow-lg flex items-center gap-2 transition-all min-h-[44px]"
                >
                  <Play className="h-4 w-4" />
                  Launch Batch Auto-Apply
                </button>
              </div>
            ) : (
              <button
                onClick={handleStopSession}
                className="px-5 py-2.5 rounded-xl bg-red-600/80 hover:bg-red-600 text-white font-bold text-sm shadow-lg flex items-center gap-2 transition-all min-h-[44px]"
              >
                <Square className="h-4 w-4" />
                Stop Automation
              </button>
            )}
          </div>
        </div>

        {/* Counter Stats */}
        {session && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-purple-900/40 text-xs">
            <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40">
              <span className="text-gray-400 block mb-0.5">Queue Target</span>
              <span className="text-lg font-bold text-white">
                {session.total_jobs}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40">
              <span className="text-gray-400 block mb-0.5">Applied</span>
              <span className="text-lg font-bold text-emerald-400">
                {session.applied_jobs}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40">
              <span className="text-gray-400 block mb-0.5">Skipped</span>
              <span className="text-lg font-bold text-gray-300">
                {session.skipped_jobs}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40">
              <span className="text-gray-400 block mb-0.5">Failed/Needs Help</span>
              <span className="text-lg font-bold text-red-400">
                {session.failed_jobs}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────── */}
      {/* 4. QUEUE OF UNAPPLIED JOBS                                 */}
      {/* ─────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-purple-400" />
            Unapplied Jobs in Database
          </h3>
          <Link
            href="/jobs"
            className="text-xs text-purple-400 hover:underline flex items-center gap-1"
          >
            Browse all jobs <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {unappliedJobs.length === 0 ? (
          <p className="text-xs text-gray-400 py-4 text-center">
            No unapplied jobs in database. Run the crawler or JobSpy scraper to populate postings.
          </p>
        ) : (
          <div className="divide-y divide-purple-900/30">
            {unappliedJobs.slice(0, 6).map((job) => (
              <div
                key={job.id}
                className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-purple-900/10 px-2 rounded-lg transition-colors"
              >
                <div>
                  <h4 className="font-semibold text-white text-sm">
                    {job.title || "Position"}
                  </h4>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {job.company || "Independent Employer"} • {job.is_remote ? "Remote" : job.location || "Flexible"}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    href={`/jobs/${job.id}`}
                    className="p-2 rounded-lg border border-purple-900/40 hover:bg-purple-900/30 text-gray-300 text-xs inline-flex items-center gap-1"
                  >
                    <Eye className="h-3.5 w-3.5" /> View
                  </Link>

                  <button
                    onClick={() => handleApplySingle(job.id)}
                    disabled={isRunning}
                    className="px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm min-h-[36px]"
                  >
                    <Zap className="h-3.5 w-3.5" /> Auto-Apply
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────── */}
      {/* 5. LIVE AUTOMATION LOG STREAM                               */}
      {/* ─────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#120a22] p-5 space-y-3 font-mono text-xs">
        <div className="flex items-center justify-between text-gray-400 border-b border-purple-900/40 pb-2">
          <span className="font-semibold text-purple-300 flex items-center gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${isRunning ? "animate-spin" : ""}`} />
            Live Automation Event Stream
          </span>
          <span>{logs.length} events logged</span>
        </div>

        <div className="max-h-64 overflow-y-auto space-y-1.5 pr-2">
          {logs.length === 0 ? (
            <p className="text-gray-500 py-3 text-center">No logs recorded yet.</p>
          ) : (
            logs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-2.5 py-1 text-gray-300 border-b border-purple-950/40"
              >
                <span className="text-[10px] text-gray-500 whitespace-nowrap mt-0.5">
                  {log.timestamp ? log.timestamp.slice(11, 19) : ""}
                </span>
                <span
                  className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase shrink-0 ${
                    log.event_type === "applied"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : log.event_type === "paused_captcha"
                      ? "bg-amber-500/20 text-amber-300"
                      : log.event_type === "paused_skill_review"
                      ? "bg-purple-500/20 text-purple-300"
                      : log.event_type === "error"
                      ? "bg-red-500/20 text-red-400"
                      : "bg-blue-500/20 text-blue-300"
                  }`}
                >
                  {log.event_type}
                </span>
                <span className="flex-1 break-words">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
