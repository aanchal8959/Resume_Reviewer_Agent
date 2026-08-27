"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createApplication, formatSalary, timeAgo, type Recommendation } from "@/lib/api";

function matchTone(score: number): string {
  if (score >= 75) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (score >= 55) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
}

export default function JobCard({
  recommendation,
  sessionQuery,
}: {
  recommendation: Recommendation;
  sessionQuery: string;
}) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const { job, match } = recommendation;
  const overall = Math.round(match.overall_match);
  const salary = formatSalary(job);
  const matchedPreview = match.matched_skills.slice(0, 4);
  const gapPreview = [...match.partial_skills, ...match.missing_skills].slice(0, 3);

  const resumeSessionId = new URLSearchParams(
    sessionQuery.startsWith("?") ? sessionQuery.slice(1) : sessionQuery
  ).get("session");

  async function handlePrepare() {
    if (!job.id || creating) return;
    setCreating(true);
    try {
      const created = await createApplication(job.id, resumeSessionId ?? undefined);
      router.push(`/applications/${created.application_id}`);
    } catch {
      setCreating(false);
    }
  }

  return (
    <article className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-bold text-slate-900">{job.title}</h3>
          <p className="text-sm text-slate-500">{job.company}</p>
        </div>
        <span
          data-testid="match-score"
          className={`shrink-0 rounded-full border px-3 py-1 text-sm font-extrabold ${matchTone(overall)}`}
        >
          {overall}%
        </span>
      </div>

      <p className="mb-3 text-xs font-medium text-slate-500">
        {[job.location ?? "Unknown location", job.work_mode !== "unknown" ? job.work_mode : null]
          .filter(Boolean)
          .join(" • ")}
        {job.experience_min != null &&
          ` • ${job.experience_min}+${job.experience_max ? `–${job.experience_max}` : "+"} yrs`}
      </p>

      <p className="mb-3 text-[11px] font-medium text-slate-400">
        Posted: {timeAgo(job.posted_at)} · Source:{" "}
        <span
          data-testid={`source-${job.source.toLowerCase()}`}
          className="font-semibold text-indigo-600"
        >
          {job.source}
        </span>
        {job.application_url == null && (
          <span className="ml-1 text-slate-300">· Application link unavailable</span>
        )}
      </p>

      <div className="mb-3 flex flex-wrap gap-1.5" data-testid="skill-chips">
        {matchedPreview.map((skill) => (
          <span
            key={`m-${skill}`}
            className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700"
          >
            ✓ {skill}
          </span>
        ))}
        {gapPreview.map((skill) => (
          <span
            key={`g-${skill}`}
            className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700"
          >
            ⚠ {skill}
          </span>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        <span className="text-sm font-bold text-slate-800">
          {salary ?? "Salary undisclosed"}
        </span>
        <div className="flex gap-2">
          <Link
            href={`/jobs/${job.id}${sessionQuery ? `?${sessionQuery}` : ""}`}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Details
          </Link>
          <button
            type="button"
            onClick={handlePrepare}
            disabled={creating}
            data-testid={`prepare-${job.id}`}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Prepare Application"}
          </button>
        </div>
      </div>
    </article>
  );
}
