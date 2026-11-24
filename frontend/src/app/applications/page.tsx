"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  getApplications,
  updateApplicationStatus,
  removeApplication,
} from "@/lib/storage";
import type { Application, ApplicationStatus } from "@/types";
import {
  ClipboardList,
  MoreVertical,
  Trash2,
  ExternalLink,
  Plus,
} from "lucide-react";

const STATUS_FILTERS: { key: string; label: string; status?: ApplicationStatus }[] = [
  { key: "all", label: "All" },
  { key: "in_progress", label: "In Progress", status: "in_progress" },
  { key: "interview", label: "Interview", status: "interview" },
  { key: "offer", label: "Offer", status: "offer" },
  { key: "rejected", label: "Rejected", status: "rejected" },
];

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [activeFilter, setActiveFilter] = useState("all");
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);

  useEffect(() => {
    setApps(getApplications());
  }, []);

  const handleStatusChange = (jobId: number, status: ApplicationStatus) => {
    updateApplicationStatus(jobId, status);
    setApps(getApplications());
    setOpenMenuId(null);
  };

  const handleRemove = (jobId: number) => {
    removeApplication(jobId);
    setApps(getApplications());
    setOpenMenuId(null);
  };

  const filteredApps = apps.filter((app) => {
    if (activeFilter === "all") return true;
    return app.status === activeFilter;
  });

  const getStatusBadge = (status: ApplicationStatus) => {
    switch (status) {
      case "in_progress":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-400 border border-blue-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
            In Progress
          </span>
        );
      case "interview":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/20 text-purple-300 border border-purple-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
            Interview
          </span>
        );
      case "offer":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Offer
          </span>
        );
      case "rejected":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
            Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-500/20 text-gray-300 border border-gray-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
            Applied
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">My Applications</h1>
        <p className="text-gray-400 text-sm mt-1">
          Track all your job applications in one unified dashboard.
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs sm:text-sm">
        {STATUS_FILTERS.map(({ key, label, status }) => {
          const count =
            key === "all"
              ? apps.length
              : apps.filter((a) => a.status === status).length;
          const isActive = activeFilter === key;

          return (
            <button
              key={key}
              onClick={() => setActiveFilter(key)}
              className={`px-4 py-2 rounded-xl border transition-colors whitespace-nowrap min-h-[44px] flex items-center gap-2 ${
                isActive
                  ? "bg-purple-600 border-purple-500 text-white font-medium"
                  : "border-purple-900/40 bg-[#1a1130] text-gray-400 hover:text-white"
              }`}
            >
              <span>{label}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  isActive ? "bg-purple-800 text-white" : "bg-[#251744] text-gray-400"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Table / List */}
      {filteredApps.length === 0 ? (
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-12 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-purple-600/20 flex items-center justify-center text-purple-400 mx-auto">
            <ClipboardList className="h-6 w-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg text-white">No applications here yet</h3>
            <p className="text-gray-400 text-sm mt-1 max-w-sm mx-auto">
              Swipe right on positions or click Apply in Job Details to automatically track submissions.
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
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-300">
              <thead className="bg-[#231742] text-xs uppercase text-gray-400 border-b border-purple-900/40">
                <tr>
                  <th scope="col" className="px-6 py-4">Company</th>
                  <th scope="col" className="px-6 py-4">Role</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Applied On</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-purple-900/30">
                {filteredApps.map((app) => (
                  <tr
                    key={app.job_id}
                    className="hover:bg-purple-900/10 transition-colors"
                  >
                    {/* Company */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple-700 to-indigo-600 flex items-center justify-center font-bold text-white text-xs">
                          {app.company.charAt(0).toUpperCase()}
                        </div>
                        <span className="font-semibold text-white">
                          {app.company}
                        </span>
                      </div>
                    </td>

                    {/* Role */}
                    <td className="px-6 py-4">
                      <Link
                        href={`/jobs/${app.job_id}`}
                        className="hover:text-purple-300 hover:underline font-medium inline-flex items-center gap-1"
                      >
                        {app.role}
                        <ExternalLink className="h-3 w-3 text-gray-500" />
                      </Link>
                    </td>

                    {/* Status */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(app.status)}
                    </td>

                    {/* Applied date */}
                    <td className="px-6 py-4 text-xs text-gray-400 whitespace-nowrap">
                      {app.applied_on}
                    </td>

                    {/* Actions Menu */}
                    <td className="px-6 py-4 text-right relative whitespace-nowrap">
                      <button
                        onClick={() =>
                          setOpenMenuId(openMenuId === app.job_id ? null : app.job_id)
                        }
                        className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-purple-900/30 min-h-[38px] min-w-[38px] inline-flex items-center justify-center"
                        aria-label="Options"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>

                      {openMenuId === app.job_id && (
                        <div className="absolute right-6 mt-1 w-44 rounded-xl bg-[#20153b] border border-purple-800/60 shadow-2xl py-1.5 z-20 text-left text-xs">
                          <p className="px-3 py-1 font-semibold text-gray-400 uppercase text-[10px]">
                            Update Status
                          </p>
                          {(
                            [
                              ["applied", "Applied"],
                              ["in_progress", "In Progress"],
                              ["interview", "Interview"],
                              ["offer", "Offer"],
                              ["rejected", "Rejected"],
                            ] as const
                          ).map(([sKey, sLabel]) => (
                            <button
                              key={sKey}
                              onClick={() => handleStatusChange(app.job_id, sKey)}
                              className={`w-full text-left px-3 py-1.5 hover:bg-purple-800/40 transition-colors ${
                                app.status === sKey
                                  ? "text-purple-300 font-semibold"
                                  : "text-gray-300"
                              }`}
                            >
                              Mark as {sLabel}
                            </button>
                          ))}
                          <div className="border-t border-purple-900/40 my-1" />
                          <button
                            onClick={() => handleRemove(app.job_id)}
                            className="w-full text-left px-3 py-1.5 text-red-400 hover:bg-red-500/10 flex items-center gap-1.5"
                          >
                            <Trash2 className="h-3 w-3" /> Remove Application
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

