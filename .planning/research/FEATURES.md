# Feature Landscape: AI Company Research Agent

**Domain:** Startup intelligence / company research pipeline  
**Researched:** 2025-05-06  
**Confidence:** HIGH (core patterns well-established; YC-specific scraping details MEDIUM)

---

## Context

This system follows a **collect → analyze → store → expose** pipeline:
- **Collect:** Scrape YC startup directory
- **Analyze:** OpenAI generates structured insights per company
- **Store:** SQLite persists collected + generated data
- **Expose:** FastAPI serves results via REST

Feature categories below are evaluated against this specific scope. References drawn from
Crunchbase, CB Insights, PitchBook, Dealroom, and similar startup intelligence products.

---

## Table Stakes

Features that developers and internal users expect by default. Missing = tool feels broken or incomplete.

### Data Collection

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Scrape company name, website, description from YC | Core data — nothing works without it | Low | YC directory HTML is stable; use `requests` + `BeautifulSoup` |
| Rate limiting / polite crawl delay | Prevents IP bans; courteous to host | Low | `time.sleep(1-2)` between requests; no `robots.txt` violations |
| Idempotent re-runs (skip already-collected) | Running twice must not duplicate rows | Low | Check by URL or company slug before insert |
| Scrape at least 10–50 companies | Minimum viable dataset for any demo | Low | YC lists hundreds; scraping 50 is trivially achievable |
| Capture raw description before AI analysis | Source of truth; AI can be re-run | Low | Store original description separately from AI output |
| Handle missing / empty descriptions gracefully | Some YC listings lack descriptions | Low | Pass placeholder prompt to AI; don't crash the pipeline |

### AI Analysis Quality

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured JSON output from LLM | Required fields (industry, model, summary, use case) must be machine-readable | Low | Use `response_format={"type": "json_object"}` or Pydantic + `parse()` |
| Prompt documentation with rationale | Explicitly required in PROJECT.md | Low | Comment prompt design decisions inline or in README |
| Handle ambiguous / vague companies | Some YC companies have 1-line descriptions | Low | Prompt should instruct model to make best-effort inference; don't fail |
| Log which companies failed analysis | Visibility into gaps in the dataset | Low | Print/log company name + error reason when AI call fails |
| Consistent output schema | All records must have same fields even if null | Low | Pydantic model for LLM output; validate before DB insert |

### API Design

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `GET /companies` — returns all companies with insights | Core endpoint; primary use case | Low | Returns list of company objects with all fields |
| `GET /companies/{id}` — returns single company | Standard REST resource pattern | Low | 404 with clear message if not found |
| JSON response with correct Content-Type header | Clients expect `application/json` | Low | FastAPI does this automatically |
| HTTP 404 on missing resource | Industry-standard error signaling | Low | `raise HTTPException(status_code=404)` |
| Auto-generated docs at `/docs` (Swagger UI) | FastAPI's killer feature; internal team expects it | Low | Free with FastAPI; no extra work needed |
| Pydantic response models (typed outputs) | Documents API contract; prevents accidental field leakage | Low | Define `CompanyResponse` Pydantic model |

### Data Freshness

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `created_at` timestamp on each record | Developers need to know when data was collected | Low | `DEFAULT CURRENT_TIMESTAMP` in SQLite |
| `analyzed_at` timestamp on AI output | Separate from collection; AI can be re-run independently | Low | Set when OpenAI call completes successfully |
| Re-runnable batch script | One-time collection must be re-runnable to refresh | Low | Script is idempotent: upsert or skip-if-exists |

### Error Handling

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Retry on OpenAI rate limit (429) | Rate limits are routine; silent retry is expected | Low | Catch `RateLimitError`; retry after `Retry-After` header or fixed delay |
| Retry on transient network errors | Timeouts happen; one retry saves a full re-run | Low | Wrap in `try/except` with 1–2 retries |
| Per-company failure isolation | One bad company must not abort the entire batch | Low | `try/except` per company in loop; log and continue |
| Configurable timeout for LLM calls | Prevents infinite hangs | Low | `timeout=30` in OpenAI client call |

---

## Differentiators

Features that elevate the tool beyond minimum viable. Not expected in v1, but provide genuine value if implemented.

### Data Collection

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Scrape additional fields: batch/year, team size, location | Richer filtering and analysis | Medium | YC profile pages contain this; requires additional parsing |
| Detect and skip already-analyzed companies on re-run | Avoids paying for redundant LLM calls | Low | Check `analyzed_at IS NOT NULL` before calling OpenAI |
| Structured logging with counts (scraped / analyzed / failed) | Operations visibility; confidence in run quality | Low | Print summary at end: "50 scraped, 48 analyzed, 2 failed" |

### AI Analysis Quality

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Model fallback: gpt-4o-mini → gpt-4o on failure | Better quality on ambiguous inputs without full cost | Medium | Retry with gpt-4o after gpt-4o-mini JSON parse failure |
| Few-shot examples in prompt | Significantly improves output consistency | Low | 2–3 example inputs/outputs in system prompt |
| Output validation before DB insert | Catches hallucinated or malformed fields early | Low | Pydantic model validates `industry`, `business_model` are non-empty strings |
| `analysis_model` field in DB | Track which model produced each insight | Low | Useful when comparing gpt-4o-mini vs gpt-4o outputs |
| Confidence / completeness flag | Flag records where description was too short for reliable analysis | Medium | Add `low_confidence: bool` field; set when description < 50 chars |

