"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  listApplications,
  updateApplicationStatus,
  type ApplicationOut,
  type ApplicationStatus,
} from "@/lib/api";

const KANBAN: { status: ApplicationStatus; label: string; tone: string }[] = [
  { status: "SAVED", label: "Saved", tone: "border-slate-300" },
  { status: "PREPARING", label: "Preparing", tone: "border-indigo-300" },
  { status: "READY_TO_APPLY", label: "Ready to Apply", tone: "border-cyan-300" },
  { status: "APPLIED", label: "Applied", tone: "border-blue-300" },
  { status: "INTERVIEW", label: "Interview", tone: "border-amber-300" },
  { status: "OFFER", label: "Offer", tone: "border-emerald-300" },
];

const TERMINAL: { status: ApplicationStatus; label: string }[] = [
  { status: "REJECTED", label: "Rejected" },
  { status: "WITHDRAWN", label: "Withdrawn" },
];

const ALL_STATUSES = [...KANBAN.map((k) => k.status), ...TERMINAL.map((t) => t.status)];

function statusTone(status: ApplicationStatus): string {
  switch (status) {
    case "OFFER": return "bg-emerald-50 text-emerald-700";
    case "INTERVIEW": return "bg-amber-50 text-amber-700";
    case "APPLIED": return "bg-blue-50 text-blue-700";
    case "READY_TO_APPLY": return "bg-cyan-50 text-cyan-700";
    case "REJECTED": return "bg-rose-50 text-rose-700";
    default: return "bg-slate-100 text-slate-600";
  }
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<ApplicationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"board" | "list">("board");

  const load = useCallback(async () => {
    try {
      const data = await listApplications();
      setApplications(data.applications);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load applications.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function changeStatus(app: ApplicationOut, status: ApplicationStatus) {
    setError(null);
    try {
      const updated = await updateApplicationStatus(app.id, status);
      setApplications((current) =>
        current?.map((a) => (a.id === updated.id ? updated : a)) ?? null
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status change failed.");
    }
  }

  if (applications === null && !error) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <p className="animate-pulse text-sm font-medium text-slate-500">Loading applications…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Applications</h1>
          <p className="text-sm text-slate-500">
            AI prepares — you review and submit. Track every application here.
          </p>
        </div>
        <div className="flex rounded-lg border border-slate-200 p-0.5">
          {(["board", "list"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold capitalize ${
                view === mode ? "bg-indigo-600 text-white" : "text-slate-600"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <p role="alert" data-testid="apps-error" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {applications?.length === 0 && (
        <div data-testid="empty-apps" className="rounded-2xl border border-dashed border-slate-300 p-12 text-center">
          <p className="text-sm font-medium text-slate-500">
            No applications yet. Find a job and click "Prepare Application".
          </p>
          <Link
            href="/jobs"
            className="mt-4 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            Find Jobs
          </Link>
        </div>
      )}

      {applications && applications.length > 0 && view === "board" && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="kanban-board">
          {KANBAN.map(({ status, label, tone }) => {
            const column = applications.filter((a) => a.status === status);
            return (
              <section key={status} className={`rounded-2xl border-t-4 ${tone} bg-slate-50/70 p-4`}>
                <h2 className="mb-3 flex items-center justify-between text-xs font-bold uppercase tracking-wide text-slate-500">
                  {label}
                  <span className="rounded-full bg-white px-2 py-0.5 text-[10px]">{column.length}</span>
                </h2>
                <div className="space-y-3">
                  {column.map((app) => (
                    <AppCard key={app.id} app={app} onStatus={(s) => changeStatus(app, s)} />
                  ))}
                  {column.length === 0 && (
                    <p className="rounded-xl border border-dashed border-slate-200 p-4 text-center text-[11px] text-slate-400">
                      Nothing here
                    </p>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {applications && applications.length > 0 && view === "list" && (
        <div className="space-y-3" data-testid="apps-list">
          {applications.map((app) => (
            <AppCard key={app.id} app={app} onStatus={(s) => changeStatus(app, s)} expanded />
          ))}
        </div>
      )}

      {applications && applications.some(
        (a) => a.status === "REJECTED" || a.status === "WITHDRAWN"
      ) && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-400">
            Terminal
          </h2>
          <div className="space-y-3">
            {applications
              .filter((a) => a.status === "REJECTED" || a.status === "WITHDRAWN")
              .map((app) => (
                <AppCard key={app.id} app={app} onStatus={(s) => changeStatus(app, s)} />
              ))}
          </div>
        </section>
      )}
    </main>
  );
}

function AppCard({
  app,
  onStatus,
  expanded = false,
}: {
  app: ApplicationOut;
  onStatus: (status: ApplicationStatus) => void;
  expanded?: boolean;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/applications/${app.id}`} className="min-w-0">
          <h3 className="truncate text-sm font-bold text-slate-900 hover:text-indigo-600">
            {app.job.title}
          </h3>
          <p className="truncate text-xs text-slate-500">{app.job.company}</p>
        </Link>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${statusTone(app.status)}`}>
          {app.status.replace("_", " ")}
        </span>
      </div>
      <p className="mt-1.5 text-[11px] font-medium text-slate-400">
        Match: {app.overall_match != null ? `${Math.round(app.overall_match)}%` : "–"}
        {app.applied_at && ` · Applied ${new Date(app.applied_at).toLocaleDateString()}`}
      </p>
      {(expanded || true) && (
        <select
          value={app.status}
          onChange={(event) => onStatus(event.target.value as ApplicationStatus)}
          aria-label={`Change status for ${app.job.title}`}
          className="mt-2 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-[11px] font-semibold text-slate-600"
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      )}
      <div className="mt-2 flex gap-2">
        <Link
          href={`/applications/${app.id}`}
          className="flex-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-center text-[11px] font-bold text-white hover:bg-indigo-700"
        >
          View Copilot
        </Link>
      </div>
    </article>
  );
}
