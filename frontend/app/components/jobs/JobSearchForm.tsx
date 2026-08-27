"use client";

import { useState } from "react";

import type { WorkMode } from "@/lib/api";

export interface JobSearchFormValues {
  keywords: string;
  locations: string;
  remote: boolean | null;
  work_modes: WorkMode[];
  experience_min: number | null;
  experience_max: number | null;
  min_match_percent: number | null;
}

const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

export default function JobSearchForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (values: JobSearchFormValues) => void;
}) {
  const [keywords, setKeywords] = useState("GenAI Engineer");
  const [locations, setLocations] = useState("Bangalore, Pune, Hyderabad");
  const [remote, setRemote] = useState<boolean>(true);
  const [workModes, setWorkModes] = useState<WorkMode[]>(["remote", "hybrid"]);
  const [expMin, setExpMin] = useState("2");
  const [expMax, setExpMax] = useState("4");
  const [minMatch, setMinMatch] = useState("60");

  function toggleMode(mode: WorkMode) {
    setWorkModes((current) =>
      current.includes(mode)
        ? current.filter((m) => m !== mode)
        : [...current, mode]
    );
  }

  return (
    <form
      className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (busy) return;
        const parseNum = (value: string): number | null => {
          const parsed = parseFloat(value);
          return Number.isFinite(parsed) ? parsed : null;
        };
        onSubmit({
          keywords,
          locations,
          remote,
          work_modes: workModes,
          experience_min: parseNum(expMin),
          experience_max: parseNum(expMax),
          min_match_percent: parseNum(minMatch),
        });
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-700">
            Target Role
          </span>
          <input
            type="text"
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
            placeholder="e.g. GenAI Engineer"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-700">
            Locations
          </span>
          <input
            type="text"
            value={locations}
            onChange={(event) => setLocations(event.target.value)}
            placeholder="Comma separated, e.g. Pune, Bangalore"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <div>
          <span className="mb-1 block text-sm font-semibold text-slate-700">
            Experience (years)
          </span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              value={expMin}
              onChange={(event) => setExpMin(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <span className="text-sm text-slate-400">to</span>
            <input
              type="number"
              min={0}
              value={expMax}
              onChange={(event) => setExpMax(event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
          </div>
        </div>
        <div>
          <span className="mb-1 block text-sm font-semibold text-slate-700">
            Minimum Match (%)
          </span>
          <input
            type="number"
            min={0}
            max={100}
            value={minMatch}
            onChange={(event) => setMinMatch(event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <span className="mb-1.5 block text-sm font-semibold text-slate-700">
            Work Mode
          </span>
          <div className="flex gap-2">
            {WORK_MODES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => toggleMode(value)}
                className={`rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                  workModes.includes(value)
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={remote}
            onChange={(event) => setRemote(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300 accent-indigo-600"
          />
          Open to remote roles anywhere
        </label>
      </div>

      <button
        type="submit"
        disabled={busy}
        className={`w-full rounded-xl px-6 py-3 text-base font-bold text-white transition ${
          busy
            ? "cursor-not-allowed bg-slate-300"
            : "bg-indigo-600 shadow-lg shadow-indigo-200 hover:bg-indigo-700"
        }`}
      >
        {busy ? "Searching jobs…" : "Find Jobs"}
      </button>
    </form>
  );
}
