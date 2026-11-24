"use client";

import { useState, useEffect, useCallback } from "react";
import {
  User,
  FileText,
  Sparkles,
  CheckCircle2,
  Briefcase,
  GraduationCap,
  Plus,
  Save,
  Loader2,
  Trash2,
  X,
  Settings,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Pencil,
  AlertCircle,
  FolderOpen,
  ExternalLink,
  Mail,
  Phone,
  MapPin,
  Globe,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────
interface Skill {
  name: string;
  category: string;
  level: string;
}
interface Project {
  id: string;
  title: string;
  link: string;
  tags: string[];
  bullets: string[];
}
interface Experience {
  company: string;
  role: string;
  location: string;
  start_date: string;
  end_date: string;
  tags: string[];
  bullets: string[];
}
interface Education {
  institution: string;
  degree: string;
  location: string;
  graduation_year: string;
  gpa: string;
}
interface ProfileSettings {
  max_daily_applications: number;
  min_delay_seconds: number;
  max_delay_seconds: number;
  browser_headless: boolean;
  chrome_user_data_dir: string;
  chrome_profile_name: string;
}
interface Profile {
  personal: {
    name: string;
    email: string;
    phone: string;
    location: string;
    linkedin_url: string;
    github_url: string;
    portfolio_url: string;
  };
  summary: string;
  skills: Skill[];
  projects: Project[];
  experience: Experience[];
  education: Education[];
  qa_bank: Record<string, string>;
  settings: ProfileSettings;
}

// ── Constants ──────────────────────────────────────────────────────────────
const SKILL_CATEGORIES = [
  "Languages",
  "Backend",
  "Frontend",
  "Databases",
  "DevOps",
  "Tools",
  "Architecture",
  "Other",
];
const SKILL_LEVELS = ["Beginner", "Intermediate", "Advanced", "Expert"];

function computeCompleteness(p: Profile): number {
  let total = 0;
  let filled = 0;
  const pf = Object.values(p.personal);
  total += pf.length;
  filled += pf.filter((v) => v && v.trim()).length;
  total += 1;
  if (p.summary.trim()) filled += 1;
  total += 1;
  if (p.skills.length > 0) filled += 1;
  total += 1;
  if (p.experience.length > 0) filled += 1;
  total += 1;
  if (p.education.length > 0) filled += 1;
  total += 1;
  if (p.projects.length > 0) filled += 1;
  total += 1;
  if (Object.keys(p.qa_bank).length > 3) filled += 1;
  return Math.round((filled / total) * 100);
}

// ── Isolated Input Component (Defined OUTSIDE ProfilePage to prevent focus loss) ──
function InputField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-400">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
      />
    </div>
  );
}

// ── Isolated Section Header Component ─────────────────────────────────────
function SectionHeader({
  isOpen,
  onToggle,
  icon: Icon,
  title,
  count,
}: {
  isOpen: boolean;
  onToggle: () => void;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center justify-between w-full text-left"
    >
      <h3 className="font-semibold text-white text-base flex items-center gap-2">
        <Icon className="h-4 w-4 text-purple-400" /> {title}
        {count !== undefined && (
          <span className="text-xs text-gray-400 font-normal ml-1">
            ({count})
          </span>
        )}
      </h3>
      {isOpen ? (
        <ChevronUp className="h-4 w-4 text-gray-400" />
      ) : (
        <ChevronDown className="h-4 w-4 text-gray-400" />
      )}
    </button>
  );
}

