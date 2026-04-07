# AI Company Research Agent

## Current Milestone: v1.1 Agent-Accessible & Production-Ready

**Goal:** Extend the research agent with agentic integrations (MCP server), a usable frontend, smart AI caching, filtering/search on the REST API, and automated CI/CD code review.

**Target features:**
- MCP server (FastMCP, standalone Python process) — `list_companies`, `get_company`, `search_companies` tools reading from the shared SQLite DB
- Filtering/search — `?industry=` and `?q=` query params on `GET /companies`
- AI response caching — SHA-256 hash of description stored as `description_hash`; pipeline skips OpenAI call if hash already has a cached analysis
- Simple frontend — static HTML/JS page to browse company cards and filter by industry
- CI/CD pipeline — GitHub Actions workflow with agentic tool (Copilot/Claude) for automated PR code review comments

---

## What This Is

An internal tool that automates company/startup research and analysis. It scrapes company data from Y Combinator's startup directory, runs each company through an OpenAI-powered agent to generate structured insights (industry, business model, summary, use case), stores everything in a SQLite database, and exposes the results through a FastAPI REST API.

## Core Value

Any company in the database can be instantly retrieved with AI-generated insights — no manual research needed.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**v1.0 (in progress — Phases 1–4):**
- [ ] Collect at least 10 companies from Y Combinator directory via web scraping
- [ ] Each company record includes: name, website, description
- [ ] AI agent analyzes each company and generates: industry, business model, 1-sentence summary, potential use case
- [ ] All data (collected + AI-generated) stored in SQLite database
- [ ] `GET /companies` endpoint returns all companies with AI insights
- [ ] `GET /companies/{id}` endpoint returns full details for a specific company
- [ ] System handles edge cases: missing descriptions, ambiguous companies
- [ ] AI prompt is documented with rationale for design choices

**v1.1 (planned — Phases 5–9):**
- [ ] MCP server exposes company data as callable tools for agentic clients
- [ ] `GET /companies` supports `?industry=` and `?q=` filtering
- [ ] AI analysis pipeline caches responses by description hash to avoid redundant API calls
- [ ] Static frontend lets users browse and filter company insights in a browser
- [ ] GitHub Actions CI/CD triggers automated agentic code review on pull requests

### Out of Scope

- Authentication/API keys on the REST API — internal tool, not exposed publicly
- Real-time scraping on API request — scraping runs as a one-time batch job
- Frontend/UI — API only for v1
- Pagination on `/companies` — fewer than 100 records expected

## Context

- **Data source:** Y Combinator startup directory (scraping with AI-assisted collection)
- **LLM provider:** OpenAI (gpt-4o-mini for cost efficiency, gpt-4o as fallback for quality)
- **Backend:** FastAPI (Python) — aligns well with AI/data stack
- **Database:** SQLite — zero setup, file-based, sufficient for this scale
- **Audience:** Internal team evaluating AI agent workflows
- **Purpose:** Demonstrate agentic development pattern: collect → analyze → store → expose

## Constraints

- **LLM:** OpenAI API — requires `OPENAI_API_KEY` environment variable
- **Scale:** ~10–50 companies (batch), not high-throughput
- **Stack:** Python-only backend — no Node.js or separate services
- **Scraping:** Y Combinator public directory only — no login-walled content

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite over PostgreSQL | Zero setup, sufficient for batch size, portable | — Pending |
| FastAPI over Flask | Auto-generated docs, Pydantic validation, async support | — Pending |
| gpt-4o-mini for analysis | Cost-efficient for batch processing ~10-50 companies | — Pending |
| Scrape YC directory | No API key needed, rich startup data, AI-assisted parsing | — Pending |
| One-time batch collection | Simpler than scheduled jobs; re-run script to refresh | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-07 — Milestone v1.1 started*
