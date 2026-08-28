import { getAuthHeaders } from "./auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types mirroring the backend schemas
// ---------------------------------------------------------------------------

export interface RoleEntry {
  title: string;
  company?: string | null;
  duration?: string | null;
}

export interface EducationEntry {
  degree: string;
  institution?: string | null;
  year?: string | null;
}

export interface Certification {
  name: string;
  issuer?: string | null;
  year?: string | null;
}

export interface Project {
  name: string;
  description?: string | null;
  technologies: string[];
}

export interface CandidateProfile {
  name: string | null;
  total_experience_years: number | null;
  current_role: string | null;
  previous_roles: RoleEntry[];
  education: EducationEntry[];
  technical_skills: string[];
  soft_skills: string[];
  programming_languages: string[];
  frameworks: string[];
  cloud_platforms: string[];
  databases: string[];
  ai_ml_skills: string[];
  projects: Project[];
  certifications: Certification[];
  domain_experience: string[];
}

export interface JobProfile {
  company: string | null;
  role: string | null;
  required_experience_years: number | null;
  required_skills: string[];
  preferred_skills: string[];
  programming_languages: string[];
  frameworks: string[];
  cloud_technologies: string[];
  ai_ml_technologies: string[];
  databases: string[];
  system_design_requirements: string[];
  soft_skills: string[];
  responsibilities: string[];
  education_requirements: string[];
  certifications: string[];
}

export type SkillStatus = "matched" | "partial" | "missing";
export type Importance = "high" | "medium" | "low";

export interface SkillGapItem {
  skill: string;
  status: SkillStatus;
  importance: Importance;
  reason?: string | null;
  recommended_action?: string | null;
}

export interface SkillGap {
  matched: string[];
  partial: string[];
  missing: string[];
  gaps: SkillGapItem[];
}

export interface ScoreBreakdown {
  required_skills: number;
  preferred_skills: number;
  experience: number;
  project_relevance: number;
  education: number;
}

export interface MatchScore {
  overall_score: number;
  breakdown: ScoreBreakdown;
  weights_used: Record<string, number>;
}

export interface RoadmapTask {
  day: number;
  topic: string;
  goal: string;
  estimated_hours: number;
  priority: Importance;
}

export interface Roadmap {
  total_days: number;
  daily_hours_target: number;
  weeks: RoadmapTask[][];
}

export interface AnalysisResult {
  session_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  error: string | null;
  candidate_profile: CandidateProfile | null;
  job_profile: JobProfile | null;
  skill_gap: SkillGap | null;
  match_score: MatchScore | null;
  roadmap: Roadmap | null;
  errors: string[];
}

export interface UploadResponse {
  session_id: string;
  resume_document_id: string;
  job_description_document_id: string;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = { ...(init?.headers as Record<string, string> | undefined), ...getAuthHeaders() } as Record<string, string>;
  return fetch(url, { ...init, headers });
}

async function handleErrors(response: Response): Promise<Response> {
  if (response.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return response;
}

export async function uploadDocuments(
  resume: File,
  jobDescription: File
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("resume", resume);
  form.append("job_description", jobDescription);
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/documents/upload`, {
      method: "POST",
      body: form,
    })
  );
  return (await response.json()) as UploadResponse;
}

export async function startAnalysis(sessionId: string): Promise<{ status: string; message?: string }> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/analysis/${sessionId}/start`, {
      method: "POST",
    })
  );
  return (await response.json()) as { status: string; message?: string };
}

