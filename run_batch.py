"""
Batch pipeline runner.

Reads a CSV of leads, generates a personalised video + email for each one,
uploads to R2, and pushes to the correct Smartlead campaign variant.

Usage examples:
  # Dry-run first — generates everything but does NOT push to Smartlead
  python3 run_batch.py --csv data/input/leads.csv --dry-run

  # Single lead (0-indexed) — good for testing one prospect end-to-end
  python3 run_batch.py --csv data/input/leads.csv --lead 0

  # Resume a partial run — skips leads already marked complete in ledger
  python3 run_batch.py --csv data/input/leads.csv --resume

  # Full production run
  python3 run_batch.py --csv data/input/leads.csv

Progress is written to ledger.sqlite so any crash can be resumed safely.
Results are also saved to data/output/results_YYYY-MM-DD.csv.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── project root on the path ─────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── rich progress bar (optional — falls back gracefully) ─────────────────────
try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, TextColumn,
    )
    from rich.table import Table
    from rich.live import Live
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "boto3", "botocore", "s3transfer",
                  "urllib3", "playwright", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


log = logging.getLogger("run_batch")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agentic Acquisition Platform — batch runner")
    p.add_argument("--csv",    default="data/input/leads.csv",
                   help="Path to leads CSV (default: data/input/leads.csv)")
    p.add_argument("--lead",   type=int, default=None, metavar="N",
                   help="Process only the N-th lead (0-indexed). Good for testing.")
    p.add_argument("--resume", action="store_true",
                   help="Skip leads already completed in ledger.sqlite")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Generate everything but do NOT push to Smartlead")
    p.add_argument("--concurrency", type=int, default=None,
                   help="Override max_concurrent_leads from settings.yaml")
    p.add_argument("--output-csv", default=None, dest="output_csv",
                   help="Path for results CSV (default: data/output/results_DATE.csv)")
    p.add_argument("--log-level", default="INFO", dest="log_level",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def _write_results_csv(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["lead_id", "status", "landing_url", "error"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def _print_summary_plain(results: list[dict], total_cost: float, elapsed: float) -> None:
    sent    = sum(1 for r in results if r["status"] == "sent")
    dry     = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed  = sum(1 for r in results if r["status"] == "failed")

    print(f"\n{'='*58}")
    print(f"  BATCH COMPLETE  —  {elapsed:.0f}s")
    print(f"{'='*58}")
    print(f"  Sent:     {sent + dry:>4}  {'(dry run)' if dry else ''}")
    print(f"  Skipped:  {skipped:>4}")
    print(f"  Failed:   {failed:>4}")
    print(f"  Cost:     ${total_cost:.3f}")
    print(f"{'='*58}\n")


def _print_summary_rich(results: list[dict], total_cost: float, elapsed: float,
                        output_csv: Path, console: "Console") -> None:
    sent    = sum(1 for r in results if r["status"] in ("sent", "dry_run"))
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed  = sum(1 for r in results if r["status"] == "failed")

    t = Table(title=f"Batch Complete — {elapsed:.0f}s", show_header=False,
              title_style="bold green")
    t.add_column("Label",  style="dim", width=12)
    t.add_column("Value",  style="bold")
    t.add_row("Sent",     str(sent))
    t.add_row("Skipped",  str(skipped))
    t.add_row("Failed",   str(failed))
    t.add_row("Cost",     f"${total_cost:.3f}")
    t.add_row("Results",  str(output_csv))
    console.print(t)

    if failed:
        console.print("\n[bold red]Failed leads:[/bold red]")
        for r in results:
            if r["status"] == "failed":
                console.print(f"  [red]✗[/red]  {r['lead_id']}  —  {r.get('error', '')[:80]}")


async def main() -> None:
    args = _parse_args()
    _setup_logging(args.log_level)

    from src.utils.settings import Settings
    from src.utils.ledger import Ledger
    from src.utils.cost_tracker import CostTracker
    from src.ingestion.csv_reader import read_leads
    from src.ai_cold_email.orchestrator.pipeline import process_lead
    from src.enrichment.website import init_shared_browser, close_shared_browser

    settings = Settings()

    # Override concurrency if flag given
    if args.concurrency:
        # Pydantic model is frozen; bypass via __dict__
        object.__setattr__(settings, "max_concurrent_leads", args.concurrency)

    # Validate R2 credentials early — fail fast with a clear message
    if not args.dry_run:
        if not settings.cloudflare_r2_account_id or \
           "example.com" in settings.cloudflare_r2_public_url:
            log.error(
                "R2 credentials not configured. Run  python3 tools/setup_r2.py  "
                "to check your setup, or add --dry-run to skip uploads."
            )
            sys.exit(1)

    # Load leads
    csv_path = Path(args.csv)
    if not csv_path.exists():
        log.error("CSV not found: %s", csv_path)
        log.error("Put your leads at  data/input/leads.csv  or pass --csv PATH")
        sys.exit(1)

    leads = read_leads(csv_path)
    if not leads:
        log.error("No valid leads found in %s — check required columns.", csv_path)
        sys.exit(1)

    # Apply filters
    if args.lead is not None:
        if args.lead >= len(leads):
            log.error("--lead %d out of range (CSV has %d leads)", args.lead, len(leads))
            sys.exit(1)
        leads = [leads[args.lead]]
        log.info("Single-lead mode: processing %s @ %s",
                 leads[0]["first_name"], leads[0]["company"])
    elif args.resume:
        ledger_check = Ledger("ledger.sqlite")
        before = len(leads)
        leads = [l for l in leads if not ledger_check.is_complete(l["lead_id"])]
        log.info("Resume mode: %d/%d leads remaining", len(leads), before)

    if not leads:
        log.info("Nothing to do.")
        return

    log.info(
        "Starting batch: %d leads | concurrency=%d | dry_run=%s",
        len(leads), settings.max_concurrent_leads, args.dry_run,
    )
    if args.dry_run:
        log.info("DRY RUN — videos will be generated but Smartlead push is skipped.")

    ledger       = Ledger("ledger.sqlite")
    cost_tracker = CostTracker(daily_budget_usd=settings.max_daily_budget_usd)
    semaphore    = asyncio.Semaphore(settings.max_concurrent_leads)

    results: list[dict] = []
    start   = time.monotonic()

    # Start a single shared Chromium browser for all leads.
    # Each lead gets its own isolated context — state never leaks between leads.
    # Saves ~60 % RAM and ~8 process launches vs. one browser per lead.
    await init_shared_browser()

    # ── Progress display ──────────────────────────────────────────────────────
    if _HAS_RICH:
        console = Console()
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        prog_task = progress.add_task("Processing leads", total=len(leads))
    else:
        progress = None
        prog_task = None
        console = None

    async def bounded(lead: dict) -> dict:
        async with semaphore:
            try:
                result = await process_lead(
                    lead, settings, ledger, cost_tracker, args.dry_run
                )
            except Exception as e:
                log.error("[%s] FAILED: %s", lead["lead_id"], e, exc_info=True)
                ledger.mark_failed(lead["lead_id"], str(e))
                result = {"lead_id": lead["lead_id"], "status": "failed", "error": str(e)}

            results.append(result)
            status_icon = {
                "sent":    "✓",
                "dry_run": "~",
                "skipped": "–",
                "failed":  "✗",
            }.get(result.get("status", ""), "?")

            if progress and prog_task is not None:
                progress.advance(prog_task)
                progress.print(
                    f"  {status_icon}  {lead['first_name']} @ {lead['company']}"
                    + (f"  →  {result.get('landing_url', '')}" if result.get("landing_url") else "")
                )
            else:
                log.info(
                    "[%s] %s  %s @ %s",
                    result.get("status", "?").upper(),
                    status_icon,
                    lead["first_name"],
                    lead["company"],
                )
            return result

    # Run all leads
    try:
        if progress:
            with progress:
                await asyncio.gather(*(bounded(lead) for lead in leads))
        else:
            await asyncio.gather(*(bounded(lead) for lead in leads))
    finally:
        # Always shut down the shared browser, even if the batch crashes mid-run
        await close_shared_browser()

    elapsed = time.monotonic() - start

    # Write results CSV
    date_str    = datetime.utcnow().strftime("%Y-%m-%d")
    output_csv  = Path(args.output_csv) if args.output_csv else \
                  Path(f"data/output/results_{date_str}.csv")
    _write_results_csv(results, output_csv)
    log.info("Results saved to %s", output_csv)

    # Summary
    total_cost = cost_tracker.total()
    if _HAS_RICH and console:
        _print_summary_rich(results, total_cost, elapsed, output_csv, console)
    else:
        _print_summary_plain(results, total_cost, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
