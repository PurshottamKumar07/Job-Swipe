"use client";

import { useAnalytics, useRuns } from "@/lib/hooks";
import {
  BarChart3,
  TrendingUp,
  Cpu,
  Layers,
  Globe,
  Briefcase,
  CheckCircle2,
  DollarSign,
  MapPin,
  Calendar,
  Sparkles,
  Loader2,
  Clock,
} from "lucide-react";

export default function AnalyticsPage() {
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics();
  const { data: runs, isLoading: runsLoading } = useRuns();

  const totalTrackedApps =
    (analytics?.funnel.applied ?? 0) +
    (analytics?.funnel.interview ?? 0) +
    (analytics?.funnel.offer ?? 0) +
    (analytics?.funnel.rejected ?? 0);

  const interviewRate =
    totalTrackedApps > 0
      ? Math.round(((analytics?.funnel.interview ?? 0) / totalTrackedApps) * 100)
      : 0;

  const offerRate =
    totalTrackedApps > 0
      ? Math.round(((analytics?.funnel.offer ?? 0) / totalTrackedApps) * 100)
      : 0;

  return (
    <div className="space-y-6 pb-20">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2.5">
          <BarChart3 className="h-7 w-7 text-purple-400" /> Analytics & Pipeline Insights
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Real-time crawler telemetry, hiring company density, salary benchmarks, and application funnel conversion.
        </p>
      </div>

      {/* Top row metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Total Crawl Runs</span>
            <Cpu className="h-4 w-4 text-purple-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {analyticsLoading ? <Loader2 className="h-6 w-6 animate-spin text-purple-400" /> : analytics?.total_crawl_runs ?? 0}
          </p>
          <span className="text-[11px] text-gray-500">
            {analytics?.total_job_links ?? 0} job links inspected
          </span>
        </div>

        <div className="p-5 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Total Extracted Jobs</span>
            <Layers className="h-4 w-4 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {analyticsLoading ? <Loader2 className="h-6 w-6 animate-spin text-purple-400" /> : analytics?.total_jobs ?? 0}
          </p>
          <span className="text-[11px] text-emerald-400 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" /> {analytics?.active_jobs ?? 0} confirmed active
          </span>
        </div>

        <div className="p-5 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Unique Companies</span>
            <Briefcase className="h-4 w-4 text-blue-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {analyticsLoading ? <Loader2 className="h-6 w-6 animate-spin text-purple-400" /> : analytics?.unique_companies ?? 0}
          </p>
          <span className="text-[11px] text-gray-500">Across all crawled boards</span>
        </div>

        <div className="p-5 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Remote Percentage</span>
            <Globe className="h-4 w-4 text-yellow-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {analytics && analytics.active_jobs > 0
              ? `${Math.round((analytics.remote_jobs / analytics.active_jobs) * 100)}%`
              : "0%"}
          </p>
          <span className="text-[11px] text-gray-500">
            {analytics?.remote_jobs ?? 0} remote-first listings
          </span>
        </div>
      </div>

      {/* Application Funnel & Salary Benchmarks */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Application Pipeline */}
        <div className="lg:col-span-2 p-6 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-white flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-purple-400" /> Application Pipeline & Conversion
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                Outcome tracking and conversion metrics from auto-apply runs.
              </p>
            </div>
            <div className="text-right">
              <span className="text-xs text-gray-400">Tracked Applications</span>
              <p className="text-xl font-bold text-purple-300">{totalTrackedApps}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <div className="p-4 rounded-xl bg-[#231742] border border-purple-900/40 text-center">
              <span className="text-xs text-purple-300">Submitted</span>
              <p className="text-2xl font-black text-white mt-1">
                {analytics?.funnel.applied ?? 0}
              </p>
              <span className="text-[10px] text-gray-400">Directly Applied</span>
            </div>
            <div className="p-4 rounded-xl bg-[#231742] border border-purple-900/40 text-center">
              <span className="text-xs text-blue-300">Interviews</span>
              <p className="text-2xl font-black text-blue-400 mt-1">
                {analytics?.funnel.interview ?? 0}
              </p>
              <span className="text-[10px] text-blue-300/80">{interviewRate}% conv.</span>
            </div>
            <div className="p-4 rounded-xl bg-[#231742] border border-purple-900/40 text-center">
              <span className="text-xs text-emerald-300">Offers</span>
              <p className="text-2xl font-black text-emerald-400 mt-1">
                {analytics?.funnel.offer ?? 0}
              </p>
              <span className="text-[10px] text-emerald-300/80">{offerRate}% conv.</span>
            </div>
            <div className="p-4 rounded-xl bg-[#231742] border border-purple-900/40 text-center">
              <span className="text-xs text-red-300">Rejected</span>
              <p className="text-2xl font-black text-red-400 mt-1">
                {analytics?.funnel.rejected ?? 0}
              </p>
              <span className="text-[10px] text-gray-400">Archived</span>
            </div>
          </div>

          {/* Daily Applications Volume Bar representation */}
          <div className="pt-3 border-t border-purple-900/30">
            <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5 mb-3">
              <Calendar className="h-3.5 w-3.5 text-purple-400" /> Daily Application Activity
            </span>
            {analytics?.daily_applications && analytics.daily_applications.length > 0 ? (
              <div className="space-y-2">
                <div className="flex items-end gap-2 h-24 pt-4 px-2">
                  {analytics.daily_applications.map((item) => {
                    const maxCount = Math.max(
                      ...analytics.daily_applications.map((d) => d.count),
                      1
                    );
                    const heightPercent = Math.max(15, Math.round((item.count / maxCount) * 100));
                    return (
                      <div
                        key={item.date}
                        className="flex-1 flex flex-col items-center gap-1 h-full justify-end group relative"
                      >
                        <div
                          className="w-full bg-gradient-to-t from-purple-600 to-indigo-500 rounded-t-md hover:from-purple-500 hover:to-indigo-400 transition-all cursor-pointer"
                          style={{ height: `${heightPercent}%` }}
                        />
                        <span className="text-[9px] text-gray-400 truncate w-full text-center">
                          {item.date.slice(5)}
                        </span>
                        {/* Tooltip */}
                        <div className="absolute -top-7 px-2 py-0.5 rounded bg-black/90 text-[10px] text-white opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-10">
                          {item.date}: {item.count} apps
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500 italic">
                No applications logged yet. Run an Auto-Apply session to generate telemetry!
              </p>
            )}
          </div>
        </div>

        {/* Salary & Location Insights */}
        <div className="p-6 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-4">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-purple-400" /> Salary Disclosures
          </h3>
          <p className="text-xs text-gray-400">
            Compensation metrics parsed from job descriptions.
          </p>

          <div className="space-y-3 pt-1">
            <div className="p-3.5 rounded-xl bg-[#231742] border border-purple-900/40 space-y-1">
              <span className="text-[11px] text-gray-400">Disclosed Average Minimum</span>
              <p className="text-xl font-bold text-white">
                {analytics?.salary_stats.avg_min
                  ? `$${Math.round(analytics.salary_stats.avg_min).toLocaleString()}`
                  : "N/A"}
              </p>
            </div>
            <div className="p-3.5 rounded-xl bg-[#231742] border border-purple-900/40 space-y-1">
              <span className="text-[11px] text-gray-400">Disclosed Average Maximum</span>
              <p className="text-xl font-bold text-white">
                {analytics?.salary_stats.avg_max
                  ? `$${Math.round(analytics.salary_stats.avg_max).toLocaleString()}`
                  : "N/A"}
              </p>
            </div>
            <span className="text-[11px] text-gray-500 block pt-1">
              {analytics?.salary_stats.disclosed_count ?? 0} of {analytics?.total_jobs ?? 0} jobs disclose transparent compensation
            </span>
          </div>

          <div className="pt-3 border-t border-purple-900/30 space-y-2">
            <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 text-purple-400" /> Top Discovered Locations
            </span>
            <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              {analytics?.top_locations && analytics.top_locations.length > 0 ? (
                analytics.top_locations.map((loc) => (
                  <div key={loc.location} className="flex justify-between text-xs py-1">
                    <span className="text-gray-300 truncate max-w-[180px]">{loc.location}</span>
                    <span className="text-gray-500 font-mono">{loc.count} jobs</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-500">No locations extracted yet.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Extraction Methods & Top Companies */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Method Breakdown */}
        <div className="p-6 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-4">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-purple-400" /> Extraction Methods
          </h3>
          <p className="text-xs text-gray-400">
            Underlying ingestion engines utilized across crawled pages.
          </p>

          <div className="space-y-3 pt-2">
            {analytics?.by_method &&
              Object.entries(analytics.by_method).map(([method, count]) => {
                const total = analytics.total_jobs || 1;
                const pct = Math.round((count / total) * 100);
                return (
                  <div key={method} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-gray-200 uppercase">
                        {method}
                      </span>
                      <span className="text-gray-400">
                        {count} ({pct}%)
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-[#251744] overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>

        {/* Top 10 Hiring Companies */}
        <div className="p-6 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-4">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <Briefcase className="h-4 w-4 text-purple-400" /> Top Hiring Companies
          </h3>
          <p className="text-xs text-gray-400">
            Organizations with the highest volume of postings discovered by crwlr.
          </p>

          <div className="overflow-x-auto pt-1">
            <table className="w-full text-left text-xs text-gray-300">
              <thead className="bg-[#231742] text-[10px] uppercase text-gray-400">
                <tr>
                  <th className="px-3 py-2.5">Company</th>
                  <th className="px-3 py-2.5">Openings</th>
                  <th className="px-3 py-2.5">Remote</th>
                  <th className="px-3 py-2.5">Applied</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-purple-900/30">
                {analytics?.top_companies && analytics.top_companies.length > 0 ? (
                  analytics.top_companies.map((comp) => (
                    <tr key={comp.company} className="hover:bg-purple-900/10">
                      <td className="px-3 py-2.5 font-semibold text-white">{comp.company}</td>
                      <td className="px-3 py-2.5 text-purple-300">{comp.total_jobs}</td>
                      <td className="px-3 py-2.5 text-gray-400">{comp.remote_count}</td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            comp.applied_count > 0
                              ? "bg-purple-500/20 text-purple-300"
                              : "text-gray-500"
                          }`}
                        >
                          {comp.applied_count}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-3 py-4 text-center text-gray-500">
                      No company data recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Crawl Runs History */}
      <div className="p-6 rounded-2xl border border-purple-900/40 bg-[#1a1130] space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <Clock className="h-4 w-4 text-purple-400" /> Recent Crawl & Scrape Telemetry
          </h3>
          <span className="text-xs text-gray-400">Latest 10 Ingestion Runs</span>
        </div>

        {runsLoading ? (
          <p className="text-xs text-gray-500">Loading runs...</p>
        ) : !runs || runs.length === 0 ? (
          <p className="text-xs text-gray-500">No crawl runs recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-gray-300">
              <thead className="bg-[#231742] text-[10px] uppercase text-gray-400">
                <tr>
                  <th className="px-4 py-3">Run ID</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Pages Crawled</th>
                  <th className="px-4 py-3">Links Inspected</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Started At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-purple-900/30">
                {runs.slice(0, 10).map((r) => (
                  <tr key={r.id} className="hover:bg-purple-900/10">
                    <td className="px-4 py-3 font-mono font-bold text-purple-300">#{r.id}</td>
                    <td className="px-4 py-3 uppercase">{r.run_type}</td>
                    <td className="px-4 py-3">{r.pages_crawled}</td>
                    <td className="px-4 py-3">{r.links_inspected}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          r.status === "completed" || r.status === "finished"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : r.status === "failed"
                            ? "bg-red-500/20 text-red-300"
                            : "bg-yellow-500/20 text-yellow-300"
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{r.started_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
