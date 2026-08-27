import type { MatchScore } from "@/lib/api";

const BREAKDOWN_LABELS: { key: keyof MatchScore["breakdown"]; label: string }[] = [
  { key: "required_skills", label: "Required Skills" },
  { key: "preferred_skills", label: "Preferred Skills" },
  { key: "experience", label: "Experience" },
  { key: "project_relevance", label: "Projects" },
  { key: "education", label: "Education / Certifications" },
];

function scoreColor(score: number): string {
  if (score >= 75) return "bg-emerald-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-rose-500";
}

export default function MatchScoreView({ score }: { score: MatchScore }) {
  const overall = Math.round(score.overall_score);
  const circumference = 2 * Math.PI * 54;
  const dashOffset = circumference * (1 - Math.min(overall, 100) / 100);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-lg font-bold text-slate-900">Match Score</h2>
      <div className="flex flex-col items-center gap-8 sm:flex-row sm:items-center">
        <div className="relative h-36 w-36 shrink-0">
          <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
            <circle cx="64" cy="64" r="54" fill="none" stroke="#e2e8f0" strokeWidth="12" />
            <circle
              cx="64"
              cy="64"
              r="54"
              fill="none"
              stroke={overall >= 75 ? "#10b981" : overall >= 50 ? "#f59e0b" : "#f43f5e"}
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-extrabold text-slate-900">{overall}%</span>
            <span className="text-xs font-medium text-slate-500">Overall Match</span>
          </div>
        </div>

        <ul className="w-full space-y-2.5">
          {BREAKDOWN_LABELS.map(({ key, label }) => {
            const value = Math.round(score.breakdown[key]);
            return (
              <li key={key}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700">{label}</span>
                  <span className="font-semibold text-slate-900">{value}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${scoreColor(value)}`}
                    style={{ width: `${value}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
