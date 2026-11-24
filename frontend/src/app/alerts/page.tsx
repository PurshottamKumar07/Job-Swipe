"use client";

import { useState } from "react";
import Link from "next/link";
import { useAlerts } from "@/lib/hooks";
import { createAlert, toggleAlert, deleteAlert, getAlertMatches } from "@/lib/api";
import type { JobAlert, ExtractedJobResponse } from "@/types";
import {
  Bell,
  Plus,
  Trash2,
  Mail,
  MapPin,
  ExternalLink,
  Briefcase,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Eye,
} from "lucide-react";

export default function AlertsPage() {
  const { data: alerts, mutate, isLoading } = useAlerts();

  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [email, setEmail] = useState("");
  const [frequency, setFrequency] = useState("Instant");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Match preview state
  const [activeMatchesAlertId, setActiveMatchesAlertId] = useState<number | null>(null);
  const [matches, setMatches] = useState<ExtractedJobResponse[]>([]);
  const [matchesLoading, setMatchesLoading] = useState(false);

  const handleAddAlert = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!keyword.trim()) {
      setError("Please enter job keywords (e.g. Python, React)");
      return;
    }
    if (!email.trim() || !email.includes("@")) {
      setError("Please provide a valid email address");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      await createAlert({
        keyword: keyword.trim(),
        location: location.trim() || undefined,
        frequency,
        email: email.trim(),
      });
      setKeyword("");
      setLocation("");
      setSuccess("Job alert created successfully! crwlr will scan matching jobs.");
      mutate();
      setTimeout(() => setSuccess(null), 4000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create alert");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggle = async (id: number) => {
    try {
      await toggleAlert(id);
      mutate();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to toggle alert");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this alert?")) return;
    try {
      await deleteAlert(id);
      if (activeMatchesAlertId === id) {
        setActiveMatchesAlertId(null);
        setMatches([]);
      }
      mutate();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete alert");
    }
  };

  const handleViewMatches = async (alertItem: JobAlert) => {
    if (activeMatchesAlertId === alertItem.id) {
      setActiveMatchesAlertId(null);
      setMatches([]);
      return;
    }

    setActiveMatchesAlertId(alertItem.id);
    setMatchesLoading(true);
    try {
      const results = await getAlertMatches(alertItem.id, 20);
      setMatches(results);
    } catch (err) {
      console.error(err);
      setMatches([]);
    } finally {
      setMatchesLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-20">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2.5">
          <Bell className="h-7 w-7 text-purple-400" /> Job Alerts & Notifications
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Configure real-time and digest job alerts. crwlr continuously matches crawled postings against your alert criteria.
        </p>
      </div>

      {/* Notifications */}
      {success && (
        <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-400 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" /> {success}
        </div>
      )}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-400 flex items-center gap-2">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {/* New Alert Form */}
      <form
        onSubmit={handleAddAlert}
        className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 sm:p-7 space-y-4"
      >
        <h3 className="font-semibold text-white text-base flex items-center gap-2">
          <Plus className="h-4 w-4 text-purple-400" /> Create New Search Alert
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="lg:col-span-2 space-y-1">
            <label className="text-xs text-gray-400">Job Title / Keywords *</label>
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="e.g. Next.js, FastAPI, Senior Backend..."
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2.5 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400">Location (Optional)</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Remote, Bengaluru..."
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2.5 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400">Frequency</label>
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
            >
              <option value="Instant">Instant Alert</option>
              <option value="Daily Digest">Daily Digest</option>
              <option value="Weekly Summary">Weekly Summary</option>
            </select>
          </div>

          <div className="sm:col-span-2 lg:col-span-3 space-y-1">
            <label className="text-xs text-gray-400">Notification Email *</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your.email@example.com"
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2.5 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-semibold text-sm transition-colors min-h-[44px] disabled:opacity-50"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              {isSubmitting ? "Creating..." : "Save Alert"}
            </button>
          </div>
        </div>
      </form>

      {/* Alerts list */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 sm:p-7 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white text-base">
            Configured Alerts ({alerts?.length ?? 0})
          </h3>
          <span className="text-xs text-gray-400">Live Database Sync</span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <Loader2 className="h-6 w-6 animate-spin text-purple-400 mr-2" />
            Loading job alerts...
          </div>
        ) : !alerts || alerts.length === 0 ? (
          <div className="text-center py-12 space-y-2">
            <Bell className="h-10 w-10 text-gray-600 mx-auto" />
            <p className="text-sm text-gray-400">No active job alerts configured yet.</p>
            <p className="text-xs text-gray-500">
              Create an alert above to monitor newly crawled job opportunities.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-purple-900/30">
            {alerts.map((alert) => (
              <div key={alert.id} className="py-5 first:pt-0 last:pb-0 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-white text-base">
                        {alert.keyword}
                      </span>
                      {alert.location && (
                        <span className="flex items-center gap-1 text-xs text-gray-400">
                          <MapPin className="h-3 w-3 text-purple-400" />
                          {alert.location}
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                        {alert.frequency}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          alert.match_count > 0
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : "bg-gray-500/20 text-gray-400"
                        }`}
                      >
                        {alert.match_count} active {alert.match_count === 1 ? "match" : "matches"}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                      <Mail className="h-3 w-3" /> Sending alerts to {alert.email} • Created{" "}
                      {alert.created_at?.slice(0, 10)}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <button
                      onClick={() => handleViewMatches(alert)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors flex items-center gap-1 min-h-[38px] ${
                        activeMatchesAlertId === alert.id
                          ? "bg-purple-600 text-white border-purple-500"
                          : "bg-[#231742] text-purple-300 border-purple-900/60 hover:bg-purple-900/30"
                      }`}
                    >
                      <Eye className="h-3.5 w-3.5" />
                      {activeMatchesAlertId === alert.id ? "Hide Matches" : "Preview Matches"}
                      {activeMatchesAlertId === alert.id ? (
                        <ChevronUp className="h-3 w-3" />
                      ) : (
                        <ChevronDown className="h-3 w-3" />
                      )}
                    </button>

                    <button
                      onClick={() => handleToggle(alert.id)}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors min-h-[38px] ${
                        alert.is_active
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30"
                          : "bg-gray-500/20 text-gray-400 border-gray-500/40 hover:bg-gray-500/30"
                      }`}
                    >
                      {alert.is_active ? "Active" : "Paused"}
                    </button>

                    <button
                      onClick={() => handleDelete(alert.id)}
                      className="p-2 text-gray-500 hover:text-red-400 rounded-lg hover:bg-red-500/10 transition-colors min-h-[38px]"
                      title="Delete alert"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Match Preview Drawer */}
                {activeMatchesAlertId === alert.id && (
                  <div className="mt-3 p-4 rounded-xl bg-[#120a22] border border-purple-900/50 space-y-3">
                    <div className="flex items-center justify-between text-xs text-gray-400 border-b border-purple-900/40 pb-2">
                      <span className="font-semibold text-purple-300">
                        Live Matching Jobs ({matches.length})
                      </span>
                      <span>Discovered in database</span>
                    </div>

                    {matchesLoading ? (
                      <div className="py-6 flex items-center justify-center text-gray-400 text-xs">
                        <Loader2 className="h-4 w-4 animate-spin text-purple-400 mr-2" />
                        Scanning matching jobs...
                      </div>
                    ) : matches.length === 0 ? (
                      <p className="text-xs text-gray-500 py-2">
                        No active jobs currently match &apos;{alert.keyword}&apos;. Run the crawler to discover new postings!
                      </p>
                    ) : (
                      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                        {matches.map((job) => (
                          <div
                            key={job.id}
                            className="p-3 rounded-lg bg-[#1a1130] border border-purple-900/40 flex items-start justify-between gap-3 text-xs"
                          >
                            <div>
                              <Link
                                href={`/jobs/${job.id}`}
                                className="font-semibold text-white hover:text-purple-300 hover:underline"
                              >
                                {job.title}
                              </Link>
                              <p className="text-gray-400 mt-0.5">
                                {job.company} • {job.location || "Remote / Unspecified"}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              {job.apply_url && (
                                <a
                                  href={job.apply_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-purple-400 hover:text-purple-300 flex items-center gap-1"
                                >
                                  Apply <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
