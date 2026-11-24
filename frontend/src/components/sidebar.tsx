"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Layers,
  LinkIcon,
  ClipboardList,
  Bookmark,
  User,
  Bell,
  BarChart3,
  ChevronLeft,
  Menu,
  Bot,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

const navItems = [
  { href: "/", label: "Home", icon: Home },
  { href: "/auto-apply", label: "Auto Apply (AI)", icon: Zap },
  { href: "/swipe", label: "Swipe Jobs", icon: Layers },
  { href: "/add-job", label: "Add Job (URL)", icon: LinkIcon },
  { href: "/crawler", label: "Crawler Control", icon: Bot },
  { href: "/applications", label: "Applications", icon: ClipboardList },
  { href: "/saved", label: "Saved Jobs", icon: Bookmark },
  { href: "/profile", label: "Resume & Profile", icon: User },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-50 flex items-center gap-3 bg-[#1a1130] px-4 py-3 border-b border-purple-900/40">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="text-white p-1"
          aria-label="Toggle menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-lg font-bold text-white">
          <span className="text-purple-400">Job</span>Swipe
        </span>
      </div>

      {/* Mobile overlay */}
      {!collapsed && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/50"
          onClick={() => setCollapsed(true)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 h-screen bg-[#1a1130] border-r border-purple-900/40 flex flex-col transition-all duration-200",
          "md:relative md:translate-x-0",
          collapsed ? "-translate-x-full md:w-[72px]" : "translate-x-0 w-64"
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-4 h-16 border-b border-purple-900/40">
          {!collapsed && (
            <span className="text-lg font-bold text-white whitespace-nowrap">
              <span className="text-purple-400">Job</span>Swipe
            </span>
          )}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="hidden md:flex text-gray-400 hover:text-white p-1"
            aria-label="Collapse sidebar"
          >
            <ChevronLeft
              className={cn(
                "h-4 w-4 transition-transform",
                collapsed && "rotate-180"
              )}
            />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => {
                  // close sidebar on mobile after navigation
                  if (window.innerWidth < 768) setCollapsed(true);
                }}
                className={cn(
                  "flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px]",
                  active
                    ? "bg-purple-600 text-white"
                    : "text-gray-400 hover:bg-purple-900/30 hover:text-white"
                )}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Upgrade CTA */}
        {!collapsed && (
          <div className="m-3 p-3 rounded-lg bg-purple-900/30 border border-purple-700/40">
            <p className="text-xs text-purple-300 font-medium">Upgrade</p>
            <p className="text-[11px] text-gray-400 mt-0.5 leading-snug">
              Get AI resume tailoring, more alerts & insights.
            </p>
          </div>
        )}
      </aside>
    </>
  );
}

