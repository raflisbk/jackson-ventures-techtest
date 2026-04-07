# Feature Landscape: AI Company Research Agent — v1.1

**Domain:** Startup intelligence / company research pipeline — additive milestone
**Researched:** 2026-04-07 (v1.1 milestone)
**Confidence:** HIGH (MCP SDK verified via PyPI + official README; SQLite LIKE + FTS5 verified via live Python test; pr-agent verified via PyPI + official docs; Jinja2 confirmed installed in venv)

> **Scope note:** This document covers ONLY the five new v1.1 features. The four v1.0 features (YC scraper, OpenAI analysis, SQLite storage, FastAPI GET endpoints) are already built and are NOT re-researched here.

---

## v1.1 Context

Five additive features extend the core v1.0 pipeline. Each is independently deliverable — they share the same DB and FastAPI app but don't require each other to function.

| # | Feature | What it Unlocks |
|---|---------|----------------|
| 1 | **MCP Server** | AI agents (Claude, GPT, custom) can query companies as tool calls |
| 2 | **Filtering / Search** | `?industry=` and `?q=` on `GET /companies` |
| 3 | **AI Caching** | Skip duplicate OpenAI calls when description has not changed |
| 4 | **Simple Frontend** | Browser-based company card grid with industry filter |
| 5 | **CI/CD Pipeline** | GitHub Actions tests + agentic PR code review |

---

## Table Stakes

Features that MUST be implemented for each v1.1 feature to work. Missing = the feature does not exist or is unreliable.

---

### Feature 1: MCP Server

**What it is:** A Model Context Protocol server that exposes company data as callable tools for AI agents. AI agents (Claude, GPT-4o with tool use, custom agents) call these tools instead of making raw HTTP requests.

**Library:** `mcp==1.27.0` (`pip install "mcp[cli]"`). Uses `FastMCP` from `mcp.server.fastmcp`. Python >= 3.10 required (already satisfied). This is the official Anthropic-maintained Python SDK — HIGH confidence.

| Table Stakes Feature | Why Required | Complexity | Implementation Notes |
|---------------------|-------------|------------|---------------------|
| `search_companies(industry, q)` tool | Primary lookup — agents need to find companies by industry or keyword | Low | Returns `list[CompanyResult]` Pydantic model; FastMCP auto-generates JSON schema |
| `get_company(id)` tool | Agents need to retrieve a single company's full details by ID | Low | Returns `CompanyResult`; raise `ValueError` on 404 (FastMCP maps to tool error) |
| `list_industries()` tool | Agents need to know valid industry values before filtering | Low | Returns `list[str]`; SQL `SELECT DISTINCT industry` |
| Structured JSON output (Pydantic return types) | Agents expect machine-readable structured data, not prose | Low | FastMCP automatically generates output schema from Pydantic return annotations |
| Mounted onto existing FastAPI app at `/mcp` | Single process, single port — no separate server to run | Low | `app.mount("/mcp", mcp.streamable_http_app())` via Starlette ASGI mounting |
| Stateless HTTP transport | Required for production use — no session state to manage | Low | `FastMCP("...", stateless_http=True, json_response=True)` |
| Tool docstrings describe inputs and outputs | AI agents read tool descriptions to understand what to call | Low | Python docstrings on each `@mcp.tool()` function |

**Specific tool signatures (recommended):**
```python
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

class CompanyResult(BaseModel):
    id: int
    company_name: str
    industry: str | None
    business_model: str | None
    summary: str | None
    use_case: str | None
    website: str | None

mcp = FastMCP("YC Company Research", stateless_http=True, json_response=True)

@mcp.tool()
def search_companies(industry: str | None = None, q: str | None = None) -> list[CompanyResult]:
    """Search YC companies by industry and/or keyword. industry is exact-match
    (case-insensitive). q searches company name and description."""
    ...

@mcp.tool()
def get_company(id: int) -> CompanyResult:
    """Get full details for a single company by its numeric ID."""
    ...

@mcp.tool()
def list_industries() -> list[str]:
    """Return all distinct industry values present in the database."""
    ...
```

