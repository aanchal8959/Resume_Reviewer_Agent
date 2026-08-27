import type { CandidateProfile } from "@/lib/api";

function SkillChips({ title, skills }: { title: string; skills: string[] }) {
  if (!skills.length) return null;
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h4>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((skill) => (
          <span
            key={skill}
            className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700"
          >
            {skill}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function CandidateProfileView({
  profile,
}: {
  profile: CandidateProfile;
}) {
  const experience =
    profile.total_experience_years != null
      ? `${profile.total_experience_years} yrs`
      : "unknown";

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold text-slate-900">Candidate Profile</h2>
        {profile.name && (
          <span className="text-sm text-slate-500">{profile.name}</span>
        )}
      </header>

      <dl className="mb-5 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-slate-50 p-3">
          <dt className="text-xs font-semibold uppercase text-slate-500">
            Experience
          </dt>
          <dd className="mt-0.5 font-semibold text-slate-800">{experience}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <dt className="text-xs font-semibold uppercase text-slate-500">
            Current Role
          </dt>
          <dd className="mt-0.5 font-semibold text-slate-800">
            {profile.current_role ?? "unknown"}
          </dd>
        </div>
      </dl>

      <div className="space-y-4">
        <SkillChips title="Programming Languages" skills={profile.programming_languages} />
        <SkillChips title="Frameworks" skills={profile.frameworks} />
        <SkillChips title="AI / ML" skills={profile.ai_ml_skills} />
        <SkillChips title="Cloud Platforms" skills={profile.cloud_platforms} />
        <SkillChips title="Databases" skills={profile.databases} />
        <SkillChips title="Other Technical Skills" skills={profile.technical_skills} />
        <SkillChips title="Soft Skills" skills={profile.soft_skills} />

        {profile.projects.length > 0 && (
          <div>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Projects
            </h4>
            <ul className="space-y-2">
              {profile.projects.map((project) => (
                <li key={project.name} className="rounded-lg border border-slate-100 p-3">
                  <p className="text-sm font-semibold text-slate-800">{project.name}</p>
                  {project.description && (
                    <p className="mt-0.5 text-xs text-slate-500">{project.description}</p>
                  )}
                  {project.technologies.length > 0 && (
                    <p className="mt-1 text-xs text-indigo-600">
                      {project.technologies.join(" · ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {profile.education.length > 0 && (
          <div>
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Education & Certifications
            </h4>
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {profile.education.map((entry) => (
                <li key={entry.degree}>
                  {entry.degree}
                  {entry.institution ? ` — ${entry.institution}` : ""}
                  {entry.year ? ` (${entry.year})` : ""}
                </li>
              ))}
              {profile.certifications.map((cert) => (
                <li key={cert.name}>{cert.name}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