### API Design

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Filter by industry: `GET /companies?industry=fintech` | Most common internal query pattern | Low | SQLite `WHERE industry = ?`; FastAPI query param |
| Filter by business model: `GET /companies?business_model=SaaS` | Second most common filter | Low | Same pattern as industry filter |
| Full-text search: `GET /companies?q=payments` | Lets users find companies by keyword | Medium | SQLite `FTS5` virtual table or `LIKE %q%` for simple version |
| Sort by name or date: `GET /companies?sort=created_at` | Predictable ordering for consumers | Low | `ORDER BY` clause; FastAPI enum query param |
| `GET /companies/stats` — counts by industry/model | Quick dataset overview | Low | SQL `GROUP BY` query; single endpoint |

### Data Freshness

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `--force-reanalyze` CLI flag | Re-run AI on all companies without re-scraping | Low | Skip scraping step; iterate over existing DB records |
| `--limit N` CLI flag | Control batch size for testing or cost management | Low | Slice the company list before the analysis loop |

### Error Handling

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Exponential backoff on retries | More polite to OpenAI; avoids thundering herd | Low | `time.sleep(2**attempt)` with jitter |
| Dead-letter log file for failed companies | Post-run review of what went wrong | Low | Append failed company name + error to `failed.log` |
| JSON parse retry with stricter prompt | First attempt fails JSON → retry with "respond ONLY with JSON" instruction | Low | Common fix for gpt-4o-mini occasionally adding prose |

---

## Anti-Features

Things that look useful but add complexity without value for v1. Explicitly defer or avoid.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Real-time scraping on API request** | Latency unpredictable (5–30s per request); blocks HTTP thread | Run scraping as offline batch job; API reads from DB only |
| **Scheduled / cron-based refresh** | Adds infrastructure (APScheduler, cron, Celery); unnecessary for 10–50 companies | Document `python scrape.py` as the refresh command in README |
| **Authentication on the API** | Internal tool; explicitly out of scope in PROJECT.md | Skip entirely for v1 |
| **Pagination on `/companies`** | <100 records; explicitly out of scope in PROJECT.md | Return all records; add pagination only if record count grows |
| **Streaming LLM responses** | Adds async complexity; structured output requires full response anyway | Use standard synchronous `client.chat.completions.create()` |
| **Embeddings + vector search** | Semantic similarity is valuable but requires a vector store; overkill for batch of 50 | Use SQLite FTS5 or simple `LIKE` for text search |
| **Fine-tuning or custom model** | Weeks of work; unnecessary when prompt engineering achieves required quality | Invest in prompt design and few-shot examples instead |
| **Async LLM calls (asyncio)** | Adds complexity; batch of 50 is fast enough sequentially | Sequential loop with per-company error handling; parallel not needed |
| **Multi-source data collection** (LinkedIn, Crunchbase API) | API keys, rate limits, TOS risk; not scoped | YC directory is sufficient for v1 |
| **Change detection / diffing** | Track what changed between scrape runs; useful but complex | Not needed for static batch; add in v2 if needed |
| **Confidence scoring from LLM** | Prompting models to self-assess confidence is unreliable | Use output validation (non-empty fields) as proxy for quality |
| **GraphQL API** | REST is sufficient; GraphQL adds schema overhead for 2 endpoints | Use FastAPI REST; extend later if needed |
| **Frontend / UI** | Explicitly out of scope in PROJECT.md | Swagger UI at `/docs` serves as the internal interface |
| **Docker / containerization** | Adds setup complexity for an internal script | `pip install -r requirements.txt` + `.env` is sufficient for v1 |

---

## Feature Dependencies

```
Raw scrape data
  └── stored in DB (companies table)
        └── AI analysis called per company
              └── structured output validated (Pydantic)
                    └── stored in DB (analysis fields on same row)
                          └── FastAPI reads from DB
                                ├── GET /companies
                                └── GET /companies/{id}

Rate limiting (scraping)       → prevents scrape failures
Per-company error isolation    → enables partial success
Retry on 429                   → prevents analysis gaps
Idempotent re-run              → enables safe re-execution
```

**Critical path:** scraping → DB storage → AI analysis → DB update → API read  
Each stage must work independently so failures don't cascade.

---

## MVP Feature Set

What to build first, in dependency order:

### Must Have (v1)
1. **Scraper** — collect name, website, description from YC directory (10–50 companies)
2. **DB schema** — SQLite table with all fields including AI output columns
3. **AI analysis loop** — per-company call to OpenAI with structured JSON output
4. **Per-company error isolation** — `try/except` in loop; log + continue on failure
5. **Retry on 429** — simple retry with fixed delay on rate limit errors
6. **`GET /companies`** — return all records with AI insights
7. **`GET /companies/{id}`** — return single record with 404 on missing
8. **Prompt documentation** — comment rationale for all key prompt decisions

### Should Have (v1 extension, low effort)
9. **`analyzed_at` timestamp** — track when each company was AI-analyzed
10. **Structured logging summary** — print scraped/analyzed/failed counts at end of run
11. **Few-shot examples in prompt** — 2–3 examples improve output consistency markedly
12. **Output validation** — Pydantic model validates LLM JSON before DB insert

### Defer (v2+)
- Filtering / search on API
- Model fallback (gpt-4o-mini → gpt-4o)
- Incremental update / re-analyze flag
- Exponential backoff with jitter
- Full-text search

---

## Sources

- **Crunchbase / CB Insights / PitchBook** — industry benchmark for startup intelligence features (training data, HIGH confidence)
- **OpenAI Chat Completions API** — `response_format`, `json_object` mode, error types including `RateLimitError` (HIGH confidence, verified via SDK README)
- **FastAPI docs** — query parameter validation, `HTTPException`, Pydantic response models (HIGH confidence)
- **SQLite FTS5** — full-text search extension available in Python's stdlib `sqlite3` (HIGH confidence)
- **YC Company Directory** — `https://www.ycombinator.com/companies` (MEDIUM confidence for exact HTML structure; needs verification at scraping time)
