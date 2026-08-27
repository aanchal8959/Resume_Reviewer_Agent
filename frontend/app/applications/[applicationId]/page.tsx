"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  approveCoverLetter,
  approveResume,
  editCoverLetter,
  exportUrl,
  generateCoverLetter,
  generateQuestions,
  getApplication,
  prepareApplication,
  researchCompany,
  tailorResume,
  toggleChecklistItem,
  updateApplicationNotes,
  updateApplicationStatus,
  type ApplicationDetail,
  type ApplicationStatus,
} from "@/lib/api";

const TABS = ["Resume", "Cover Letter", "Company", "Questions", "Checklist"] as const;
type Tab = (typeof TABS)[number];

const STATUSES: ApplicationStatus[] = [
  "SAVED", "PREPARING", "READY_TO_APPLY", "APPLIED", "OA_RECEIVED",
  "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN",
];

export default function ApplicationCopilotPage() {
  const params = useParams<{ applicationId: string }>();
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Resume");
  const [notesDraft, setNotesDraft] = useState("");
  const [letterDraft, setLetterDraft] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getApplication(params.applicationId);
      setDetail(data);
      setNotesDraft(data.notes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load application.");
    }
  }, [params?.applicationId]);

  useEffect(() => {
    if (params?.applicationId) void load();
  }, [params?.applicationId, load]);

  async function run(action: string, fn: () => Promise<ApplicationDetail>) {
    setBusy(action);
    setError(null);
    try {
      setDetail(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed.`);
    } finally {
      setBusy(null);
    }
  }

  if (error && !detail) {
    return (
      <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Application unavailable</h1>
        <p className="mt-2 text-sm text-slate-500">{error}</p>
        <Link href="/applications" className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white">
          All applications
        </Link>
      </main>
    );
  }

  if (!detail) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="animate-pulse text-sm font-medium text-slate-500">Loading copilot…</p>
      </main>
    );
  }

  const resume = detail.tailored_resume;
  const letter = detail.cover_letter;
  const company = detail.company_info;
  const warnings = [
    ...(detail.warnings ?? []),
    ...(detail.message ? [detail.message] : []),
  ];

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8">
      {/* ------------------------- header ------------------------- */}
      <Link href="/applications" className="text-sm font-semibold text-indigo-600 hover:underline">
        ← Applications
      </Link>
      <header className="my-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
              Application Copilot
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              <span className="font-semibold">{detail.job.title}</span> · {detail.job.company}
              {detail.job.location ? ` · ${detail.job.location}` : ""}
            </p>
            {detail.overall_match != null && (
              <span className="mt-2 inline-block rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-bold text-emerald-700">
                Match {Math.round(detail.overall_match)}%
              </span>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <select
              value={detail.status}
              onChange={(event) =>
                run("status", () =>
                  updateApplicationStatus(detail.id, event.target.value as ApplicationStatus)
                )
              }
              aria-label="Application status"
              className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700"
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            {detail.job.application_url && (
              <a
                href={detail.job.application_url}
                target="_blank"
                rel="noreferrer noopener"
                className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white hover:bg-slate-900"
              >
                Open Application Website ↗
              </a>
            )}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("prepare", () => prepareApplication(detail.id))}
            className={`rounded-lg px-4 py-2 text-xs font-bold text-white ${
              busy ? "cursor-not-allowed bg-slate-300" : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            {busy === "prepare" ? "Preparing everything…" : "⚡ Prepare Everything"}
          </button>
          {([
            ["Tailor Resume", "tailor", () => tailorResume(detail.id)],
            ["Cover Letter", "letter", () => generateCoverLetter(detail.id)],
            ["Research Company", "research", () => researchCompany(detail.id)],
            ["Questions", "questions", () => generateQuestions(detail.id)],
          ] as [string, string, () => Promise<ApplicationDetail>][]).map(
            ([label, key, fn]) => (
              <button
                key={key}
                type="button"
                disabled={busy !== null}
                onClick={() => run(key, fn)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {busy === key ? "Working…" : label}
              </button>
            )
          )}
        </div>
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[11px] font-medium text-amber-800">
          AI prepares your application. You review and submit it — nothing is ever
          sent automatically.
        </p>
        {(warnings.length > 0 || busy) && (
          <div className="mt-3 space-y-1" role="status">
            {busy && <p className="animate-pulse text-xs font-medium text-indigo-600">Working on “{busy}”…</p>}
            {warnings.map((w) => (
              <p key={w} data-testid="copilot-warning" className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{w}</p>
            ))}
          </div>
        )}
        {error && (
          <p role="alert" data-testid="copilot-error" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
        )}
      </header>

      {/* ------------------------- tabs ------------------------- */}
      <div className="mb-4 flex gap-1 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-xs font-bold transition ${
              tab === t ? "bg-indigo-600 text-white" : "bg-white text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ------------------------- RESUME ------------------------- */}
      {tab === "Resume" && (
        <section data-testid="tab-resume" className="space-y-4">
          {!resume && (
            <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              Not tailored yet — click “Tailor Resume” or “Prepare Everything”.
            </p>
          )}
          {resume && (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-base font-bold text-slate-900">Tailored Resume</h2>
                  <span
                    data-testid="truthfulness-badge"
                    className={`rounded-full px-3 py-1 text-[10px] font-bold uppercase ${
                      resume.unsupported_claims_count === 0
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-rose-50 text-rose-700"
                    }`}
                  >
                    {resume.truthfulness_checked
                      ? resume.unsupported_claims_count === 0
                        ? "Truthfulness check passed"
                        : `${resume.unsupported_claims_count} unsupported claim(s)`
                      : "Not checked"}
                  </span>
                </div>
                <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-4 font-sans text-sm leading-relaxed text-slate-700">
                  {resume.content_markdown}
                </pre>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" onClick={() => run("approve", () => approveResume(detail.id))}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-emerald-700">
                    ✓ Approve this version
                  </button>
                  {(["md", "txt", "pdf"] as const).map((fmt) => (
                    <a key={fmt} href={exportUrl(detail.id, "resume", fmt)}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">
                      Download .{fmt}
                    </a>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="change-log">
                <h3 className="mb-3 text-sm font-bold text-slate-800">What changed</h3>
                <ul className="space-y-3">
                  {resume.changes.map((change, index) => (
                    <li key={index} className={`rounded-xl p-3 ${change.supported ? "bg-slate-50" : "bg-rose-50"}`}>
                      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wide">
                        <span className="text-slate-400">{change.section}</span>
                        <span className="rounded-full bg-white px-2 py-0.5 text-indigo-600">{change.type}</span>
                        {!change.supported && (
                          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-rose-700">unsupported</span>
                        )}
                      </div>
                      <p className="mt-1.5 text-xs text-slate-500 line-through decoration-slate-300">{change.original}</p>
                      <p className="mt-1 text-xs font-medium text-slate-800">{change.updated}</p>
                      {change.reason && <p className="mt-1 text-[11px] text-slate-400">Reason: {change.reason}</p>}
                      {change.warning && (
                        <p className="mt-1 text-[11px] font-semibold text-rose-600">⚠ {change.warning}</p>
                      )}
                    </li>
                  ))}
                </ul>
                {resume.recommendations.length > 0 && (
                  <ul className="mt-4 space-y-1 text-xs text-indigo-700">
                    {resume.recommendations.map((rec) => <li key={rec}>→ {rec}</li>)}
                  </ul>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {/* ------------------------- COVER LETTER ------------------------- */}
      {tab === "Cover Letter" && (
        <section data-testid="tab-cover-letter" className="space-y-4">
          {!letter && (
            <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No cover letter yet — click “Cover Letter” to generate one.
            </p>
          )}
          {letter && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-slate-900">
                  Cover Letter{" "}
                  <span className="text-xs font-medium text-slate-400">
                    ({letter.word_count} words · {letter.generated_with})
                  </span>
                </h2>
                {letter.approved && (
                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-[10px] font-bold uppercase text-emerald-700">
                    Approved
                  </span>
                )}
              </div>
              <textarea
                value={letterDraft ?? letter.content_text}
                onChange={(event) => setLetterDraft(event.target.value)}
                rows={16}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4 font-sans text-sm leading-relaxed text-slate-700 focus:border-indigo-400 focus:outline-none"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={letterDraft === null || letterDraft === letter.content_text}
                  onClick={() => run("save-letter", async () => {
                    const updated = await editCoverLetter(detail.id, letterDraft as string);
                    setLetterDraft(null);
                    return updated;
                  })}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  Save edits
                </button>
                <button type="button" onClick={() => run("approve-letter", () => approveCoverLetter(detail.id))}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-emerald-700">
                  ✓ Approve
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await navigator.clipboard.writeText(letter.content_text);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
                {(["txt", "pdf"] as const).map((fmt) => (
                  <a key={fmt} href={exportUrl(detail.id, "cover-letter", fmt)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">
                    Download .{fmt}
                  </a>
                ))}
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => { setLetterDraft(null); return run("regen-letter", () => generateCoverLetter(detail.id, true)); }}
                  className="ml-auto rounded-lg border border-amber-200 px-3 py-1.5 text-[11px] font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                >
                  Regenerate
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* ------------------------- COMPANY ------------------------- */}
      {tab === "Company" && (
        <section data-testid="tab-company" className="space-y-4">
          {!company && (
            <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No company research yet — click “Research Company”.
            </p>
          )}
          {company && (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h2 className="text-base font-bold text-slate-900">{company.name}</h2>
                  <p className="text-xs text-slate-500">
                    {[company.industry, company.headquarters, company.company_size]
                      .filter(Boolean).join(" · ") || "Details not available"}
                  </p>
                  {company.description && (
                    <p className="mt-3 text-sm leading-relaxed text-slate-600">{company.description}</p>
                  )}
                  {company.products_services.length > 0 && (
                    <>
                      <h3 className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-400">Products / Services</h3>
                      <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
                        {company.products_services.map((p) => <li key={p}>{p}</li>)}
                      </ul>
                    </>
                  )}
                  {company.website && (
                    <a href={company.website} target="_blank" rel="noreferrer noopener"
                      className="mt-4 inline-block text-xs font-semibold text-indigo-600 hover:underline">
                      Website ↗
                    </a>
                  )}
                </div>

                {detail.company_insights && (
                  <div className="space-y-4">
                    <InsightBlock title="Why this role matters" body={detail.company_insights.why_role_matters} />
                    <InsightBlock title="Technology environment" items={detail.company_insights.technology_environment} />
                    <InsightBlock title="Interview preparation clues" items={detail.company_insights.interview_prep_areas} />
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {/* ------------------------- QUESTIONS ------------------------- */}
      {tab === "Questions" && (
        <section data-testid="tab-questions" className="space-y-3">
          {detail.questions.length === 0 && (
            <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No questions yet — click “Questions”.
            </p>
          )}
          {detail.questions.map((qa, index) => (
            <article key={index} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold uppercase text-indigo-600">
                  {qa.category}
                </span>
                <h3 className="text-sm font-bold text-slate-900">{qa.question}</h3>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                {qa.suggested_answer}
              </p>
            </article>
          ))}
        </section>
      )}

      {/* ------------------------- CHECKLIST ------------------------- */}
      {tab === "Checklist" && (
        <section data-testid="tab-checklist" className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-base font-bold text-slate-900">Preparation checklist</h2>
            <ul className="space-y-2">
              {detail.checklist.map((item) => (
                <li key={item.key}>
                  <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={item.done}
                      onChange={(event) =>
                        run(`check-${item.key}`, async () => {
                          await toggleChecklistItem(detail.id, item.key, event.target.checked);
                          return getApplication(detail.id);
                        })
                      }
                      className="h-4 w-4 accent-indigo-600"
                    />
                    <span className={`text-sm ${item.done ? "text-slate-400 line-through" : "text-slate-700"}`}>
                      {item.done ? "✓" : "□"} {item.label}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-2 text-base font-bold text-slate-900">Personal notes</h2>
              <textarea
                value={notesDraft}
                onChange={(event) => setNotesDraft(event.target.value)}
                rows={4}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 focus:border-indigo-400 focus:outline-none"
                placeholder="Recruiter names, referral codes, talking points…"
              />
              <button
                type="button"
                disabled={notesDraft === detail.notes}
                onClick={() => run("notes", () => updateApplicationNotes(detail.id, notesDraft))}
                className="mt-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-indigo-700 disabled:opacity-40"
              >
                Save notes
              </button>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="timeline">
              <h2 className="mb-3 text-base font-bold text-slate-900">Timeline</h2>
              <ol className="relative space-y-3 border-l-2 border-slate-100 pl-4">
                {detail.timeline.map((event, index) => (
                  <li key={event.id ?? index} className="text-xs">
                    <span className="absolute -left-[5px] h-2 w-2 rounded-full bg-indigo-400" style={{ marginTop: 4 }} />
                    <span className="font-semibold text-slate-700">{event.event.replace(/_/g, " ")}</span>
                    {event.notes && <span className="text-slate-400"> — {event.notes}</span>}
                    <span className="block text-[10px] text-slate-400">
                      {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                    </span>
                  </li>
                ))}
              </ol>
            </div>

            {detail.job.application_url && (
              <a
                href={detail.job.application_url}
                target="_blank"
                rel="noreferrer noopener"
                className="block rounded-xl bg-slate-800 px-4 py-3 text-center text-xs font-bold text-white hover:bg-slate-900"
              >
                Open Application Website ↗ (you submit — we never do)
              </a>
            )}
          </div>
        </section>
      )}
    </main>
  );
}

function InsightBlock({ title, body, items }: { title: string; body?: string; items?: string[] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">{title}</h3>
      {body && <p className="text-sm leading-relaxed text-slate-600">{body}</p>}
      {items && (
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
          {items.length === 0 ? <li className="list-none text-slate-400">Not available.</li> :
            items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}
