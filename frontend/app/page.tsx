"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import FileUpload from "./components/FileUpload";
import { startAnalysis, uploadDocuments } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [resume, setResume] = useState<File | null>(null);
  const [jobDescription, setJobDescription] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = resume !== null && jobDescription !== null && !busy;

  async function handleAnalyze() {
    if (!resume || !jobDescription) return;
    setBusy(true);
    setError(null);
    try {
      const upload = await uploadDocuments(resume, jobDescription);
      const started = await startAnalysis(upload.session_id);
      if (started.status === "failed") {
        setError(started.message ?? "Analysis failed. Please try again.");
        return;
      }
      router.push(`/analysis/${upload.session_id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong while analyzing your documents."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col items-center justify-center px-4 py-12">
      <div className="mb-10 text-center">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-4 py-1.5 text-xs font-semibold text-indigo-700">
          Multi-agent AI pipeline · LangGraph powered
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl">
          Job Switch Agent
        </h1>
        <p className="mt-3 text-lg text-slate-500">
          Your AI career team for a smarter job switch.
        </p>
      </div>

      <div className="w-full rounded-2xl border border-slate-200 bg-white/70 p-6 shadow-sm backdrop-blur sm:p-8">
        <div className="grid gap-6 sm:grid-cols-2">
          <FileUpload
            label="Upload Resume"
            hint="Your most recent resume (PDF/TXT)"
            file={resume}
            onFileSelected={setResume}
          />
          <FileUpload
            label="Upload Job Description"
            hint="The role you are targeting (PDF/TXT)"
            file={jobDescription}
            onFileSelected={setJobDescription}
          />
        </div>

        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleAnalyze}
          className={`mt-8 w-full rounded-xl px-6 py-3.5 text-base font-bold text-white transition ${
            canSubmit
              ? "bg-indigo-600 shadow-lg shadow-indigo-200 hover:bg-indigo-700"
              : "cursor-not-allowed bg-slate-300"
          }`}
        >
          {busy ? "Analyzing…" : "Analyze My Match"}
        </button>
        <p className="mt-3 text-center text-xs text-slate-400">
          You will get a candidate profile, job breakdown, transparent match
          score, skill gaps and a personalized 30-day roadmap.
        </p>
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
