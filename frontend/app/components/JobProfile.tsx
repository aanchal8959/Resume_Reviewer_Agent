import type { JobProfile } from "@/lib/api";

function ListSection({
  title,
  items,
  badgeClass = "bg-slate-100 text-slate-700",
}: {
  title: string;
  items: string[];
  badgeClass?: string;
}) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h4>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badgeClass}`}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function JobProfileView({ profile }: { profile: JobProfile }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold text-slate-900">Target Job</h2>
        {profile.company && (
          <span className="text-sm text-slate-500">{profile.company}</span>
        )}
      </header>

      <dl className="mb-5 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-slate-50 p-3">
          <dt className="text-xs font-semibold uppercase text-slate-500">Role</dt>
          <dd className="mt-0.5 font-semibold text-slate-800">
            {profile.role ?? "unknown"}
          </dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <dt className="text-xs font-semibold uppercase text-slate-500">
            Required Experience
          </dt>
          <dd className="mt-0.5 font-semibold text-slate-800">
            {profile.required_experience_years != null
              ? `${profile.required_experience_years}+ yrs`
              : "unknown"}
          </dd>
        </div>
      </dl>

      <div className="space-y-4">
        <ListSection
          title="Required Skills"
          items={profile.required_skills}
          badgeClass="bg-emerald-50 text-emerald-700"
        />
        <ListSection
          title="Preferred Skills"
          items={profile.preferred_skills}
          badgeClass="bg-amber-50 text-amber-700"
        />
        <ListSection title="AI / ML" items={profile.ai_ml_technologies} />
        <ListSection title="Cloud & Infrastructure" items={profile.cloud_technologies} />
        <ListSection title="Frameworks" items={profile.frameworks} />
        <ListSection title="System Design" items={profile.system_design_requirements} />

        {profile.responsibilities.length > 0 && (
          <div>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Responsibilities
            </h4>
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {profile.responsibilities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {(profile.education_requirements.length > 0 ||
          profile.certifications.length > 0) && (
          <div>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Education / Certifications
            </h4>
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {profile.education_requirements.map((item) => (
                <li key={item}>{item}</li>
              ))}
              {profile.certifications.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