**Q: Should tool results be plain text or structured JSON?**
Structured JSON (Pydantic return types). FastMCP v1.27.0 supports structured output natively — returning a Pydantic model generates a JSON schema and validates the output automatically. Plain text is a fallback for LLM-readable prose; structured JSON is what tool-calling agents consume programmatically.

---

### Feature 2: Filtering / Search

**What it is:** Query parameters on `GET /companies` that let clients filter by industry and search by keyword.

| Table Stakes Feature | Why Required | Complexity | Implementation Notes |
|---------------------|-------------|------------|---------------------|
| `?industry=` filter (case-insensitive) | Most common query — users think "show me fintech companies" | Low | `WHERE LOWER(industry) = LOWER(:industry)` — verified: SQLite LIKE is ASCII case-insensitive, but LOWER() is safer for non-ASCII |
| `?q=` search across name + description | Users search by keyword, not just taxonomy | Low | `WHERE company_name LIKE '%:q%' OR description LIKE '%:q%'` |
| Both parameters optional and composable | `?industry=fintech&q=payments` must work | Low | Check `if industry: query = query.where(...)` separately |
| 200 with empty list when no results match | No 404 for "no results" — empty array is correct REST | Low | FastAPI returns `[]` naturally; no special handling needed |

**Specific answers to design questions:**

- **`?industry=` exact-match or case-insensitive?** Case-insensitive exact match via `LOWER()`. Confirmed: SQLite LIKE (`LIKE 'fintech'`) is case-insensitive for ASCII and matches 'FinTech', 'fintech', 'FINTECH' in live test. Use `LOWER(industry) = LOWER(:industry)` for safety.
- **`?q=` name only or name+description?** Name + description. Searching only name would miss "an AI company in healthcare" matching "health". Both fields searched with `LIKE '%q%'` is correct at this scale.
- **Pagination needed at 50 records?** No. At 50 records, returning all matches is sub-millisecond. Adding pagination UI/API complexity is not justified. The original v1.0 design explicitly deferred pagination. Revisit at 500+ records.
- **FTS5 or LIKE?** LIKE `'%q%'` for v1.1. FTS5 is confirmed available in Python's stdlib sqlite3 but requires a separate virtual table, migration, and sync logic. LIKE is simpler, correct, and fast at 50 records. Upgrade to FTS5 in v1.2 if search quality matters.

---

### Feature 3: AI Caching

**What it is:** Before calling OpenAI for a company, hash its description. If the hash matches what's already stored (and AI fields are populated), skip the call.

| Table Stakes Feature | Why Required | Complexity | Implementation Notes |
|---------------------|-------------|------------|---------------------|
| `description_hash` column on Company table | Store the hash with the record for later comparison | Low | `description_hash: str | None = None` field on SQLModel Company; SHA-256 hex string (64 chars) |
| Hash computed with `hashlib.sha256` | Built-in, no dependencies, deterministic | Low | `hashlib.sha256(description.encode()).hexdigest()` |
| Skip OpenAI call when hash matches AND AI fields are non-null | The combined condition prevents re-analyzing when only partial data exists | Low | `if company.description_hash == new_hash and company.industry is not None: continue` |
| Log cache hits at INFO level | Operators need to see why a company was skipped | Low | `print(f"[CACHE HIT] {company.company_name} — skipping OpenAI call")` |
| Update `description_hash` after each successful analysis | Must keep the hash current so future runs detect changes | Low | Set `company.description_hash = new_hash` before committing the analysis |

**Specific answers to design questions:**

