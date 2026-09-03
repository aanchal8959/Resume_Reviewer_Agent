"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import CandidateProfileView from "../../components/CandidateProfile";
import JobProfileView from "../../components/JobProfile";
import MatchScoreView from "../../components/MatchScore";
import RoadmapView from "../../components/Roadmap";
import SkillGapView from "../../components/SkillGap";
import { getAnalysis, type AnalysisResult } from "@/lib/api";

export default function AnalysisPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    getAnalysis(sessionId)
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load analysis.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <p className="animate-pulse text-sm font-medium text-slate-500">
          Loading analysis…
        </p>
      </main>
    );
  }

  if (error || !result) {
    return (
      <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Analysis unavailable</h1>
        <p className="mt-2 text-sm text-slate-500">{error ?? "Session not found."}</p>
        <Link
          href="/"
          className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Start over
        </Link>
      </main>
    );
  }

  const warnings = result.errors.filter((e) => e.startsWith("[warning]"));
  const fatalErrors = result.errors.filter((e) => !e.startsWith("[warning]"));
  const failed =
    result.status === "failed" ||
    fatalErrors.length > 0 ||
    result.match_score === null;

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
            Analysis Dashboard
          </h1>
          <p className="text-xs text-slate-400">Session {result.session_id}</p>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/jobs?session=${result.session_id}`}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
          >
            Find Jobs →
          </Link>
          <Link
            href="/"
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
          >
            New analysis
          </Link>
        </div>
      </header>

      {warnings.length > 0 && (
        <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          {warnings.map((w) => (
            <p key={w} className="text-xs font-medium text-amber-800">{w}</p>
          ))}
        </div>
      )}

      {failed && (
        <div className="mb-8 rounded-xl border border-red-200 bg-red-50 px-5 py-4">
          <p className="text-sm font-semibold text-red-800">
            This analysis did not complete successfully.
          </p>
          {(result.error || result.errors[0]) && (
            <p className="mt-1 text-xs text-red-600">{result.error ?? result.errors[0]}</p>
          )}
        </div>
      )}

      {result.candidate_profile && result.job_profile && (
        <div className="mb-8 grid gap-6 lg:grid-cols-2">
          <CandidateProfileView profile={result.candidate_profile} />
          <JobProfileView profile={result.job_profile} />
        </div>
      )}

      {result.match_score && (
        <div className="mb-8">
          <MatchScoreView score={result.match_score} />
        </div>
      )}

      {result.skill_gap && (
        <div className="mb-8">
          <SkillGapView skillGap={result.skill_gap} />
        </div>
      )}

      {result.roadmap && (
        <RoadmapView roadmap={result.roadmap} />
      )}
    </main>
  );
}
