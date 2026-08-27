"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import JobCard from "../components/jobs/JobCard";
import JobSearchForm, { type JobSearchFormValues } from "../components/jobs/JobSearchForm";
import {
  getRecommendations,
  searchJobs,
  type ProviderStatusInfo,
  type SearchMetadata,
  type Recommendation,
} from "@/lib/api";

type SortKey = "best" | "newest" | "salary" | "experience";

const SORTERS: Record<SortKey, (a: Recommendation, b: Recommendation) => number> = {
  best: (a, b) => b.match.overall_match - a.match.overall_match,
  newest: (a, b) =>
    new Date(b.job.posted_at ?? 0).getTime() - new Date(a.job.posted_at ?? 0).getTime(),
  salary: (a, b) => (b.job.salary_max ?? 0) - (a.job.salary_max ?? 0),
  experience: (a, b) =>
    (b.match.breakdown.experience_match ?? 0) - (a.match.breakdown.experience_match ?? 0),
};

function JobsPageInner() {
  const params = useSearchParams();
  const resumeSessionId = params?.get("session") ?? null;
  const analyzeRequested = params?.get("analyze") === "1" ? params.get("job") : null;

  const [busy, setBusy] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Recommendation[] | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("best");
  const [sources, setSources] = useState<ProviderStatusInfo[] | null>(null);
  const [meta, setMeta] = useState<SearchMetadata | null>(null);

  const sorted = useMemo(() => {
    if (!results) return null;
    return [...results].sort(SORTERS[sortKey]);
  }, [results, sortKey]);

  const runSearch = useCallback(
    async (values: JobSearchFormValues) => {
      if (!resumeSessionId) {
        setError("Missing resume session. Analyze your resume first.");
        return;
      }
      setBusy(true);
      setError(null);
      setResults(null);
      setSources(null);
      setMeta(null);
      try {
        const started = await searchJobs({
          session_id: resumeSessionId,
          keywords: values.keywords
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean),
          locations: values.locations
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean),
          remote: values.remote || values.work_modes.includes("remote"),
          work_modes: values.work_modes,
          experience_min: values.experience_min,
          experience_max: values.experience_max,
          min_match_percent: values.min_match_percent,
        });
        setSources(started.sources ?? null);
        setMeta(started.metadata ?? null);
        if (started.status !== "completed") {
          setError(started.message ?? "Job discovery failed. Please try again.");
          return;
        }
        const recs = await getRecommendations(
          started.search_id,
          values.min_match_percent ?? undefined
        );
        setResults(recs.recommendations);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setBusy(false);
      }
    },
    [resumeSessionId]
  );

  useEffect(() => {
    if (!analyzeRequested) return;
    // Direct "Analyze Job" entries re-run a sensible default search first so the
    // user lands on the results grid.
    void runSearch({
      keywords: "",
      locations: "",
      remote: true,
      work_modes: ["remote", "hybrid", "onsite"],
      experience_min: null,
      experience_max: null,
      min_match_percent: null,
    });
  }, [analyzeRequested, runSearch]);

  if (!resumeSessionId) {
    return (
      <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Find Your Next Job</h1>
        <p className="mt-2 text-sm text-slate-500">
          Job discovery is personalized with your resume profile. Upload your
          resume and run an analysis first.
        </p>
        <Link
          href="/"
          className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Upload resume
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
          Find Your Next Job
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Personalized discovery powered by your candidate profile and live
          job sources (Remotive & more).
        </p>
      </header>

      <div className="mb-8">
        <JobSearchForm busy={busy} onSubmit={runSearch} />
        {error && (
          <p
            role="alert"
            data-testid="jobs-error"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </p>
        )}
      </div>

      {loadingResults && (
        <p className="animate-pulse text-sm font-medium text-slate-500">Loading jobs…</p>
      )}

      {sources && sources.length > 0 && (
        <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4" data-testid="source-status">
          <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">
            Sources queried
          </p>
          <div className="flex flex-wrap gap-2">
            {sources.map((s) => (
              <span
                key={s.name}
                className={`rounded-full px-3 py-1 text-[11px] font-semibold ${
                  s.status === "error"
                    ? "bg-red-50 text-red-600"
                    : s.status === "success"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-slate-100 text-slate-500"
                }`}
              >
                {s.status === "success" ? "✓" : s.status === "error" ? "✗" : "…"} {s.name}
                {s.status === "success" ? ` (${s.count})` : ""}
              </span>
            ))}
            {meta && (meta.live_results || meta.cached_results) && (
              <span className="rounded-full bg-indigo-50 px-3 py-1 text-[11px] font-semibold text-indigo-600">
                {meta.cached_results
                  ? "Served from cache"
                  : `Live results${meta.duplicates_removed != null ? ` · ${meta.duplicates_removed} duplicates removed` : ""}`}
              </span>
            )}
          </div>
          {sources.some((s) => s.status === "error") && (
            <p className="mt-2 text-[11px] text-amber-600">
              Some job sources are temporarily unavailable.
            </p>
          )}
        </div>
      )}

      {sorted && (
        <>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-900">
              Recommended Jobs{" "}
              <span className="text-sm font-medium text-slate-400">
                ({sorted.length})
              </span>
            </h2>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              Sort
              <select
                value={sortKey}
                onChange={(event) => setSortKey(event.target.value as SortKey)}
                className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs font-semibold text-slate-700"
              >
                <option value="best">Best Match</option>
                <option value="newest">Newest</option>
                <option value="salary">Salary</option>
                <option value="experience">Experience Fit</option>
              </select>
            </label>
          </div>

          {sorted.length === 0 ? (
            <div
              data-testid="empty-state"
              className="rounded-2xl border border-dashed border-slate-300 p-12 text-center"
            >
              <p className="text-sm font-medium text-slate-500">
                No jobs matched your preferences. Try widening the filters or
                lowering the minimum match.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {sorted.map((rec) => (
                <JobCard
                  key={`${rec.rank}-${rec.job.id}`}
                  recommendation={rec}
                  sessionQuery={`session=${resumeSessionId}`}
                />
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}

export default function JobsPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <p className="animate-pulse text-sm font-medium text-slate-500">Loading…</p>
        </main>
      }
    >
      <JobsPageInner />
    </Suspense>
  );
}

