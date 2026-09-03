"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import {
  analyzeJob,
  formatSalary,
  getJob,
  type JobDetailResponse,
} from "@/lib/api";

const BREAKDOWN_LABELS: { key: string; label: string }[] = [
  { key: "required_skill_match", label: "Required Skills" },
  { key: "preferred_skill_match", label: "Preferred Skills" },
  { key: "role_match", label: "Role" },
  { key: "experience_match", label: "Experience" },
  { key: "location_match", label: "Location" },
  { key: "salary_match", label: "Salary" },
];

function scoreTone(score: number): string {
  if (score >= 75) return "bg-emerald-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-rose-500";
}

function JobDetailInner() {
  const params = useParams<{ jobId: string }>();
  const search = useSearchParams();
  const resumeSessionId = search?.get("session");
  // Defensive: strip any accidental query junk that ended up in the path
  // (e.g. /jobs/abc123session=... from older links).
  const jobId = (params?.jobId ?? "").split(/[?&]/)[0];

  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    getJob(jobId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load job.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function handleAnalyze() {
    if (!resumeSessionId || !detail?.job.id) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const started = await analyzeJob(detail.job.id, resumeSessionId);
      if (started.session_id) {
        window.location.href = `/analysis/${started.session_id}`;
        return;
      }
      setAnalyzeError(started.message ?? "Analysis could not be completed.");
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (error && !detail) {
    return (
      <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Job unavailable</h1>
        <p className="mt-2 text-sm text-slate-500">{error}</p>
        <Link
          href="/jobs"
          className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Back to job search
        </Link>
      </main>
    );
  }

  if (!detail) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <p className="animate-pulse text-sm font-medium text-slate-500">Loading job…</p>
      </main>
    );
  }

  const { job, sources, match, explanation } = detail;
  const postedLabel = job.posted_at
    ? new Date(job.posted_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;
  const salaryLabel = formatSalary(job);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10">
      <Link href="/jobs" className="text-sm font-semibold text-indigo-600 hover:underline">
        ← Back to results
      </Link>

      {/* ---------------- Job information ---------------- */}
      <header className="mb-8 mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              {job.title}
            </h1>
            <p className="mt-1 text-sm text-slate-500">{job.company}</p>
          </div>
          {match && (
            <div data-testid="overall-match" className="text-right">
              <span className="text-4xl font-extrabold text-indigo-600">
                {Math.round(match.overall_match)}%
              </span>
              <span className="block text-xs font-medium uppercase tracking-wide text-slate-400">
                Overall Match
              </span>
            </div>
          )}
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["Location", job.location ?? "unknown"],
            ["Work mode", job.work_mode],
            [
              "Experience",
              job.experience_min != null
                ? `${job.experience_min}${job.experience_max != null ? `–${job.experience_max}` : "+"} yrs`
                : "unknown",
            ],
            ["Salary", salaryLabel ?? "undisclosed"],
            ["Posted", postedLabel ?? "unknown"],
            ["Source", sources.map((s) => s.source).join(", ") || job.source],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-50 p-2.5">
              <dt className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                {label}
              </dt>
              <dd className="mt-0.5 truncate text-sm font-semibold text-slate-700">
                {value}
              </dd>
            </div>
          ))}
        </dl>

        {job.application_url && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-4 inline-block text-sm font-semibold text-indigo-600 hover:underline"
          >
            View original posting ↗
          </a>
        )}
      </header>

      {match && (
        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-bold text-slate-900">Match Analysis</h2>
          <ul className="space-y-2.5">
            {BREAKDOWN_LABELS.map(({ key, label }) => {
              const value = match.breakdown[key as keyof typeof match.breakdown];
              if (value == null) return null;
              const rounded = Math.round(value);
              return (
                <li key={key}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-700">{label}</span>
                    <span className="font-semibold text-slate-900">{rounded}%</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full ${scoreTone(rounded)}`}
                      style={{ width: `${Math.min(100, rounded)}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {(match || job.required_skills.length > 0) && (
        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-bold text-slate-900">Skills</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Matched",
                items: match?.matched_skills ?? [],
                chip: "border-emerald-200 bg-emerald-50 text-emerald-700",
                prefix: "✓",
              },
              {
                title: "Partial",
                items: match?.partial_skills ?? [],
                chip: "border-amber-200 bg-amber-50 text-amber-700",
                prefix: "≈",
              },
              {
                title: "Missing",
                items: match?.missing_skills ?? [],
                chip: "border-rose-200 bg-rose-50 text-rose-700",
                prefix: "✕",
              },
            ].map(({ title, items, chip, prefix }) => (
              <div key={title} className="rounded-xl border border-slate-100 p-4">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
                  {title}
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {items.length === 0 && (
                    <span className="text-xs text-slate-400">None</span>
                  )}
                  {items.map((skill) => (
                    <span
                      key={skill}
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${chip}`}
                    >
                      {prefix} {skill}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {explanation && (
        <section className="mb-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-6">
            <h2 className="mb-3 text-base font-bold text-emerald-800">
              Why this job matches you
            </h2>
            <ul className="space-y-1.5 text-sm text-emerald-900">
              {explanation.strengths.length === 0 && (
                <li className="text-emerald-700/70">No strong signals found.</li>
              )}
              {explanation.strengths.map((line) => (
                <li key={line}>✓ {line}</li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-amber-100 bg-amber-50/60 p-6">
            <h2 className="mb-3 text-base font-bold text-amber-800">Main gaps</h2>
            <ul className="space-y-1.5 text-sm text-amber-900">
              {explanation.gaps.length === 0 && (
                <li className="text-amber-700/70">No significant gaps detected.</li>
              )}
              {explanation.gaps.map((line) => (
                <li key={line}>⚠ {line}</li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-3 text-lg font-bold text-slate-900">Job Description</h2>
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-600">
          {job.description || "No description available."}
        </pre>
        {job.preferred_skills.length > 0 && !match && (
          <p className="mt-4 text-xs text-slate-400">
            Preferred skills: {job.preferred_skills.join(", ")}
          </p>
        )}
      </section>

      <button
        type="button"
        onClick={handleAnalyze}
        disabled={analyzing || !resumeSessionId}
        title={!resumeSessionId ? "Requires a resume session (?session=...)" : undefined}
        className={`w-full rounded-xl px-6 py-3.5 text-base font-bold text-white transition ${
          analyzing || !resumeSessionId
            ? "cursor-not-allowed bg-slate-300"
            : "bg-indigo-600 shadow-lg shadow-indigo-200 hover:bg-indigo-700"
        }`}
      >
        {analyzing ? "Running Phase 1 analysis…" : "Analyze & Prepare"}
      </button>
      {!resumeSessionId && (
        <p className="mt-3 text-center text-xs text-slate-400">
          Personalized analysis needs your resume session — start from the job
          search page with <code>?session=…</code>.
        </p>
      )}
      {analyzeError && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {analyzeError}
        </p>
      )}
    </main>
  );
}

export default function JobDetailPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-[60vh] items-center justify-center">
          <p className="animate-pulse text-sm font-medium text-slate-500">Loading…</p>
        </main>
      }
    >
      <JobDetailInner />
    </Suspense>
  );
}
