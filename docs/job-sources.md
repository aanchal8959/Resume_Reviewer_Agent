# Job Sources — Provider Guide

Phase 4 makes job discovery **source-driven**: the database is a *cache +
history*, not the primary source. Every provider plugs into the same interface,
so adding one never touches matching, ranking, applications, or the frontend.

```
User search
    ↓
JobSourceManager ──► ProviderAdapter × N (timeout · retry · error isolation)
    ↓                     │
    │                RawJob[] per provider
    │                     ↓
    ├──── Cache hit? ── Normalization (JobNormalizer)
    │                     ↓
    │                Deduplication (fingerprint + fuzzy)
    │                     ↓
    │                URL verification (TTL-capped, rate-respecting)
    │                     ↓
    └───────────────► jobs table (cache + history, never deleted)
                          ↓
                 Existing Matching → Ranking → UI
```

## 1. Supported providers

| Provider | Type | Auth | Free tier | Env flags | Notes |
|---|---|---|---|---|---|
| `MockJobSource` | MOCK | none | n/a | `ENABLE_MOCK_JOBS=true` | 50 deterministic demo jobs incl. duplicates; always labelled **Demo Data** in the UI |
| Remotive | REAL | none | yes (public API) | `ENABLE_REMOTIVE=true` | Remote-only jobs; documented developer API |
| Arbeitnow | REAL | none | yes (public API) | `ENABLE_ARBEITNOW=true` | EU-heavy job board feed; JSON, paginated |
| Jobicy | REAL | none | yes (public API) | `ENABLE_JOBICY=true` | Remote jobs; JSON; salary sometimes present |
| Adzuna | REAL | app_id + app_key (free at developer.adzuna.com) | yes w/ daily quota | `ADZUNA_APP_ID`, `ADZUNA_API_KEY` | Official API; broad coverage incl. India (`ADZUNA_COUNTRY`, default `in`) |
| Greenhouse boards | REAL | none (public ATS feeds) | yes | `GREENHOUSE_COMPANIES=token1:Name,token2` | Company-career pattern: each token is a company's public board |

## 2. Selecting a strategy

```env
JOB_SOURCE_MODE=mock     # offline demo dataset only (default; no network)
JOB_SOURCE_MODE=live     # real providers only (falls back to mock if none configured)
JOB_SOURCE_MODE=hybrid   # real providers + clearly-labelled demo data
```

Legacy Phase 2 variable `JOB_SOURCE=mock|remotive` still works when
`JOB_SOURCE_MODE` is left at its default.

## 3. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `JOB_SOURCE_MODE` | `mock` | mock \| live \| hybrid |
| `ENABLE_REMOTIVE` / `ENABLE_ARBEITNOW` / `ENABLE_JOBICY` | `false` | enable public-API providers |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | — | Adzuna credentials (provider stays off until both set) |
| `GREENHOUSE_COMPANIES` | — | e.g. `stripe:Stripe Inc,datadog` |
| `PROVIDER_TIMEOUT_SECONDS` | `10` | Per-request provider timeout |
| `MAX_PROVIDER_RETRIES` | `2` | Extra attempts with exponential backoff (429/5xx/network) |
| `JOB_CACHE_TTL_MINUTES` | `60` | Fresh-cache window that skips external calls |
| `URL_VERIFY_TTL_HOURS` | `24` | Minimum interval between URL checks |
| `URL_VERIFY_MAX_PER_SEARCH` | `10` | Hard cap of verifications per cycle |
| `JOB_STALE_DAYS` | `30` | Age after which unseen jobs become `UNKNOWN` |

## 4. Data fields & normalization

Providers return heterogeneous payloads; each adapter maps them into `RawJob`,
then `JobNormalizer` produces the canonical `Job`. Example mapping:

- Arbeitnow: `company_name → company`, `location → location`, unix `created_at → posted_at`
- Jobicy: `jobTitle → title`, `companyName → company`, `jobGeo → location`, `jobLevel → experience_level`
- Adzuna: `company.display_name → company`, `location.display_name → location`
- Greenhouse: board token → company display name, `absolute_url → application_url`

The rest of the system only ever sees normalized `Job` objects.

## 5. Caching

* First search for a query: providers queried, results stored.
* Repeat within `JOB_CACHE_TTL_MINUTES`: served from the local cache
  (`metadata.cached_results = true`) — zero external calls.
* Stale cache: external refresh; re-encountered jobs get `last_seen_at`
  refreshed and are reactivated from `EXPIRED/UNKNOWN` to `ACTIVE`.
* Force a refresh from the API with `"refresh": true` on the POST search body.

## 6. Deduplication

Deterministic, no LLM:
1. `(source, source_job_id)` exact pair;
2. normalized application URL equality;
3. same company + exact/synonym-expanded title subset/ratio ≥ 0.80;
4. long-description similarity ≥ 0.85 (only for descriptions ≥ 120 chars).

Canonical record keeps the richest field values plus full source provenance.

## 7. URL validation & freshness

* `url_status`: VALID / INVALID / UNKNOWN; `last_verified_at` timestamp stored.
* Only URLs older than `URL_VERIFY_TTL_HOURS` are checked, max
  `URL_VERIFY_MAX_PER_SEARCH` per cycle, HEAD-first (405 → skip, no penalty).
* Network errors leave status UNKNOWN — unreachable ≠ expired.
* Jobs unseen for `JOB_STALE_DAYS` become `UNKNOWN`; nothing is ever deleted,
  so Phase 3 applications and analytics keep their history.

## 8. Legal / ToS considerations

* Only official public APIs and documented public ATS endpoints are integrated.
* LinkedIn, Naukri and similar sites have **no authorized public job-search API
  for this use** and prohibit automated access in their ToS — they are therefore
  intentionally **not** integrated. No login bypass, CAPTCHA evasion, HTML
  scraping of protected pages, or anti-bot countermeasures exist anywhere in
  this codebase, by design.
* Rate limits are respected via timeouts, capped retries, caching and the URL
  verification budget above.

## 9. Adding a new provider

1. Create `my_source.py` with a class exposing
   `search_jobs(preferences, strategy_queries) -> list[RawJob]`
   (map the provider payload inside `_to_raw`).
2. Register it in `JobSourceManager._build_adapters` behind its own env flag.
3. Add adapter unit tests using saved payload samples (no live calls).
Nothing else in the application changes.