- **Force-refresh mechanism?** Yes — a `--force-refresh` CLI flag. When set, bypass the hash check entirely (re-analyze every company). Implementation: pass boolean to the analysis loop; if True, always call OpenAI regardless of hash. This is a differentiator (not table stakes) but low complexity.
- **How to log cache hits?** `print(f"[CACHE HIT] {name}")` at pipeline level, and include in the summary count: `"50 companies | 30 analyzed | 18 cached | 2 failed"`. No dedicated log file needed — stdout is sufficient for an internal batch script.
- **SHA-256 vs MD5?** SHA-256. MD5 has collision vulnerabilities (not relevant here, but no reason to use it). SHA-256 is stdlib, equally fast for short strings, and produces a 64-char hex that fits in a TEXT column.

---

### Feature 4: Simple Frontend

**What it is:** An HTML page served by FastAPI that renders company cards with a filter dropdown. Browser-based; no separate server.

| Table Stakes Feature | Why Required | Complexity | Implementation Notes |
|---------------------|-------------|------------|---------------------|
| Company cards showing name, industry, business_model, summary, website link | Users need to scan companies visually | Low | Jinja2 template; each card is a `<div>` with these fields |
| Industry filter dropdown | Primary filter use case | Low | `<select>` populated with `SELECT DISTINCT industry FROM company` |
| Filter implemented client-side with JavaScript | Avoids page reload for 50 records; simpler UX | Low | `data-industry` attribute on each card; JS shows/hides on select change |
| Tailwind CSS via CDN | Zero build step; professional grid layout | Low | `<script src="https://cdn.tailwindcss.com"></script>` — no npm, no node |
| Served from FastAPI at `GET /` or `GET /ui` | Single server, no separate static hosting | Low | `fastapi.templating.Jinja2Templates`; `Jinja2Templates(directory="templates")` |
| Template file in `templates/index.html` | Separation of HTML from Python | Low | FastAPI's standard Jinja2 directory convention |
| `StaticFiles` mount (optional, for future CSS/JS files) | Needed if extracting JS/CSS to separate files | Low | `app.mount("/static", StaticFiles(directory="static"), name="static")` |

**Specific answers to design questions:**

- **What should cards show?** `company_name` (as heading), `industry` (badge/tag), `business_model` (secondary badge), `summary` (body text), `website` (link, target=_blank). Omit `use_case` and raw `description` from the card — too verbose. Show them in an expanded/detail view only (differentiator).
- **Client-side JS or server-side filtering?** Client-side for v1.1. At <100 records, all cards are already in the DOM — a `data-industry` attribute + 5 lines of JS is instant. Server-side form submission works but causes full page reload. Client-side is faster UX and simpler to implement at this scale. Exception: `?q=` text search should call the server-side endpoint (`GET /companies?q=`) to leverage SQL search.
- **Simplest approach?** Jinja2 template with Tailwind CDN. Jinja2 is already installed (v3.1.6 confirmed in venv as a transitive dependency of `fastapi[standard]`). No new dependencies. No build step. This is a 1-file HTML template.

---

### Feature 5: CI/CD Pipeline

**What it is:** Two GitHub Actions workflows: (1) run pytest on push/PR, (2) agentic code review comment on PRs using pr-agent.

| Table Stakes Feature | Why Required | Complexity | Implementation Notes |
|---------------------|-------------|------------|---------------------|
| `.github/workflows/ci.yml` that runs `pytest` on push to main and on PRs | Catches regressions before merge | Low | `actions/setup-python@v5` + `pip install -r requirements.txt` + `pytest` |
| Single Python version (3.11) — no matrix | Internal tool; matrix is overkill | Low | `python-version: "3.11"` in `ci.yml` |
| Fail-fast on test failure | PRs must not merge with broken tests | Low | Default GitHub Actions behavior |
| `.github/workflows/pr_agent.yml` using `qodo-ai/pr-agent@main` | AI review comments on PRs | Low | Requires `OPENAI_KEY` secret; `GITHUB_TOKEN` auto-created |
| Trigger pr-agent on PR open, reopen, ready-for-review | Review on every new/updated PR | Low | `on: pull_request: types: [opened, reopened, ready_for_review]` |
| Skip bot-created PRs | Prevents review loops | Low | `if: ${{ github.event.sender.type != 'Bot' }}` |
| Secrets: `OPENAI_KEY` in repo Settings | pr-agent needs OpenAI to generate reviews | Low | Repository Settings → Secrets → Actions |

