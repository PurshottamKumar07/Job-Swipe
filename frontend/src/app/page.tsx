"use client";

import { useStats } from "@/lib/hooks";
import {
  ClipboardList,
  Bookmark,
  Briefcase,
  Globe,
  Layers,
  BarChart3,
  FileText,
  Bell,
  ArrowRight,
  Sparkles,
  Bot,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const { data: stats, isLoading } = useStats();
  const [url, setUrl] = useState("");
  const router = useRouter();

  const statCards = [
    {
      label: "Applications",
      value: stats?.total_extracted_jobs ?? 0,
      icon: ClipboardList,
      color: "text-purple-400",
      bg: "bg-purple-500/10",
    },
    {
      label: "Saved Jobs",
      value: stats?.active_jobs ?? 0,
      icon: Bookmark,
      color: "text-blue-400",
      bg: "bg-blue-500/10",
    },
    {
      label: "In Progress",
      value: stats?.total_job_links ?? 0,
      icon: Briefcase,
      color: "text-yellow-400",
      bg: "bg-yellow-500/10",
    },
    {
      label: "Remote Jobs",
      value: stats?.remote_jobs ?? 0,
      icon: Globe,
      color: "text-green-400",
      bg: "bg-green-500/10",
    },
  ];

  const quickActions = [
    {
      label: "Activate Crawler",
      sub: "Run discovery pipeline",
      icon: Bot,
      href: "/crawler",
      color: "bg-purple-500/20 text-purple-400",
    },
    {
      label: "Swipe Jobs",
      sub: "Discover & save",
      icon: Layers,
      href: "/swipe",
      color: "bg-indigo-500/20 text-indigo-400",
    },
    {
      label: "Track Applications",
      sub: "View your status",
      icon: BarChart3,
      href: "/applications",
      color: "bg-blue-500/20 text-blue-400",
    },
    {
      label: "Browse All Jobs",
      sub: "Search & filter",
      icon: FileText,
      href: "/jobs",
      color: "bg-emerald-500/20 text-emerald-400",
    },
  ];

  const handleExtract = () => {
    if (url.trim()) {
      router.push(`/add-job?url=${encodeURIComponent(url.trim())}`);
    }
  };

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">
          Hey there! <span className="inline-block animate-bounce">👋</span>
        </h1>
        <p className="text-gray-400 mt-1">
          Find, apply and track jobs — all in one place.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map(({ label, value, icon: Icon, color, bg }) => (
          <div
            key={label}
            className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 sm:p-5"
          >
            <div className="flex items-center gap-3">
              <div className={`rounded-lg p-2 ${bg}`}>
                <Icon className={`h-5 w-5 ${color}`} />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {isLoading ? (
                    <span className="inline-block w-8 h-7 rounded bg-purple-900/40 animate-pulse" />
                  ) : (
                    value
                  )}
                </p>
                <p className="text-xs text-gray-400">{label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Paste URL card */}
      <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-5 sm:p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="rounded-lg p-2 bg-purple-500/20">
            <Sparkles className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">
              Paste a Job URL and Auto-Fill Details
            </h2>
            <p className="text-sm text-gray-400 mt-0.5">
              Add any job posting link (LinkedIn, Naukri, Indeed, AngelList,
              etc.) and let AI extract the details for you.
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.linkedin.com/jobs/..."
            className="flex-1 rounded-lg bg-[#2a1f45] border border-purple-900/40 px-4 py-3 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
            onKeyDown={(e) => e.key === "Enter" && handleExtract()}
          />
          <button
            onClick={handleExtract}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 px-6 py-3 text-sm font-medium transition-colors min-h-[44px] whitespace-nowrap"
          >
            <Sparkles className="h-4 w-4" />
            Extract Details
          </button>
        </div>
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {quickActions.map(({ label, sub, icon: Icon, href, color }) => (
            <Link
              key={href}
              href={href}
              className="group rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 hover:border-purple-600/60 transition-colors"
            >
              <div className={`inline-flex rounded-lg p-2 ${color} mb-3`}>
                <Icon className="h-5 w-5" />
              </div>
              <p className="font-medium text-sm">{label}</p>
              <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
              <ArrowRight className="h-4 w-4 text-gray-500 group-hover:text-purple-400 mt-2 transition-colors" />
            </Link>
          ))}
        </div>
      </div>

      {/* Top companies */}
      {stats && Object.keys(stats.top_companies).length > 0 && (
        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-5">
          <h2 className="text-lg font-semibold mb-4">Top Companies</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.top_companies).map(([name, count]) => (
              <Link
                key={name}
                href={`/jobs?company=${encodeURIComponent(name)}`}
                className="inline-flex items-center gap-1.5 rounded-full bg-purple-900/30 border border-purple-700/40 px-3 py-1.5 text-sm hover:bg-purple-900/50 transition-colors"
              >
                <span>{name}</span>
                <span className="text-xs text-gray-400">{count}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
