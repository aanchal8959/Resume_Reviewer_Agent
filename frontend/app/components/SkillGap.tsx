import type { Importance, SkillGap } from "@/lib/api";

const STATUS_COLUMNS: {
  key: "matched" | "partial" | "missing";
  title: string;
  chip: string;
}[] = [
  { key: "matched", title: "Matched", chip: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  { key: "partial", title: "Partial", chip: "bg-amber-50 text-amber-700 border-amber-200" },
  { key: "missing", title: "Missing", chip: "bg-rose-50 text-rose-700 border-rose-200" },
];

const IMPORTANCE_STYLES: Record<Importance, string> = {
  high: "bg-rose-100 text-rose-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

export default function SkillGapView({ skillGap }: { skillGap: SkillGap }) {
  const priorityGaps = [...skillGap.gaps]
    .filter((gap) => gap.status !== "matched")
    .sort((a, b) => {
      const order = { high: 0, medium: 1, low: 2 } as const;
      return order[a.importance] - order[b.importance];
    });

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-bold text-slate-900">Skill Gap</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {STATUS_COLUMNS.map(({ key, title, chip }) => (
            <div key={key} className="rounded-xl border border-slate-100 p-4">
              <h3 className="mb-3 text-sm font-bold text-slate-800">{title}</h3>
              <div className="flex flex-wrap gap-1.5">
                {skillGap[key].length === 0 && (
                  <span className="text-xs text-slate-400">None</span>
                )}
                {skillGap[key].map((skill) => (
                  <span
                    key={skill}
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${chip}`}
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-bold text-slate-900">Priority Gaps</h2>
        {priorityGaps.length === 0 ? (
          <p className="text-sm text-slate-500">No significant gaps found. 🎯</p>
        ) : (
          <ol className="space-y-3">
            {priorityGaps.map((gap, index) => (
              <li key={gap.skill} className="flex items-start gap-3 rounded-xl bg-slate-50 p-3.5">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{gap.skill}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${IMPORTANCE_STYLES[gap.importance]}`}
                    >
                      {gap.importance}
                    </span>
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                      {gap.status}
                    </span>
                  </div>
                  {gap.reason && (
                    <p className="mt-1 text-xs leading-relaxed text-slate-500">{gap.reason}</p>
                  )}
                  {gap.recommended_action && (
                    <p className="mt-1 text-xs font-medium leading-relaxed text-indigo-600">
                      → {gap.recommended_action}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
