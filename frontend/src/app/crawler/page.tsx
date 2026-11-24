"use client";

import { useState, useEffect } from "react";
import {
  useRuns,
  useStats,
  useSeeds,
} from "@/lib/hooks";
import {
  startCrawl,
  startExtract,
  updateSeeds,
  importExistingData,
  startAdzunaFetch,
  startFreeJobsFetch,
  startJobSpyScrape,
} from "@/lib/api";
import {
  Bot,
  Play,
  RotateCcw,
  Sparkles,
  Layers,
  Database,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sliders,
  Globe,
  DownloadCloud,
  ArrowRight,
  ExternalLink,
  Rss,
  Search,
  MapPin,
  DollarSign,
  Zap,
} from "lucide-react";
import Link from "next/link";

export default function CrawlerPage() {
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
  }, []);

  const { data: stats, mutate: mutateStats } = useStats();
  const { data: runs, isLoading: runsLoading, mutate: mutateRuns } = useRuns();
  const { data: seedsData, mutate: mutateSeeds } = useSeeds();

  // Form states
  const [seedUrlsText, setSeedUrlsText] = useState<string>("");
  const [maxPages, setMaxPages] = useState<number>(30);
  const [concurrency, setConcurrency] = useState<number>(10);
  const [delay, setDelay] = useState<number>(0.25);
  const [timeout, setTimeoutSec] = useState<number>(10);
  const [respectRobots, setRespectRobots] = useState<boolean>(false);

  // Action states
  const [isCrawling, setIsCrawling] = useState(false);
  const [extractingRunId, setExtractingRunId] = useState<number | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<{
    type: "success" | "error" | "info";
    text: string;
  } | null>(null);

  // Free Jobs API state (Remotive + Himalayas — 100% free, no key)
  const [apiSource, setApiSource] = useState<"all" | "remotive" | "himalayas">("all");
  const [apiSearch, setApiSearch] = useState("software engineer");
  const [apiCategory, setApiCategory] = useState("software-dev");
  const [apiLimit, setApiLimit] = useState(50);
  const [isFetchingFreeJobs, setIsFetchingFreeJobs] = useState(false);

  // JobSpy Multi-Board Scraper state
  const [jobspySearch, setJobspySearch] = useState("software engineer");
  const [jobspyLocation, setJobspyLocation] = useState("");
  const [jobspySites, setJobspySites] = useState<string[]>(["linkedin", "indeed", "glassdoor"]);
  const [jobspyResults, setJobspyResults] = useState(20);
  const [jobspyHoursOld, setJobspyHoursOld] = useState<string>("");
  const [jobspyRemote, setJobspyRemote] = useState(false);
  const [jobspyJobType, setJobspyJobType] = useState("");
  const [jobspyCountry, setJobspyCountry] = useState("usa");
  const [jobspyFetchDesc, setJobspyFetchDesc] = useState(true);
  const [isScrapingJobSpy, setIsScrapingJobSpy] = useState(false);

  // Pre-fill seeds from seeds.txt if empty
  const handleLoadSavedSeeds = () => {
    if (seedsData?.urls && seedsData.urls.length > 0) {
      setSeedUrlsText(seedsData.urls.join("\n"));
    }
  };

  // Launch Stage 1 Crawl
  const handleStartCrawl = async () => {
    const rawUrls = seedUrlsText
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    const urlsToUse =
      rawUrls.length > 0
        ? rawUrls
        : seedsData?.urls && seedsData.urls.length > 0
        ? seedsData.urls
        : ["https://stripe.com", "https://remoteok.com", "https://github.com/about"];

    setIsCrawling(true);
    setFeedbackMessage({
      type: "info",
      text: "Activating crawler across target domains...",
    });

    try {
      const res = await startCrawl({
        seed_urls: urlsToUse,
        max_pages: maxPages,
        concurrency,
        delay,
        timeout,
        respect_robots: respectRobots,
      });

      setFeedbackMessage({
        type: "success",
        text: `Crawl run #${res.run_id} launched successfully! Monitoring progress below.`,
      });
      mutateRuns();
      mutateStats();
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to launch crawl run.",
      });
    } finally {
      setIsCrawling(false);
    }
  };

  // Trigger Stage 2 Extraction
  const handleStartExtract = async (crawlRunId: number) => {
    setExtractingRunId(crawlRunId);
    setFeedbackMessage({
      type: "info",
      text: `Activating Stage 2 Job Extractor for run #${crawlRunId}...`,
    });

    try {
      const res = await startExtract({
        crawl_run_id: crawlRunId,
        concurrency,
        timeout,
      });

      setFeedbackMessage({
        type: "success",
        text: `Extraction active for run #${crawlRunId}. Parsing ATS endpoints & schema markup.`,
      });
      mutateRuns();
      mutateStats();
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to start extraction.",
      });
    } finally {
      setExtractingRunId(null);
    }
  };

  // Ingest existing files into DB
  const handleImportExisting = async () => {
    setIsImporting(true);
    setFeedbackMessage({
      type: "info",
      text: "Importing existing jobs.json and extracted_jobs.json into SQLite...",
    });

    try {
      const res = await importExistingData();
      setFeedbackMessage({
        type: "success",
        text: res.message,
      });
      mutateRuns();
      mutateStats();
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to import existing data.",
      });
    } finally {
      setIsImporting(false);
    }
  };

  // Free Jobs API fetch handler (Remotive + Himalayas)
  const handleFreeJobsFetch = async () => {
    setIsFetchingFreeJobs(true);
    setFeedbackMessage({
      type: "info",
      text: `Fetching free jobs from ${apiSource === "all" ? "Remotive & Himalayas" : apiSource.toUpperCase()} (no key needed)...`,
    });
    try {
      const res = await startFreeJobsFetch({
        source: apiSource,
        search: apiSearch.trim() || undefined,
        category: apiCategory || undefined,
        limit: apiLimit,
      });
      setFeedbackMessage({
        type: "success",
        text: `Free jobs run #${res.run_id} launched! Fetched jobs will appear in Browse Jobs in a few seconds.`,
      });
      mutateRuns();
      mutateStats();
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to fetch from free job APIs.",
      });
    } finally {
      setIsFetchingFreeJobs(false);
    }
  };

  // JobSpy scrape handler
  const handleJobSpyScrape = async () => {
    setIsScrapingJobSpy(true);
    setFeedbackMessage({
      type: "info",
      text: `Scraping jobs from ${jobspySites.join(", ")} via JobSpy (search: "${jobspySearch}")...`,
    });
    try {
      const res = await startJobSpyScrape({
        search_term: jobspySearch.trim() || "software engineer",
        location: jobspyLocation.trim() || undefined,
        sites: jobspySites,
        results_wanted: jobspyResults,
        hours_old: jobspyHoursOld ? parseInt(jobspyHoursOld, 10) : undefined,
        is_remote: jobspyRemote,
        job_type: jobspyJobType || undefined,
        country_indeed: jobspyCountry,
        fetch_description: jobspyFetchDesc,
      });
      setFeedbackMessage({
        type: "success",
        text: `JobSpy run #${res.run_id} launched! Scraping ${jobspySites.join(", ")} — jobs will appear in Browse Jobs shortly.`,
      });
      mutateRuns();
      mutateStats();
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to start JobSpy scrape.",
      });
    } finally {
      setIsScrapingJobSpy(false);
    }
  };

  const toggleSite = (site: string) => {
    setJobspySites((prev) =>
      prev.includes(site) ? prev.filter((s) => s !== site) : [...prev, site]
    );
  };

  // Save current textarea back to seeds.txt
  const handleSaveSeeds = async () => {
    const urls = seedUrlsText
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    if (urls.length === 0) return;

    try {
      await updateSeeds(urls);
      mutateSeeds();
      setFeedbackMessage({
        type: "success",
        text: "Successfully saved seed URLs to seeds.txt",
      });
    } catch (err: any) {
      setFeedbackMessage({
        type: "error",
        text: err?.message || "Failed to update seeds.txt",
      });
    }
  };

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2.5">
              <Bot className="h-7 w-7 text-purple-400" />
              Crawler Control Center
            </h1>
            <p className="text-gray-400 text-sm mt-1">
              Activate the asynchronous crawler, monitor crawl discovery runs, and trigger Stage 2 job extraction.
            </p>
          </div>

          <button
            onClick={handleImportExisting}
            disabled={isImporting}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-purple-800/60 bg-purple-950/30 hover:bg-purple-900/40 text-purple-300 text-xs sm:text-sm font-medium transition-colors min-h-[44px]"
          >
            {isImporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <DownloadCloud className="h-4 w-4" />
            )}
            Import Existing JSON Data
          </button>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedbackMessage && (
        <div
          className={`p-4 rounded-xl text-sm flex items-start gap-3 border ${
            feedbackMessage.type === "success"
              ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
              : feedbackMessage.type === "error"
              ? "bg-red-950/40 border-red-800/60 text-red-300"
              : "bg-purple-950/40 border-purple-800/60 text-purple-300"
          }`}
        >
          {feedbackMessage.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : feedbackMessage.type === "error" ? (
            <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          ) : (
            <Loader2 className="h-5 w-5 text-purple-400 animate-spin shrink-0 mt-0.5" />
          )}
          <div className="flex-1">
            <p>{feedbackMessage.text}</p>
          </div>
          <button
            onClick={() => setFeedbackMessage(null)}
            className="text-gray-400 hover:text-white text-xs ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* Live Metrics Overview */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg p-2 bg-purple-500/10 text-purple-400">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {stats?.total_crawl_runs ?? 0}
              </p>
              <p className="text-xs text-gray-400">Total Crawl Runs</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg p-2 bg-blue-500/10 text-blue-400">
              <Globe className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {stats?.total_job_links ?? 0}
              </p>
              <p className="text-xs text-gray-400">Discovered Job Links</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg p-2 bg-emerald-500/10 text-emerald-400">
              <Layers className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {stats?.total_extracted_jobs ?? 0}
              </p>
              <p className="text-xs text-gray-400">Extracted Jobs in DB</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-purple-900/40 bg-[#1a1130] p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg p-2 bg-indigo-500/10 text-indigo-400">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {stats?.unique_companies ?? 0}
              </p>
              <p className="text-xs text-gray-400">Unique Companies</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Activation Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Crawl Launcher */}
        <div className="lg:col-span-2 rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Play className="h-4 w-4 text-purple-400" />
              Launch Stage 1 Crawler
            </h2>
            <button
              onClick={handleLoadSavedSeeds}
              className="text-xs text-purple-400 hover:text-purple-300 font-medium transition-colors"
            >
              Load from seeds.txt
            </button>
          </div>

          {/* Seeds Input */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <label htmlFor="seedUrls">Seed URLs (one per line)</label>
              <span>{seedUrlsText.split("\n").filter((s) => s.trim()).length} target(s)</span>
            </div>
            <textarea
              id="seedUrls"
              rows={4}
              value={seedUrlsText}
              onChange={(e) => setSeedUrlsText(e.target.value)}
              placeholder="https://stripe.com&#10;https://remoteok.com&#10;https://github.com/about"
              className="w-full rounded-xl bg-[#231742] border border-purple-900/50 p-3 text-xs sm:text-sm font-mono placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 text-gray-200"
            />
            <div className="flex justify-end gap-2 text-xs">
              <button
                onClick={handleSaveSeeds}
                className="text-gray-400 hover:text-purple-300 transition-colors"
              >
                Save as default seeds
              </button>
            </div>
          </div>

          {/* Parameter Sliders / Inputs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="text-xs font-medium text-gray-300 flex justify-between">
                <span>Max Pages</span>
                <span className="text-purple-400 font-bold">{maxPages}</span>
              </label>
              <input
                type="range"
                min={5}
                max={200}
                step={5}
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value, 10))}
                className="w-full accent-purple-500 mt-2"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-300 flex justify-between">
                <span>Concurrency</span>
                <span className="text-purple-400 font-bold">{concurrency} workers</span>
              </label>
              <input
                type="range"
                min={1}
                max={30}
                step={1}
                value={concurrency}
                onChange={(e) => setConcurrency(parseInt(e.target.value, 10))}
                className="w-full accent-purple-500 mt-2"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-300 flex justify-between">
                <span>Per-Domain Delay (sec)</span>
                <span className="text-purple-400 font-bold">{delay}s</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={delay}
                onChange={(e) => setDelay(parseFloat(e.target.value))}
                className="w-full accent-purple-500 mt-2"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-300 flex justify-between">
                <span>Request Timeout (sec)</span>
                <span className="text-purple-400 font-bold">{timeout}s</span>
              </label>
              <input
                type="range"
                min={5}
                max={30}
                step={1}
                value={timeout}
                onChange={(e) => setTimeoutSec(parseInt(e.target.value, 10))}
                className="w-full accent-purple-500 mt-2"
              />
            </div>
          </div>

          {/* Robots toggle & submit */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-4 border-t border-purple-900/40">
            <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={respectRobots}
                onChange={(e) => setRespectRobots(e.target.checked)}
                className="rounded border-purple-800 text-purple-600 focus:ring-purple-500 bg-[#231742] h-4 w-4"
              />
              <span>Respect robots.txt rules</span>
            </label>

            <button
              onClick={handleStartCrawl}
              disabled={isCrawling}
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors shadow-lg min-h-[44px] w-full sm:w-auto"
            >
              {isCrawling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Crawling in Background...</span>
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-white" />
                  <span>Activate Crawler 🚀</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Col: Stage Pipeline Quick Guide */}
        <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-5 flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="font-semibold text-white flex items-center gap-2 text-base">
              <Sliders className="h-4 w-4 text-purple-400" />
              Pipeline Architecture
            </h3>

            <div className="space-y-3 text-xs text-gray-300">
              <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40 space-y-1">
                <p className="font-semibold text-purple-300">Stage 1: Link Discovery</p>
                <p className="text-gray-400">
                  Fetches seed HTML, scores anchor tags, regex matches job URLs, and saves candidate URLs into SQLite.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40 space-y-1">
                <p className="font-semibold text-indigo-300">Stage 2: Structured Extraction</p>
                <p className="text-gray-400">
                  Visits discovered job URLs, calls ATS APIs (Greenhouse/Lever/Ashby), extracts JSON-LD schemas, and normalizes salaries & remote flags.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-[#231742] border border-purple-900/40 space-y-1">
                <p className="font-semibold text-emerald-300">Stage 3: Swipe & Apply</p>
                <p className="text-gray-400">
                  Browse discovered jobs in the Swipe deck, search with FTS5, and track submissions.
                </p>
              </div>
            </div>
          </div>

          <Link
            href="/jobs"
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#231742] hover:bg-purple-900/40 border border-purple-800/50 text-xs font-semibold text-purple-300 transition-colors"
          >
            Explore Extracted Jobs <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>

      {/* ── Free Jobs API Fetch Card (Remotive & Himalayas) ─────────────── */}
      <div className="rounded-2xl border border-emerald-900/40 bg-[#0e211b] p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Rss className="h-5 w-5 text-emerald-400" />
              Free Global Jobs API
              <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-300 border border-emerald-800/40">
                100% Free · No API Key
              </span>
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Pull clean, live remote jobs instantly from <span className="text-emerald-300 font-medium">Remotive</span> &amp; <span className="text-emerald-300 font-medium">Himalayas</span>. No credit cards, trial limits, or rate limit paywalls.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Source Selection */}
          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Globe className="h-3.5 w-3.5 text-emerald-400" />
              Data Source
            </label>
            <select
              value={apiSource}
              onChange={(e) => setApiSource(e.target.value as any)}
              className="w-full px-3 py-2.5 rounded-xl bg-[#142d25] border border-emerald-900/40 text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 min-h-[44px]"
            >
              <option value="all">🌐 Both (Remotive + Himalayas)</option>
              <option value="remotive">⚡ Remotive (Global Tech)</option>
              <option value="himalayas">🏔️ Himalayas (Salary Data)</option>
            </select>
          </div>

          {/* Search Query */}
          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Search className="h-3.5 w-3.5 text-emerald-400" />
              Keywords
            </label>
            <input
              type="text"
              value={apiSearch}
              onChange={(e) => setApiSearch(e.target.value)}
              placeholder="e.g. python, react, backend"
              className="w-full px-3 py-2.5 rounded-xl bg-[#142d25] border border-emerald-900/40 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 min-h-[44px]"
            />
          </div>

          {/* Category */}
          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Layers className="h-3.5 w-3.5 text-emerald-400" />
              Category <span className="text-gray-500">(Remotive)</span>
            </label>
            <select
              value={apiCategory}
              onChange={(e) => setApiCategory(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-[#142d25] border border-emerald-900/40 text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 min-h-[44px]"
            >
              <option value="">All Categories</option>
              <option value="software-dev">Software Development</option>
              <option value="data">Data & Analytics</option>
              <option value="design">Design</option>
              <option value="devops">DevOps & Sysadmin</option>
              <option value="product">Product</option>
              <option value="qa">QA / Testing</option>
              <option value="marketing">Marketing</option>
              <option value="sales">Sales</option>
            </select>
          </div>

          {/* Limit Slider */}
          <div>
            <label className="text-xs font-medium text-gray-300 flex justify-between mb-1.5">
              <span>Fetch Limit</span>
              <span className="text-emerald-400 font-bold">{apiLimit} jobs</span>
            </label>
            <input
              type="range"
              min={10}
              max={150}
              step={10}
              value={apiLimit}
              onChange={(e) => setApiLimit(parseInt(e.target.value))}
              className="w-full accent-emerald-500 mt-2"
            />
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-1">
          <p className="text-xs text-gray-400">
            Jobs are instantly deduplicated and normalized into your database. View them on <Link href="/jobs" className="text-emerald-400 underline hover:text-emerald-300">Browse Jobs</Link> or swipe right on the <Link href="/swipe" className="text-emerald-400 underline hover:text-emerald-300">Swipe Deck</Link>.
          </p>

          <button
            onClick={handleFreeJobsFetch}
            disabled={isFetchingFreeJobs}
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors shadow-lg min-h-[44px] shrink-0"
          >
            {isFetchingFreeJobs ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Fetching Jobs...</span>
              </>
            ) : (
              <>
                <Rss className="h-4 w-4" />
                <span>Fetch Free Jobs ⚡</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── JobSpy Multi-Board Scraper Card ────────────────────────── */}
      <div className="rounded-2xl border border-blue-900/40 bg-[#0e1629] p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-400" />
              JobSpy Multi-Board Scraper
              <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-800/40">
                Free · No API Key
              </span>
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Scrape real job postings from{" "}
              <span className="text-blue-300 font-medium">LinkedIn</span>,{" "}
              <span className="text-blue-300 font-medium">Indeed</span>,{" "}
              <span className="text-blue-300 font-medium">Glassdoor</span>,{" "}
              <span className="text-blue-300 font-medium">ZipRecruiter</span>,{" "}
              <span className="text-blue-300 font-medium">Google</span> & more.
              Duplicates are auto-detected and merged.
            </p>
          </div>
        </div>

        {/* Row 1: Search & Location */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Search className="h-3.5 w-3.5 text-blue-400" />
              Search Term
            </label>
            <input
              type="text"
              value={jobspySearch}
              onChange={(e) => setJobspySearch(e.target.value)}
              placeholder="e.g. software engineer, python developer"
              className="w-full px-3 py-2.5 rounded-xl bg-[#141e30] border border-blue-900/40 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[44px]"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <MapPin className="h-3.5 w-3.5 text-blue-400" />
              Location
            </label>
            <input
              type="text"
              value={jobspyLocation}
              onChange={(e) => setJobspyLocation(e.target.value)}
              placeholder="e.g. San Francisco, CA or Remote"
              className="w-full px-3 py-2.5 rounded-xl bg-[#141e30] border border-blue-900/40 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[44px]"
            />
          </div>
        </div>

        {/* Row 2: Site toggles */}
        <div>
          <label className="text-xs font-medium text-gray-300 mb-2 block">
            Job Boards
          </label>
          <div className="flex flex-wrap gap-2">
            {[
              { key: "linkedin", label: "LinkedIn", emoji: "🔗" },
              { key: "indeed", label: "Indeed", emoji: "🔍" },
              { key: "glassdoor", label: "Glassdoor", emoji: "🏢" },
              { key: "zip_recruiter", label: "ZipRecruiter", emoji: "⚡" },
              { key: "google", label: "Google", emoji: "🔎" },
              { key: "bayt", label: "Bayt", emoji: "🌍" },
              { key: "naukri", label: "Naukri", emoji: "🇮🇳" },
              { key: "bdjobs", label: "BDJobs", emoji: "🇧🇩" },
              { key: "hellowork", label: "HelloWork", emoji: "🇫🇷" },
            ].map(({ key, label, emoji }) => (
              <button
                key={key}
                onClick={() => toggleSite(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  jobspySites.includes(key)
                    ? "bg-blue-600/30 border-blue-500/60 text-blue-200"
                    : "bg-[#141e30] border-blue-900/30 text-gray-500 hover:text-gray-300"
                }`}
              >
                {emoji} {label}
              </button>
            ))}
          </div>
        </div>

        {/* Row 3: Results, Country, Job Type, Hours Old */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-300 flex justify-between mb-1.5">
              <span>Results per Site</span>
              <span className="text-blue-400 font-bold">{jobspyResults}</span>
            </label>
            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={jobspyResults}
              onChange={(e) => setJobspyResults(parseInt(e.target.value, 10))}
              className="w-full accent-blue-500 mt-1"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Globe className="h-3.5 w-3.5 text-blue-400" />
              Country (Indeed)
            </label>
            <select
              value={jobspyCountry}
              onChange={(e) => setJobspyCountry(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-[#141e30] border border-blue-900/40 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[44px]"
            >
              <option value="usa">🇺🇸 USA</option>
              <option value="uk">🇬🇧 UK</option>
              <option value="canada">🇨🇦 Canada</option>
              <option value="india">🇮🇳 India</option>
              <option value="germany">🇩🇪 Germany</option>
              <option value="australia">🇦🇺 Australia</option>
              <option value="france">🇫🇷 France</option>
              <option value="netherlands">🇳🇱 Netherlands</option>
              <option value="singapore">🇸🇬 Singapore</option>
              <option value="brazil">🇧🇷 Brazil</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Layers className="h-3.5 w-3.5 text-blue-400" />
              Job Type
            </label>
            <select
              value={jobspyJobType}
              onChange={(e) => setJobspyJobType(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-[#141e30] border border-blue-900/40 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[44px]"
            >
              <option value="">All Types</option>
              <option value="fulltime">Full-Time</option>
              <option value="parttime">Part-Time</option>
              <option value="contract">Contract</option>
              <option value="temporary">Temporary</option>
              <option value="internship">Internship</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-300 flex items-center gap-1.5 mb-1.5">
              Hours Old
            </label>
            <input
              type="number"
              value={jobspyHoursOld}
              onChange={(e) => setJobspyHoursOld(e.target.value)}
              placeholder="e.g. 24, 72"
              className="w-full px-3 py-2.5 rounded-xl bg-[#141e30] border border-blue-900/40 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[44px]"
            />
          </div>
        </div>

        {/* Row 4: Toggles & Submit */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-1">
          <div className="flex items-center gap-5">
            <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={jobspyRemote}
                onChange={(e) => setJobspyRemote(e.target.checked)}
                className="rounded border-blue-800 text-blue-600 focus:ring-blue-500 bg-[#141e30] h-4 w-4"
              />
              <span>Remote Only</span>
            </label>
            <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={jobspyFetchDesc}
                onChange={(e) => setJobspyFetchDesc(e.target.checked)}
                className="rounded border-blue-800 text-blue-600 focus:ring-blue-500 bg-[#141e30] h-4 w-4"
              />
              <span>Fetch Descriptions</span>
            </label>
          </div>

          <button
            onClick={handleJobSpyScrape}
            disabled={isScrapingJobSpy || jobspySites.length === 0}
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors shadow-lg min-h-[44px] shrink-0"
          >
            {isScrapingJobSpy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Scraping Jobs...</span>
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                <span>Scrape Jobs ⚡</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Crawl Runs Monitor */}
      <div className="rounded-2xl border border-purple-900/40 bg-[#1a1130] p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <RotateCcw className="h-4 w-4 text-purple-400" />
              Crawl & Extraction Runs
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Live status from background workers. Completed crawl runs can be extracted directly.
            </p>
          </div>

          <button
            onClick={() => {
              mutateRuns();
              mutateStats();
            }}
            className="p-2 rounded-lg border border-purple-900/50 hover:bg-purple-900/30 text-gray-400 hover:text-white transition-colors"
            title="Refresh Runs"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>

        {runsLoading ? (
          <div className="space-y-3 animate-pulse">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-16 rounded-xl bg-[#231742]" />
            ))}
          </div>
        ) : !runs || runs.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No crawl runs recorded yet. Click "Activate Crawler" above to begin your first run.
          </div>
        ) : (
          <div className="divide-y divide-purple-900/30">
            {runs.map((run) => {
              const isRunning = run.status === "running";
              const isExtracting = extractingRunId === run.id;

              return (
                <div
                  key={run.id}
                  className="py-4 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="flex items-start sm:items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-[#231742] border border-purple-900/50 flex items-center justify-center font-mono font-bold text-sm text-purple-300 shrink-0">
                      #{run.id}
                    </div>

                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-white text-sm uppercase tracking-wide">
                          {run.run_type}
                        </span>

                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            isRunning
                              ? "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 animate-pulse"
                              : run.status === "completed"
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-red-500/20 text-red-300 border border-red-500/30"
                          }`}
                        >
                          {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-ping" />}
                          {run.status}
                        </span>

                        <span className="text-[11px] text-gray-500" suppressHydrationWarning>
                          Started:{" "}
                          {isMounted
                            ? new Date(run.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                            : run.started_at
                            ? run.started_at.slice(11, 16)
                            : ""}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-gray-400">
                        <span>
                          Pages: <strong className="text-gray-200">{run.pages_crawled}</strong>
                        </span>
                        <span>•</span>
                        <span>
                          Links: <strong className="text-gray-200">{run.links_inspected}</strong>
                        </span>
                        {run.errors > 0 && (
                          <>
                            <span>•</span>
                            <span className="text-red-400">
                              Errors: <strong>{run.errors}</strong>
                            </span>
                          </>
                        )}
                      </div>

                      {run.status === "failed" && run.error_message && (
                        <div className="mt-2 text-xs text-red-300 bg-red-950/40 border border-red-800/50 rounded-lg px-2.5 py-1.5 font-mono break-all max-w-xl">
                          <span className="font-semibold text-red-400">Error: </span>
                          {run.error_message}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions per run */}
                  <div className="flex items-center gap-2 self-end sm:self-center">
                    {run.run_type === "crawl" && run.status === "completed" && (
                      <button
                        onClick={() => handleStartExtract(run.id)}
                        disabled={isExtracting}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold transition-colors disabled:opacity-50 min-h-[38px]"
                      >
                        {isExtracting ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="h-3.5 w-3.5" />
                        )}
                        <span>Extract Jobs (Stage 2)</span>
                      </button>
                    )}

                    <Link
                      href={`/jobs`}
                      className="p-2 rounded-lg border border-purple-900/40 text-gray-400 hover:text-white hover:bg-purple-900/30 text-xs min-h-[38px] min-w-[38px] inline-flex items-center justify-center"
                      title="View Discovered Jobs"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