**Specific answers to design questions:**

- **What should the agentic reviewer comment on?** Changed files only (default pr-agent behavior). pr-agent fetches the diff and reviews only lines added/modified in the PR. It comments on: logic bugs, missing error handling, code style issues, test coverage gaps. It does NOT re-review unmodified files.
- **Whole PR or just changed files?** Just changed files (diff-based). This is pr-agent's default and correct behavior — avoids noise from flagging pre-existing issues in unchanged code.
- **How to avoid review noise?** Three settings in a `.pr_agent.toml` or `configuration.toml` at repo root:
  ```toml
  [pr_reviewer]
  num_code_suggestions = 3        # max 3 suggestions per PR (not 10+)
  inline_code_comments = true     # put comments on specific lines, not a wall of text
  extra_instructions = "Focus on Python correctness, error handling, and test coverage. Ignore minor style issues handled by ruff."
  ```
  Also: do NOT trigger on `pull_request: types: [synchronize]` (avoid re-review on every push to the PR branch) — trigger only on open/reopen.
- **Issue_comment trigger?** Include it (allows manual `/review` and `/improve` commands in PR comments) but it's a differentiator, not table stakes.

---

## Differentiators

Nice-to-have additions that improve quality without blocking the core use case.

### Feature 1: MCP Server — Differentiators

| Differentiator | Value | Complexity |
|----------------|-------|------------|
| `get_companies_by_business_model(model)` tool | Common second filter for agents | Low |
| MCP Resources (`company://{id}`) for read-only context injection | Semantically cleaner for context vs action | Medium |
| `mcp dev` inspector integration | Debug tool calls interactively during development | Low (zero code, just `mcp dev agent/mcp_server.py`) |
| Expose MCP server URL in README with Claude Desktop config | Makes the server immediately usable | Low (documentation only) |

### Feature 2: Filtering / Search — Differentiators

| Differentiator | Value | Complexity |
|----------------|-------|------------|
| `?business_model=` filter | Second most common filter after industry | Low |
| FTS5 virtual table for `?q=` | Ranked results, prefix search, stemming vs LIKE substring | Medium (requires migration + sync trigger) |
| `GET /companies/stats` — counts by industry/business_model | Dataset overview for dashboards and agents | Low (SQL GROUP BY) |
| `?sort=name` or `?sort=created_at` | Predictable ordering | Low |

### Feature 3: AI Caching — Differentiators

| Differentiator | Value | Complexity |
|----------------|-------|------------|
| `--force-refresh` CLI flag | Re-analyze all companies without re-scraping | Low |
| Cache hit counter in pipeline summary output | `"18 cached, 30 analyzed, 2 failed"` at end of run | Low |
| `analysis_model` field stores which model produced each record | Compare gpt-4o-mini vs gpt-4o output quality | Low |

### Feature 4: Simple Frontend — Differentiators

| Differentiator | Value | Complexity |
|----------------|-------|------------|
| Text search box wired to `GET /companies?q=` | Full-text search from the UI | Low |
| Company count label ("Showing X of Y") | Feedback when filter reduces results | Low |
| Expandable card detail view | Show `use_case` and raw `description` on click | Low (CSS + 10 lines JS) |
| Responsive grid (Tailwind `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`) | Usable on laptop and wide monitor | Low (Tailwind classes only) |

### Feature 5: CI/CD — Differentiators

| Differentiator | Value | Complexity |
|----------------|-------|------------|
| `pytest-cov` coverage report posted to PR as comment | Coverage visibility without extra tooling | Low |
| `ruff` lint step in CI | Catches Python style issues before review | Low |
| Issue comment trigger for `/review` and `/improve` commands | Manual re-review and improvement suggestions on demand | Low |
| PR status check blocks merge on failing tests | Enforced quality gate | Low (branch protection rule in GitHub settings) |