export async function getAnalysis(sessionId: string): Promise<AnalysisResult> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/analysis/${sessionId}`)
  );
  return (await response.json()) as AnalysisResult;
}

// ---------------------------------------------------------------------------
// Phase 2: job discovery types
// ---------------------------------------------------------------------------

export type WorkMode = "remote" | "hybrid" | "onsite" | "unknown";

export interface JobSearchPreferences {
  keywords: string[];
  locations: string[];
  remote?: boolean | null;
  work_modes?: WorkMode[];
  experience_min?: number | null;
  experience_max?: number | null;
  salary_min?: number | null;
  employment_types?: string[];
  min_match_percent?: number | null;
}

export interface SourceRecord {
  source: string;
  source_job_id?: string | null;
  title?: string | null;
  url?: string | null;
}

export interface Job {
  id: string | null;
  source: string;
  source_type: "REAL" | "MOCK";
  status: "ACTIVE" | "EXPIRED" | "REMOVED" | "UNKNOWN";
  url_status: "VALID" | "INVALID" | "UNKNOWN";
  last_seen_at?: string | null;
  last_verified_at?: string | null;
  experience_level?: string | null;
  source_job_id?: string | null;
  title: string;
  company: string;
  description: string;
  location: string | null;
  work_mode: WorkMode;
  employment_type: string | null;
  experience_min: number | null;
  experience_max: number | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  required_skills: string[];
  preferred_skills: string[];
  posted_at: string | null;
  application_url: string | null;
  created_at: string | null;
}

export interface JobMatchBreakdown {
  required_skill_match: number | null;
  preferred_skill_match: number | null;
  role_match: number | null;
  experience_match: number | null;
  location_match: number | null;
  salary_match: number | null;
}

export interface JobMatch {
  job_id: string;
  overall_match: number;
  breakdown: JobMatchBreakdown;
  weights_used: Record<string, number>;
  matched_skills: string[];
  partial_skills: string[];
  missing_skills: string[];
  risk_factors: string[];
  filtered_out: boolean;
  filter_reasons: string[];
}

export interface JobExplanation {
  strengths: string[];
  gaps: string[];
}

export interface Recommendation {
  rank: number;
  job: Job;
  match: JobMatch;
  explanation: JobExplanation;
  freshness_bonus?: number;
  adjusted_score?: number;
}

export interface RankedRecommendations {
  search_id: string;
  status: string;
  total_jobs: number;
  recommendations: Recommendation[];
}

export interface JobSearchResponse {
  search_id: string;
  status: string;
  message?: string | null;
  sources?: ProviderStatusInfo[];
  metadata?: SearchMetadata;
  warnings?: string[];
}

export interface JobDetailResponse {
  job: Job;
  sources: SourceRecord[];
  match?: JobMatch | null;
  explanation?: JobExplanation | null;
}

export function formatSalary(job: Job): string | null {
  if (job.salary_min == null && job.salary_max == null) return null;
  const fmt = (v: number) => `\u20B9${Number.isInteger(v) ? v : v.toFixed(1)}L`;
  if (job.salary_min != null && job.salary_max != null) {
    return job.salary_min === job.salary_max
      ? fmt(job.salary_min)
      : `${fmt(job.salary_min)} \u2013 ${fmt(job.salary_max)}`;
  }
  return fmt((job.salary_min ?? job.salary_max) as number);
}

// ---------------------------------------------------------------------------
// Phase 2 API calls
// ---------------------------------------------------------------------------

export async function searchJobs(
  prefs: JobSearchPreferences & { session_id: string }
): Promise<JobSearchResponse> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/jobs/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    })
  );
  return (await response.json()) as JobSearchResponse;
}

export async function getRecommendations(
  searchId: string,
  minMatch?: number
): Promise<RankedRecommendations> {
  const params = minMatch != null ? `?min_match=${minMatch}` : "";
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/jobs/recommendations/${searchId}${params}`)
  );
  return (await response.json()) as RankedRecommendations;
}

export async function getJob(jobId: string): Promise<JobDetailResponse> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/jobs/${jobId}`)
  );
  return (await response.json()) as JobDetailResponse;
}

export async function analyzeJob(
  jobId: string,
  resumeSessionId: string
): Promise<{ session_id: string; status: string; message?: string | null }> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/jobs/${jobId}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_session_id: resumeSessionId }),
    })
  );
  return (await response.json()) as {
    session_id: string;
    status: string;
    message?: string | null;
  };
}


// ---------------------------------------------------------------------------
// Phase 3: application copilot types & calls
// ---------------------------------------------------------------------------

export type ApplicationStatus =
  | "SAVED" | "PREPARING" | "READY_TO_APPLY" | "APPLIED" | "OA_RECEIVED"
  | "INTERVIEW" | "OFFER" | "REJECTED" | "WITHDRAWN";

export interface ResumeChange {
  section: string;
  original: string;
  updated: string;
  reason?: string | null;
  type: string;
  supported: boolean;
  warning?: string | null;
}

export interface TailoredResume {
  content_markdown: string;
  changes: ResumeChange[];
  summary: string;
  recommendations: string[];
  truthfulness_checked: boolean;
  unsupported_claims_count: number;
}

export interface CompanyInfo {
  name: string;
  industry: string | null;
  description: string | null;
  products_services: string[];
  company_size: string | null;
  headquarters: string | null;
  technology_areas: string[];
  recent_news: string[];
  website: string | null;
  source: string;
  is_mock: boolean;
}

export interface CompanyInsights {
  what_they_do: string;
  why_role_matters: string;
  technology_environment: string[];
  interview_prep_areas: string[];
}

export interface CoverLetterDraft {
  content_text: string;
  word_count: number;
  generated_with: string;
  approved: boolean;
}

export interface ApplicationQuestionItem {
  question: string;
  suggested_answer: string;
  category: string;
  order_index: number;
}

export interface ChecklistItem {
  key: string;
  label: string;
  done: boolean;
  auto: boolean;
}

export interface EventOut {
  id?: string | null;
  event: string;
  notes?: string | null;
  created_at?: string | null;
}

export interface JobSummary {
  id: string | null;
  title: string;
  company: string;
  location: string | null;
  work_mode: string | null;
  application_url: string | null;
}

export interface ApplicationOut {
  id: string;
  job: JobSummary;
  status: ApplicationStatus;
  overall_match: number | null;
  applied_at: string | null;
  notes: string;
  next_action: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApplicationDetail extends ApplicationOut {
  timeline: EventOut[];
  checklist: ChecklistItem[];
  tailored_resume: TailoredResume | null;
  cover_letter: CoverLetterDraft | null;
  company_info: CompanyInfo | null;
  company_insights: CompanyInsights | null;
  questions: ApplicationQuestionItem[];
  warnings?: string[];
  research_available?: boolean;
  message?: string | null;
}

export interface ApplicationAnalyticsPayload {
  analytics: {
    total_applications: number;
    saved: number; preparing: number; ready_to_apply: number;
    applied: number; oa_received: number; interviews: number;
    offers: number; rejected: number; withdrawn: number;
    interview_rate: number; offer_rate: number; rejection_rate: number;
    average_match_score: number | null;
  };
  insights: { insights: string[]; sufficient_data: boolean };
}

export async function createApplication(
  jobId: string,
  resumeSessionId?: string
): Promise<{ application_id: string }> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: jobId,
        resume_session_id: resumeSessionId ?? undefined,
      }),
    })
  );
  return (await response.json()) as { application_id: string };
}

export async function listApplications(filters?: {
  status?: string; company?: string; role?: string;
}): Promise<{ total: number; applications: ApplicationOut[] }> {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.company) params.set("company", filters.company);
  if (filters?.role) params.set("role", filters.role);
  const qs = params.toString();
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications${qs ? `?${qs}` : ""}`)
  );
  return (await response.json()) as { total: number; applications: ApplicationOut[] };
}