// ── Profile Page ───────────────────────────────────────────────────────────
export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [savedProfile, setSavedProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // collapsible sections
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    personal: true,
    summary: true,
    skills: true,
    experience: true,
    education: true,
    projects: true,
    qa: true,
    settings: false,
  });

  // new skill form
  const [newSkillName, setNewSkillName] = useState("");
  const [newSkillCat, setNewSkillCat] = useState("Other");
  const [newSkillLevel, setNewSkillLevel] = useState("Intermediate");

  // new QA entry
  const [newQaKey, setNewQaKey] = useState("");
  const [newQaVal, setNewQaVal] = useState("");

  // ── Fetch ─────────────────────────────────────────────────────────────
  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/auto-apply/profile`);
      if (!res.ok) throw new Error(`Failed to load profile (${res.status})`);
      const data: Profile = await res.json();
      setProfile(data);
      setSavedProfile(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  // ── Save ──────────────────────────────────────────────────────────────
  const handleSaveProfile = async () => {
    if (!profile) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const res = await fetch(`${API}/api/auto-apply/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      setSaved(true);
      setSavedProfile(structuredClone(profile));
      setIsEditing(false);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    if (savedProfile) {
      setProfile(structuredClone(savedProfile));
    }
    setIsEditing(false);
  };

  // ── Mutators ──────────────────────────────────────────────────────────
  const update = (mutator: (p: Profile) => void) => {
    if (!profile) return;
    const clone = structuredClone(profile);
    mutator(clone);
    setProfile(clone);
  };

  const toggleSection = (key: string) =>
    setOpenSections((s) => ({ ...s, [key]: !s[key] }));

  // ── Loading / Error states ────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
        <span className="ml-3 text-gray-400">Loading master profile…</span>
      </div>
    );
  }

  if (error && !profile) {
    return (
      <div className="max-w-2xl mx-auto mt-20 text-center space-y-4">
        <AlertCircle className="h-12 w-12 text-red-400 mx-auto" />
        <p className="text-red-400 font-semibold">{error}</p>
        <button
          onClick={fetchProfile}
          className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-semibold text-sm min-h-[44px]"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!profile) return null;

  const completeness = computeCompleteness(profile);

  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-28">
      {/* Header with Mode Toggle & Action Buttons */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2.5">
            <User className="h-7 w-7 text-purple-400" /> Resume & Master Profile
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Manage your personal data, skills, and ATS tailoring settings for automated applications.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {!isEditing ? (
            <button
              onClick={() => setIsEditing(true)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-sm min-h-[44px] shadow-lg shadow-purple-900/30 transition-all"
            >
              <Pencil className="h-4 w-4" /> Edit Profile
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleCancelEdit}
                disabled={saving}
                className="px-4 py-2.5 rounded-xl border border-purple-900/60 hover:bg-purple-900/20 text-gray-300 font-medium text-sm min-h-[44px] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveProfile}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-sm min-h-[44px] shadow-lg shadow-purple-900/30 transition-all"
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {saving ? "Saving…" : "Save Changes"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Notifications */}
      {saved && (
        <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-400 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" /> Profile saved to profile.json successfully!
        </div>
      )}
      {error && profile && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-400 flex items-center gap-2">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {/* ── Profile Overview Card ────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5">
          <div className="flex items-start sm:items-center gap-5">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center font-bold text-3xl text-white shadow-xl shrink-0">
              <User className="h-10 w-10" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold text-white truncate">
                  {profile.personal.name || "Candidate Name"}
                </h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                  {isEditing ? "Editing Mode" : "Master Profile"}
                </span>
              </div>
              <p className="text-sm text-gray-400 mt-1 truncate">
                {profile.experience[0]?.role || "Software Engineer"} •{" "}
                {profile.personal.location || "Location Flexible"}
              </p>
              <div className="flex items-center gap-3 mt-3 text-xs text-gray-400 flex-wrap">
                <span
                  className={`flex items-center gap-1 ${
                    completeness >= 80 ? "text-emerald-400" : "text-amber-400"
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> {completeness}% Profile Completeness
                </span>
                <span>• {profile.skills.length} skills</span>
                <span>• {profile.experience.length} roles</span>
              </div>
            </div>
          </div>

          {!isEditing && (
            <button
              onClick={() => setIsEditing(true)}
              className="px-4 py-2 rounded-xl bg-[#231742] hover:bg-purple-900/40 border border-purple-900/50 text-purple-200 text-xs font-medium flex items-center gap-1.5 min-h-[40px] transition-colors self-start sm:self-auto"
            >
              <Pencil className="h-3.5 w-3.5" /> Edit Profile
            </button>
          )}
        </div>
      </div>

      {/* ── Personal Info Section ────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.personal}
          onToggle={() => toggleSection("personal")}
          icon={User}
          title="Personal Information"
        />
        {openSections.personal && (
          isEditing ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <InputField label="Full Name" value={profile.personal.name} onChange={(v) => update((p) => (p.personal.name = v))} />
              <InputField label="Email" value={profile.personal.email} type="email" onChange={(v) => update((p) => (p.personal.email = v))} />
              <InputField label="Phone" value={profile.personal.phone} onChange={(v) => update((p) => (p.personal.phone = v))} />
              <InputField label="Location" value={profile.personal.location} onChange={(v) => update((p) => (p.personal.location = v))} />
              <InputField label="LinkedIn URL" value={profile.personal.linkedin_url} onChange={(v) => update((p) => (p.personal.linkedin_url = v))} />
              <InputField label="GitHub URL" value={profile.personal.github_url} onChange={(v) => update((p) => (p.personal.github_url = v))} />
              <div className="sm:col-span-2">
                <InputField label="Portfolio URL" value={profile.personal.portfolio_url} onChange={(v) => update((p) => (p.personal.portfolio_url = v))} placeholder="https://yoursite.dev" />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2 text-xs">
              <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                <span className="text-gray-400 flex items-center gap-1"><Mail className="h-3 w-3 text-purple-400" /> Email</span>
                <p className="font-medium text-white">{profile.personal.email || "—"}</p>
              </div>
              <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                <span className="text-gray-400 flex items-center gap-1"><Phone className="h-3 w-3 text-purple-400" /> Phone</span>
                <p className="font-medium text-white">{profile.personal.phone || "—"}</p>
              </div>
              <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                <span className="text-gray-400 flex items-center gap-1"><MapPin className="h-3 w-3 text-purple-400" /> Location</span>
                <p className="font-medium text-white">{profile.personal.location || "—"}</p>
              </div>
              {profile.personal.linkedin_url && (
                <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                  <span className="text-gray-400">LinkedIn</span>
                  <a href={profile.personal.linkedin_url} target="_blank" rel="noopener noreferrer" className="font-medium text-purple-300 hover:underline flex items-center gap-1 truncate">
                    {profile.personal.linkedin_url.replace("https://", "")} <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                  </a>
                </div>
              )}
              {profile.personal.github_url && (
                <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                  <span className="text-gray-400">GitHub</span>
                  <a href={profile.personal.github_url} target="_blank" rel="noopener noreferrer" className="font-medium text-purple-300 hover:underline flex items-center gap-1 truncate">
                    {profile.personal.github_url.replace("https://", "")} <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                  </a>
                </div>
              )}
              {profile.personal.portfolio_url && (
                <div className="p-3 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1">
                  <span className="text-gray-400 flex items-center gap-1"><Globe className="h-3 w-3 text-purple-400" /> Portfolio</span>
                  <a href={profile.personal.portfolio_url} target="_blank" rel="noopener noreferrer" className="font-medium text-purple-300 hover:underline flex items-center gap-1 truncate">
                    {profile.personal.portfolio_url.replace("https://", "")} <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                  </a>
                </div>
              )}
            </div>
          )
        )}
      </div>

      {/* ── Professional Summary Section ─────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.summary}
          onToggle={() => toggleSection("summary")}
          icon={FileText}
          title="Professional Summary"
        />
        {openSections.summary && (
          isEditing ? (
            <textarea
              value={profile.summary}
              onChange={(e) => update((p) => (p.summary = e.target.value))}
              rows={4}
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-3 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y"
              placeholder="Write a 2-3 sentence professional summary…"
            />
          ) : (
            <p className="text-sm text-gray-300 leading-relaxed bg-[#231742]/40 border border-purple-900/30 rounded-xl p-4">
              {profile.summary || "No professional summary provided yet."}
            </p>
          )
        )}
      </div>

      {/* ── Skills & Technologies Section ────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.skills}
          onToggle={() => toggleSection("skills")}
          icon={Sparkles}
          title="Skills & Technologies"
          count={profile.skills.length}
        />
        {openSections.skills && (
          <>
            {SKILL_CATEGORIES.filter((cat) =>
              profile.skills.some((s) => s.category === cat)
            ).map((cat) => (
              <div key={cat} className="space-y-2">
                <p className="text-xs text-purple-400 font-semibold uppercase tracking-wider">
                  {cat}
                </p>
                <div className="flex flex-wrap gap-2">
                  {profile.skills
                    .filter((s) => s.category === cat)
                    .map((s) => (
                      <span
                        key={s.name}
                        className="group relative px-3 py-1.5 rounded-lg bg-[#251744] border border-purple-900/50 text-purple-200 text-xs font-medium flex items-center gap-1.5"
                      >
                        {s.name}
                        <span className="text-[10px] text-gray-400">
                          ({s.level})
                        </span>
                        {isEditing && (
                          <button
                            type="button"
                            onClick={() =>
                              update(
                                (p) => (p.skills = p.skills.filter((x) => x.name !== s.name))
                              )
                            }
                            className="ml-1 text-red-400 hover:text-red-300"
                            title="Remove skill"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </span>
                    ))}
                </div>
              </div>
            ))}

            {isEditing && (
              <div className="flex flex-wrap gap-2 pt-3 border-t border-purple-900/30">
                <input
                  type="text"
                  value={newSkillName}
                  onChange={(e) => setNewSkillName(e.target.value)}
                  placeholder="Skill name…"
                  className="flex-1 min-w-[140px] rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newSkillName.trim()) {
                      update((p) =>
                        p.skills.push({
                          name: newSkillName.trim(),
                          category: newSkillCat,
                          level: newSkillLevel,
                        })
                      );
                      setNewSkillName("");
                    }
                  }}
                />
                <select
                  value={newSkillCat}
                  onChange={(e) => setNewSkillCat(e.target.value)}
                  className="rounded-xl bg-[#231742] border border-purple-900/50 px-3 py-2 text-sm text-gray-300 min-h-[44px]"
                >
                  {SKILL_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <select
                  value={newSkillLevel}
                  onChange={(e) => setNewSkillLevel(e.target.value)}
                  className="rounded-xl bg-[#231742] border border-purple-900/50 px-3 py-2 text-sm text-gray-300 min-h-[44px]"
                >
                  {SKILL_LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    if (!newSkillName.trim()) return;
                    update((p) =>
                      p.skills.push({
                        name: newSkillName.trim(),
                        category: newSkillCat,
                        level: newSkillLevel,
                      })
                    );
                    setNewSkillName("");
                  }}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-colors flex items-center gap-1.5 min-h-[44px]"
                >
                  <Plus className="h-4 w-4" /> Add
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Experience Section ───────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.experience}
          onToggle={() => toggleSection("experience")}
          icon={Briefcase}
          title="Work Experience"
          count={profile.experience.length}
        />
        {openSections.experience && (
          isEditing ? (
            <>
              {profile.experience.map((exp, i) => (
                <div
                  key={i}
                  className="border border-purple-900/30 rounded-xl p-4 space-y-3 bg-[#1e1438]"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <InputField label="Role" value={exp.role} onChange={(v) => update((p) => (p.experience[i].role = v))} />
                      <InputField label="Company" value={exp.company} onChange={(v) => update((p) => (p.experience[i].company = v))} />
                      <InputField label="Location" value={exp.location} onChange={(v) => update((p) => (p.experience[i].location = v))} />
                      <div className="flex gap-2">
                        <InputField label="Start" value={exp.start_date} placeholder="YYYY-MM" onChange={(v) => update((p) => (p.experience[i].start_date = v))} />
                        <InputField label="End" value={exp.end_date} placeholder="Present" onChange={(v) => update((p) => (p.experience[i].end_date = v))} />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => update((p) => p.experience.splice(i, 1))}
                      className="ml-3 mt-5 text-red-400/60 hover:text-red-400 transition-colors"
                      title="Remove experience"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs text-gray-400">Bullet Points</label>
                    {exp.bullets.map((b, bi) => (
                      <div key={bi} className="flex gap-2">
                        <input
                          value={b}
                          onChange={(e) =>
                            update(
                              (p) => (p.experience[i].bullets[bi] = e.target.value)
                            )
                          }
                          className="flex-1 rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            update((p) => p.experience[i].bullets.splice(bi, 1))
                          }
                          className="text-red-400/40 hover:text-red-400"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() =>
                        update((p) => p.experience[i].bullets.push(""))
                      }
                      className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                    >
                      <Plus className="h-3 w-3" /> Add bullet
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  update((p) =>
                    p.experience.push({
                      company: "",
                      role: "",
                      location: "",
                      start_date: "",
                      end_date: "Present",
                      tags: [],
                      bullets: [""],
                    })
                  )
                }
                className="w-full rounded-xl border border-dashed border-purple-800/50 py-3 text-sm text-purple-400 hover:text-purple-300 hover:border-purple-700 transition-colors flex items-center justify-center gap-2 min-h-[44px]"
              >
                <Plus className="h-4 w-4" /> Add Experience Entry
              </button>
            </>
          ) : (
            <div className="space-y-4">
              {profile.experience.map((exp, i) => (
                <div
                  key={i}
                  className="border-l-2 border-purple-600 pl-4 py-1 space-y-1"
                >
                  <p className="font-semibold text-white text-sm sm:text-base">
                    {exp.role} <span className="font-normal text-gray-400">at {exp.company}</span>
                  </p>
                  <p className="text-xs text-purple-400">
                    {exp.start_date} – {exp.end_date} • {exp.location || "Remote"}
                  </p>
                  {exp.bullets.length > 0 && (
                    <ul className="list-disc list-inside text-xs text-gray-300 space-y-1 pt-1">
                      {exp.bullets.filter(Boolean).map((b, bi) => (
                        <li key={bi} className="leading-relaxed">
                          {b}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {/* ── Education Section ────────────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.education}
          onToggle={() => toggleSection("education")}
          icon={GraduationCap}
          title="Education"
          count={profile.education.length}
        />
        {openSections.education && (
          isEditing ? (
            <>
              {profile.education.map((edu, i) => (
                <div
                  key={i}
                  className="border border-purple-900/30 rounded-xl p-4 space-y-3 bg-[#1e1438]"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <InputField label="Institution" value={edu.institution} onChange={(v) => update((p) => (p.education[i].institution = v))} />
                      <InputField label="Degree" value={edu.degree} onChange={(v) => update((p) => (p.education[i].degree = v))} />
                      <InputField label="Location" value={edu.location} onChange={(v) => update((p) => (p.education[i].location = v))} />
                      <div className="flex gap-2">
                        <InputField label="Year" value={edu.graduation_year} onChange={(v) => update((p) => (p.education[i].graduation_year = v))} />
                        <InputField label="GPA" value={edu.gpa} onChange={(v) => update((p) => (p.education[i].gpa = v))} />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => update((p) => p.education.splice(i, 1))}
                      className="ml-3 mt-5 text-red-400/60 hover:text-red-400 transition-colors"
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  update((p) =>
                    p.education.push({
                      institution: "",
                      degree: "",
                      location: "",
                      graduation_year: "",
                      gpa: "",
                    })
                  )
                }
                className="w-full rounded-xl border border-dashed border-purple-800/50 py-3 text-sm text-purple-400 hover:text-purple-300 hover:border-purple-700 transition-colors flex items-center justify-center gap-2 min-h-[44px]"
              >
                <Plus className="h-4 w-4" /> Add Education Entry
              </button>
            </>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profile.education.map((edu, i) => (
                <div
                  key={i}
                  className="p-4 rounded-xl bg-[#231742]/50 border border-purple-900/30 space-y-1"
                >
                  <p className="font-semibold text-white text-sm">{edu.degree}</p>
                  <p className="text-xs text-purple-300">{edu.institution}</p>
                  <p className="text-[11px] text-gray-400">
                    Graduation: {edu.graduation_year} • GPA: {edu.gpa}
                  </p>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {/* ── Featured Projects Section ────────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.projects}
          onToggle={() => toggleSection("projects")}
          icon={FolderOpen}
          title="Featured Projects"
          count={profile.projects.length}
        />
        {openSections.projects && (
          isEditing ? (
            <>
              {profile.projects.map((proj, i) => (
                <div
                  key={i}
                  className="border border-purple-900/30 rounded-xl p-4 space-y-3 bg-[#1e1438]"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <InputField label="Title" value={proj.title} onChange={(v) => update((p) => (p.projects[i].title = v))} />
                      <InputField label="Link" value={proj.link} onChange={(v) => update((p) => (p.projects[i].link = v))} />
                    </div>
                    <button
                      type="button"
                      onClick={() => update((p) => p.projects.splice(i, 1))}
                      className="ml-3 mt-5 text-red-400/60 hover:text-red-400 transition-colors"
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs text-gray-400">Tags (comma-separated)</label>
                    <input
                      value={proj.tags.join(", ")}
                      onChange={(e) =>
                        update(
                          (p) =>
                            (p.projects[i].tags = e.target.value
                              .split(",")
                              .map((t) => t.trim())
                              .filter(Boolean))
                        )
                      }
                      className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                      placeholder="Python, FastAPI, React…"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs text-gray-400">Bullet Points</label>
                    {proj.bullets.map((b, bi) => (
                      <div key={bi} className="flex gap-2">
                        <input
                          value={b}
                          onChange={(e) =>
                            update(
                              (p) => (p.projects[i].bullets[bi] = e.target.value)
                            )
                          }
                          className="flex-1 rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            update((p) => p.projects[i].bullets.splice(bi, 1))
                          }
                          className="text-red-400/40 hover:text-red-400"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() =>
                        update((p) => p.projects[i].bullets.push(""))
                      }
                      className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                    >
                      <Plus className="h-3 w-3" /> Add bullet
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  update((p) =>
                    p.projects.push({
                      id: `project-${Date.now()}`,
                      title: "",
                      link: "",
                      tags: [],
                      bullets: [""],
                    })
                  )
                }
                className="w-full rounded-xl border border-dashed border-purple-800/50 py-3 text-sm text-purple-400 hover:text-purple-300 hover:border-purple-700 transition-colors flex items-center justify-center gap-2 min-h-[44px]"
              >
                <Plus className="h-4 w-4" /> Add Project
              </button>
            </>
          ) : (
            <div className="space-y-3">
              {profile.projects.map((proj, i) => (
                <div
                  key={i}
                  className="p-4 rounded-xl bg-[#231742]/40 border border-purple-900/30 space-y-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold text-white text-sm">{proj.title}</span>
                    {proj.link && (
                      <a
                        href={proj.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-purple-400 hover:underline flex items-center gap-1"
                      >
                        Code / Live <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                  {proj.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {proj.tags.map((tag) => (
                        <span key={tag} className="px-2 py-0.5 rounded text-[10px] bg-[#1a1130] text-purple-300 border border-purple-900/40">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {proj.bullets.length > 0 && (
                    <ul className="list-disc list-inside text-xs text-gray-300 space-y-1">
                      {proj.bullets.filter(Boolean).map((b, bi) => (
                        <li key={bi}>{b}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {/* ── Screening Q&A Bank Section ──────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.qa}
          onToggle={() => toggleSection("qa")}
          icon={MessageSquare}
          title="Screening Q&A Bank"
          count={Object.keys(profile.qa_bank).length}
        />
        {openSections.qa && (
          isEditing ? (
            <>
              <p className="text-xs text-gray-400">
                Pre-fill screening answers so the auto-apply engine can respond to common ATS questions automatically.
              </p>
              <div className="space-y-2">
                {Object.entries(profile.qa_bank).map(([q, a]) => (
                  <div key={q} className="flex gap-2 items-start">
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <input
                        value={q}
                        readOnly
                        className="rounded-xl bg-[#231742]/60 border border-purple-900/30 px-4 py-2 text-xs text-gray-400 min-h-[44px]"
                      />
                      <input
                        value={a}
                        onChange={(e) =>
                          update((p) => (p.qa_bank[q] = e.target.value))
                        }
                        className="rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        update((p) => {
                          delete p.qa_bank[q];
                        })
                      }
                      className="mt-2 text-red-400/40 hover:text-red-400"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>

              <div className="flex gap-2 pt-2 border-t border-purple-900/30">
                <input
                  value={newQaKey}
                  onChange={(e) => setNewQaKey(e.target.value)}
                  placeholder="Question (e.g. years with docker)"
                  className="flex-1 rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                />
                <input
                  value={newQaVal}
                  onChange={(e) => setNewQaVal(e.target.value)}
                  placeholder="Answer"
                  className="flex-1 rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (!newQaKey.trim() || !newQaVal.trim()) return;
                    update(
                      (p) => (p.qa_bank[newQaKey.trim().toLowerCase()] = newQaVal.trim())
                    );
                    setNewQaKey("");
                    setNewQaVal("");
                  }}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-colors flex items-center gap-1.5 min-h-[44px]"
                >
                  <Plus className="h-4 w-4" /> Add
                </button>
              </div>
            </>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {Object.entries(profile.qa_bank).map(([q, a]) => (
                <div key={q} className="p-3 rounded-xl bg-[#231742]/40 border border-purple-900/30 space-y-0.5">
                  <span className="text-[11px] text-gray-400 capitalize block truncate">{q}</span>
                  <span className="text-xs font-semibold text-purple-300">{a}</span>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {/* ── Auto-Apply Settings Section ──────────────────────────────── */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-4">
        <SectionHeader
          isOpen={openSections.settings}
          onToggle={() => toggleSection("settings")}
          icon={Settings}
          title="Auto-Apply Settings"
        />
        {openSections.settings && (
          isEditing ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Max Daily Applications</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={profile.settings.max_daily_applications}
                  onChange={(e) =>
                    update(
                      (p) =>
                        (p.settings.max_daily_applications = parseInt(e.target.value) || 15)
                    )
                  }
                  className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Min Delay Between Apps (seconds)</label>
                <input
                  type="number"
                  min={10}
                  max={300}
                  value={profile.settings.min_delay_seconds}
                  onChange={(e) =>
                    update(
                      (p) =>
                        (p.settings.min_delay_seconds = parseInt(e.target.value) || 60)
                    )
                  }
                  className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Max Delay Between Apps (seconds)</label>
                <input
                  type="number"
                  min={10}
                  max={600}
                  value={profile.settings.max_delay_seconds}
                  onChange={(e) =>
                    update(
                      (p) =>
                        (p.settings.max_delay_seconds = parseInt(e.target.value) || 120)
                    )
                  }
                  className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Chrome Profile Name</label>
                <input
                  type="text"
                  value={profile.settings.chrome_profile_name}
                  onChange={(e) =>
                    update(
                      (p) => (p.settings.chrome_profile_name = e.target.value)
                    )
                  }
                  className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                  placeholder="Default"
                />
              </div>
              <div className="sm:col-span-2 space-y-1">
                <label className="text-xs text-gray-400">Chrome User Data Directory (optional)</label>
                <input
                  type="text"
                  value={profile.settings.chrome_user_data_dir}
                  onChange={(e) =>
                    update(
                      (p) => (p.settings.chrome_user_data_dir = e.target.value)
                    )
                  }
                  className="w-full rounded-xl bg-[#231742] border border-purple-900/50 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
                  placeholder="C:\\Users\\you\\AppData\\Local\\Google\\Chrome\\User Data"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    update(
                      (p) =>
                        (p.settings.browser_headless = !p.settings.browser_headless)
                    )
                  }
                  className={`w-12 h-7 rounded-full transition-colors relative ${
                    profile.settings.browser_headless
                      ? "bg-purple-600"
                      : "bg-[#231742] border border-purple-900/50"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${
                      profile.settings.browser_headless
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
                <label className="text-sm text-gray-300">Headless Browser Mode</label>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-[#231742]/40 border border-purple-900/30">
                <span className="text-gray-400 block">Daily Cap</span>
                <span className="font-semibold text-white">{profile.settings.max_daily_applications} apps / day</span>
              </div>
              <div className="p-3 rounded-xl bg-[#231742]/40 border border-purple-900/30">
                <span className="text-gray-400 block">Rate Delay Range</span>
                <span className="font-semibold text-white">{profile.settings.min_delay_seconds}s – {profile.settings.max_delay_seconds}s</span>
              </div>
              <div className="p-3 rounded-xl bg-[#231742]/40 border border-purple-900/30">
                <span className="text-gray-400 block">Browser Mode</span>
                <span className="font-semibold text-white">{profile.settings.browser_headless ? "Headless" : "Headed (Visible)"}</span>
              </div>
            </div>
          )
        )}
      </div>

      {/* ── Sticky Bottom Bar in Edit Mode ───────────────────────────── */}
      {isEditing && (
        <div className="fixed bottom-0 left-0 right-0 bg-[#120e1e]/95 backdrop-blur border-t border-purple-900/40 p-4 flex items-center justify-between z-50 shadow-2xl">
          <span className="text-sm text-purple-300 flex items-center gap-2">
            <Pencil className="h-4 w-4 text-purple-400" /> Editing Mode Active
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={handleCancelEdit}
              disabled={saving}
              className="px-4 py-2.5 rounded-xl border border-purple-900/60 hover:bg-purple-900/20 text-gray-300 font-medium text-sm min-h-[44px]"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveProfile}
              disabled={saving}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-sm min-h-[44px] shadow-lg shadow-purple-900/40"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {saving ? "Saving…" : "Save All Changes"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
