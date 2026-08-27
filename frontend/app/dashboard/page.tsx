"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getAnalytics,
  type ApplicationAnalyticsPayload,
} from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<ApplicationAnalyticsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAnalytics()
      .then(setData)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load analytics.")
      );
  }, []);

  const a = data?.analytics;

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight text-slate-900">
        Career Overview
      </h1>
      <p className="mb-8 text-sm text-slate-500">
        Your pipeline at a glance — deterministic stats computed from your own
        application data.
      </p>

      {error && (
        <p role="alert" className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="mb-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6" data-testid="summary-cards">
        {[
          ["Applications", a?.total_applications],
          ["Preparing", a ? a.preparing + a.saved : undefined],
          ["Applied", a?.applied],
          ["Interviews", a?.interviews],
          ["Offers", a?.offers],
          ["Rejected", a?.rejected],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{label}</p>
            <p className="mt-1 text-3xl font-extrabold text-slate-900">{value ?? "–"}</p>
          </div>
        ))}
      </div>

      {a && (
        <section className="mb-10 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Application → Interview</h2>
            <p className="mt-2 text-3xl font-extrabold text-indigo-600">{a.interview_rate}%</p>
            <p className="text-xs text-slate-400">of applications that reached "Applied"</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Interview → Offer</h2>
            <p className="mt-2 text-3xl font-extrabold text-emerald-600">{a.offer_rate}%</p>
            <p className="text-xs text-slate-400">offer conversion</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">Avg. Match Score</h2>
            <p className="mt-2 text-3xl font-extrabold text-amber-600">
              {a.average_match_score != null ? `${Math.round(a.average_match_score)}%` : "–"}
            </p>
            <p className="text-xs text-slate-400">across matched jobs</p>
          </div>
        </section>
      )}

      {data?.insights && (
        <section className="mb-10 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-6">
          <h2 className="mb-3 text-base font-bold text-indigo-800">Smart Insights</h2>
          {data.insights.sufficient_data ? (
            <ul className="list-inside list-disc space-y-1 text-sm text-indigo-900">
              {data.insights.insights.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-indigo-700/80">
              Not enough application history to generate reliable insights.
            </p>
          )}
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          href="/jobs"
          className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Find Jobs →
        </Link>
        <Link
          href="/applications"
          className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          View Applications
        </Link>
      </div>
    </main>
  );
}
