"""
Pipeline orchestrator: scrape YC companies then run AI analysis on each.

Usage:
    python scripts/run_pipeline.py

The pipeline is idempotent:
  - Scraper uses upsert — re-running never creates duplicate records.
  - Analyzer skips companies where industry IS NOT NULL — re-running is safe.
  - Per-company commit — partial runs preserve already-analyzed companies.

This is the ONLY file that imports from all three domains:
  app/     — database engine and Company model
  scraper/ — YC API fetch
  agent/   — OpenAI analyzer
"""
import logging

from dotenv import load_dotenv
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Company
from scraper.yc_scraper import fetch_companies
from agent.analyzer import analyze_company, compute_description_hash

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    """Run the full scrape → analyze → store pipeline."""
    create_db_and_tables()

    # ------------------------------------------------------------------
    # Step 1: Scrape — fetch YC companies from the API and upsert into DB
    # ------------------------------------------------------------------
    logger.info("Scraping YC companies...")
    fetch_companies()

    # ------------------------------------------------------------------
    # Step 2: Analyze — iterate companies, skip already-done, call OpenAI
    # ------------------------------------------------------------------
    with Session(engine) as session:
        companies = session.exec(select(Company)).all()
        total = len(companies)
        skipped = 0
        analyzed = 0
        failed = 0

        for i, company in enumerate(companies, 1):
            # Two-condition cache check (CACHE-01):
            # Hash match alone is insufficient — partial write (hash stored but
            # analysis failed) must trigger re-analysis.
            computed_hash = compute_description_hash(company.description or "")
            is_cache_hit = (
                computed_hash is not None
                and company.description_hash == computed_hash
                and company.industry is not None
            )
            if is_cache_hit:
                logger.info(f"[CACHE HIT] {company.company_name}")
                skipped += 1
                continue

            logger.info(f"[{i}/{total}] Analyzing: {company.company_name}")
            try:
                result = analyze_company(
                    company.company_name, company.description or ""
                )
                if result is None:
                    # analyze_company already logged the error; count and move on
                    failed += 1
                    continue

                # Write AI fields — always store .value (str), not the enum object
                company.industry = result.industry.value
                company.business_model = result.business_model
                company.summary = result.summary
                company.use_case = result.use_case
                company.description_hash = computed_hash   # CACHE-02: store hash
                session.add(company)
                session.commit()   # per-company commit — partial runs survive crashes
                analyzed += 1

            except Exception as exc:
                # Safety net: analyze_company should never raise, but be defensive
                logger.error(
                    f"Unexpected error for {company.company_name}: {exc}"
                )
                session.rollback()
                failed += 1

    logger.info(
        f"Done. analyzed={analyzed} skipped={skipped} failed={failed}"
    )


if __name__ == "__main__":
    run()