export async function getApplication(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}`)
  );
  return (await response.json()) as ApplicationDetail;
}

export async function updateApplicationStatus(
  applicationId: string,
  newStatus: ApplicationStatus,
  notes?: string
): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus, notes }),
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function updateApplicationNotes(
  applicationId: string,
  notes: string
): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function prepareApplication(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/prepare`, {
      method: "POST",
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function tailorResume(applicationId: string, regenerate = false): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/resume/tailor`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ regenerate }),
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function approveResume(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/resume/approve`, {
      method: "POST",
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function generateCoverLetter(applicationId: string, regenerate = false): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/cover-letter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ regenerate }),
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function editCoverLetter(applicationId: string, contentText: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/cover-letter`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_text: contentText }),
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function approveCoverLetter(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/cover-letter/approve`, {
      method: "POST",
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function researchCompany(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/company/research`, {
      method: "POST",
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function generateQuestions(applicationId: string): Promise<ApplicationDetail> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/${applicationId}/questions`, {
      method: "POST",
    })
  );
  return (await response.json()) as ApplicationDetail;
}

export async function toggleChecklistItem(
  applicationId: string, key: string, done: boolean
): Promise<{ checklist: ChecklistItem[] }> {
  const response = await handleErrors(
    await authFetch(
      `${API_BASE_URL}/api/applications/${applicationId}/checklist/${key}?done=${done}`,
      { method: "PATCH" }
    )
  );
  return (await response.json()) as { checklist: ChecklistItem[] };
}

export function exportUrl(applicationId: string, kind: "resume" | "cover-letter", fmt: string): string {
  return `${API_BASE_URL}/api/applications/${applicationId}/${kind}/export?fmt=${fmt}`;
}

export async function getAnalytics(): Promise<ApplicationAnalyticsPayload> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/applications/analytics`)
  );
  return (await response.json()) as ApplicationAnalyticsPayload;
}


export async function signup(email: string, password: string): Promise<{ id: string; email: string }> {
  const response = await handleErrors(
    await fetch(`${API_BASE_URL}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
  );
  return (await response.json()) as { id: string; email: string };
}

export async function login(email: string, password: string): Promise<{ access_token: string; token_type: string }> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  const response = await handleErrors(
    await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    })
  );
  return (await response.json()) as { access_token: string; token_type: string };
}

export async function getMe(): Promise<{ id: string; email: string }> {
  const response = await handleErrors(await authFetch(`${API_BASE_URL}/api/auth/me`));
  return (await response.json()) as { id: string; email: string };
}

// ---------------------------------------------------------------------------
// Phase 4: provider aggregation types & calls
// ---------------------------------------------------------------------------

export interface ProviderStatusInfo {
  name: string;
  source_type: "REAL" | "MOCK";
  status: "success" | "empty" | "error" | "skipped";
  count: number;
  enabled: boolean;
  message?: string | null;
}

export interface SearchMetadata {
  live_results: boolean;
  cached_results: boolean;
  discovered?: number;
  unique?: number;
  duplicates_removed?: number;
  duration_ms?: number | null;
}

export interface Pagination {
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
}

export interface ProviderHealth {
  name: string;
  source: string;
  source_type: "REAL" | "MOCK";
  enabled: boolean;
  healthy: boolean | null;
  status: "healthy" | "unknown" | "not_configured";
}

export async function getProviderHealth(): Promise<{ providers: ProviderHealth[] }> {
  const response = await handleErrors(
    await authFetch(`${API_BASE_URL}/api/jobs/providers`)
  );
  return (await response.json()) as { providers: ProviderHealth[] };
}

export function timeAgo(postedAt: string | null): string {
  if (!postedAt) return "Date unavailable";
  const then = new Date(postedAt).getTime();
  if (Number.isNaN(then)) return "Date unavailable";
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