---

## Anti-Features

Things to explicitly NOT build for v1.1. Building these adds complexity without proportional value at this stage.

| Anti-Feature | Feature | Why Avoid | What to Do Instead |
|--------------|---------|-----------|-------------------|
| **Stdio transport for MCP** | MCP Server | Only useful for local Claude Desktop; HTTP is universal and production-ready | Use `stateless_http=True` transport — works for all agents |
| **MCP Authentication** | MCP Server | Internal tool; adds OAuth/JWT complexity with no security benefit | Skip entirely; revisit if MCP server becomes externally facing |
| **MCP Resources instead of Tools** | MCP Server | Resources are for static context injection; tools are for queries. Agents need tools | Use `@mcp.tool()` for all three exposed operations |
| **FTS5 for v1.1 search** | Filtering | Requires schema migration (new virtual table), sync triggers, and different query syntax. LIKE is correct at 50 records | Use `LIKE '%q%'` now; migrate to FTS5 when record count or search quality demands it |
| **Pagination** | Filtering | 50 records, sub-millisecond DB queries. Pagination UI adds complexity with zero performance benefit | Return all matches; add pagination at 500+ records |
| **Redis or external cache** | AI Caching | Overkill for a local SQLite batch pipeline | Store `description_hash` in the Company row itself |
| **TTL-based cache expiry** | AI Caching | Adds time-based invalidation logic; hash-based is correct (description change = stale) | Use hash check only; `--force-refresh` for manual invalidation |
| **React/Vue/Next.js frontend** | Frontend | No build toolchain; all three require Node.js, npm, and a build step. 1-file Jinja2 template achieves the same goal | Jinja2 template + Tailwind CDN |
| **Dedicated frontend server** | Frontend | Two processes to run is harder to document and deploy | Serve HTML from FastAPI at `/` |
| **Matrix CI across Python 3.9/3.10/3.11/3.12** | CI/CD | Internal tool; one version is enough | Pin to Python 3.11 only |
| **Docker build in CI** | CI/CD | Project is not containerized (v1.0 decision). Adding Docker to CI validates nothing useful | Skip Docker entirely through v1.x |
| **Auto-merge on passing tests** | CI/CD | Risky; merges PRs before human review; noisy | Require human approval + passing CI; pr-agent comment is advisory not blocking |
| **Multiple AI review tools** | CI/CD | Running two AI reviewers produces conflicting comments | Use pr-agent only; it covers review + improvement suggestions |

---

## Feature Dependencies

```
v1.0 Foundation (already built)
  ├── Company SQLModel table (company_name, description, industry, ...)
  ├── GET /companies + GET /companies/{id}
  └── run_pipeline.py (scrape → analyze → store)
        │
        ├── Feature 2: Filtering/Search
        │     └── Adds ?industry= and ?q= query params to GET /companies
        │         No schema changes required
        │
        ├── Feature 3: AI Caching
        │     └── Adds description_hash column to Company table
        │         Modifies run_pipeline.py analysis loop
        │         No API changes
        │
        ├── Feature 4: Simple Frontend
        │     └── Adds GET / route serving Jinja2 template
        │         DEPENDS ON Feature 2 (uses ?q= endpoint for text search)
        │         No DB changes
        │
        ├── Feature 1: MCP Server
        │     └── Mounts at /mcp on existing FastAPI app
        │         DEPENDS ON Feature 2 (search_companies tool reuses filter logic)
        │         No DB changes
        │
        └── Feature 5: CI/CD Pipeline
              └── GitHub Actions workflows in .github/workflows/
                  No application code changes
                  Independent of all other features
```

