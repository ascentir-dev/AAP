"""
Pipeline orchestrator.

Usage:
    python -m src.orchestrator --csv data/input/leads.csv
    python -m src.orchestrator --csv data/input/leads.csv --single-lead 0
    python -m src.orchestrator --csv data/input/leads.csv --resume
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

from src.ai_cold_email.orchestrator.pipeline import run_pipeline
from src.utils.settings import load_settings

console = Console()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.command()
@click.option("--csv", "csv_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--single-lead", type=int, default=None, help="Run only this row index (0-based)")
@click.option("--resume", is_flag=True, help="Skip leads already processed in ledger")
@click.option("--dry-run", is_flag=True, help="Skip Smartlead push (everything else runs)")
def main(csv_path: Path, single_lead: int | None, resume: bool, dry_run: bool) -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    console.print(f"[bold cyan]Lead Personalization Pipeline[/bold cyan]")
    console.print(f"CSV: {csv_path}")
    if single_lead is not None:
        console.print(f"Mode: single lead (row {single_lead})")
    elif resume:
        console.print("Mode: resume")
    else:
        console.print("Mode: full run")
    if dry_run:
        console.print("[yellow]DRY RUN — Smartlead push disabled[/yellow]")

    asyncio.run(
        run_pipeline(
            csv_path=csv_path,
            single_lead_index=single_lead,
            resume=resume,
            dry_run=dry_run,
            settings=settings,
        )
    )


if __name__ == "__main__":
    main()
