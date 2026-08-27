import type { Importance, Roadmap } from "@/lib/api";

const PRIORITY_STYLES: Record<Importance, string> = {
  high: "bg-rose-100 text-rose-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

export default function RoadmapView({ roadmap }: { roadmap: Roadmap }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900">
          30-Day Roadmap
        </h2>
        <span className="text-xs text-slate-500">
          ~{roadmap.daily_hours_target} hrs / day · {roadmap.total_days} days
        </span>
      </header>

      <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
        {roadmap.weeks.map((week, weekIndex) => (
          <div key={weekIndex} className="rounded-xl border border-slate-100 p-4">
            <h3 className="mb-3 text-sm font-bold text-indigo-700">
              Week {weekIndex + 1}
            </h3>
            <ol className="space-y-2.5">
              {week.map((task) => (
                <li key={task.day} className="flex gap-3">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-xs font-bold text-indigo-700">
                    {task.day}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-snug text-slate-800">
                      {task.topic}
                      <span
                        className={`ml-2 inline-block rounded-full px-1.5 py-px align-middle text-[10px] font-bold uppercase ${PRIORITY_STYLES[task.priority]}`}
                      >
                        {task.priority}
                      </span>
                    </p>
                    <p className="text-xs leading-relaxed text-slate-500">{task.goal}</p>
                    <p className="mt-0.5 text-[11px] font-medium text-slate-400">
                      ~{task.estimated_hours} hrs
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}