**Critical ordering for implementation:**
1. Feature 3 (caching) first — it requires a DB schema migration (`description_hash` column). Do this before any other features so the migration only happens once.
2. Feature 2 (filtering) second — shared filter logic is used by both Feature 4 (frontend) and Feature 1 (MCP server). Build once, reuse twice.
3. Feature 1 (MCP server) and Feature 4 (frontend) can be built in any order after Feature 2.
4. Feature 5 (CI/CD) is independent — can be done at any point, but doing it early catches regressions from Features 1-4.

---

## MVP Definition for v1.1

### Must Have (v1.1 table stakes — build all of these)

**Feature 2 — Filtering:**
1. `?industry=` case-insensitive filter on `GET /companies`
2. `?q=` LIKE search across `company_name` + `description` on `GET /companies`

**Feature 3 — AI Caching:**
3. `description_hash` column added to Company table
4. Hash check in `run_pipeline.py` before each OpenAI call (skip if match + fields populated)
5. Log cache hits to stdout

**Feature 1 — MCP Server:**
6. `FastMCP` server mounted at `/mcp` on existing FastAPI app
7. Three tools: `search_companies`, `get_company`, `list_industries`
8. Structured Pydantic return types on all tools

**Feature 4 — Frontend:**
9. `GET /` serves Jinja2 template with company cards
10. Industry filter dropdown (client-side JS)
11. Tailwind CSS via CDN

**Feature 5 — CI/CD:**
12. `.github/workflows/ci.yml` running pytest on push + PR
13. `.github/workflows/pr_agent.yml` with pr-agent for AI code review

### Should Have (low effort, high value — add if time allows)

- `--force-refresh` CLI flag for cache bypass
- `?business_model=` filter alongside `?industry=`
- Cache hit counter in pipeline summary
- `ruff` lint step in CI
- Text search box in frontend wired to `?q=` endpoint

### Defer (v1.2+)

- FTS5 full-text search (replaces LIKE, requires migration)
- MCP Resources alongside Tools
- Frontend expandable card detail view
- Coverage reporting in CI
- `GET /companies/stats` endpoint

---

## Prioritization Matrix

| Feature | Value | Effort | Risk | Priority |
|---------|-------|--------|------|----------|
| **Filtering (Feature 2)** | High — unlocks all API consumers | Low | Low | **1st** |
| **AI Caching (Feature 3)** | High — saves API costs on re-runs | Low | Low (schema migration) | **2nd** |
| **CI/CD (Feature 5)** | Medium — safety net for new features | Low | Low | **3rd** (early, catches bugs) |
| **MCP Server (Feature 1)** | High — core v1.1 differentiator | Medium | Low | **4th** |
| **Frontend (Feature 4)** | Medium — demo-able UI | Low | Low | **5th** |

---

## Sources

- **MCP Python SDK** — `mcp==1.27.0` on PyPI (verified 2026-04-07). Official README: `https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md`. FastMCP Tools, Structured Output, ASGI Mounting sections — HIGH confidence.
- **SQLite LIKE case-insensitivity** — verified via live Python test: `LIKE 'fintech'` matches 'FinTech', 'fintech', 'FINTECH' (ASCII). `LOWER()` comparison also confirmed working — HIGH confidence.
- **SQLite FTS5** — verified available in Python stdlib `sqlite3`: `CREATE VIRTUAL TABLE USING fts5(...)` confirmed working with prefix search — HIGH confidence.
- **Jinja2** — `jinja2==3.1.6` confirmed installed in project venv (transitive dep of `fastapi[standard]`) — HIGH confidence.
- **pr-agent** — `pr-agent==0.3.0` by Qodo AI on PyPI. Official docs: `https://qodo-merge-docs.qodo.ai/installation/github/`. GitHub Action `qodo-ai/pr-agent@main` with `OPENAI_KEY` secret pattern confirmed — HIGH confidence.
- **hashlib.sha256** — Python stdlib, no installation needed. Used for description hash in caching — HIGH confidence.
- **Tailwind CSS CDN** — `https://cdn.tailwindcss.com` — zero build step pattern, well-established for internal tools — HIGH confidence.
