"""
Analytics CLI.

Usage:
    python -m src.analytics report             # full text report
    python -m src.analytics report --frameworks # framework-only roll-up
    python -m src.analytics report --heatmap   # framework x motion heatmap
    python -m src.analytics insights           # AI-generated patterns
    python -m src.analytics significance       # quick significance check
"""
from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from src.analytics.queries import (
    cost_summary,
    framework_motion_heatmap,
    framework_stats,
    significance_status,
    variant_stats,
    variant_vertical_heatmap,
)

console = Console()
log = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--frameworks", is_flag=True, help="Framework-only roll-up")
@click.option("--heatmap", is_flag=True, help="Framework x motion heatmap")
@click.option("--vertical", is_flag=True, help="Variant x vertical heatmap")
@click.option("--db", default="ledger.sqlite", type=click.Path())
def report(frameworks: bool, heatmap: bool, vertical: bool, db: str) -> None:
    """Print analytics report."""
    from src.utils.settings import load_settings

    settings = load_settings()
    test = settings.active_test_config()
    if not test:
        console.print("[yellow]No active test in settings.yaml[/yellow]")
        return

    db_path = Path(db)

    # Default: full report. Flags narrow to a section.
    show_all = not (frameworks or heatmap or vertical)
    primary = test.get("primary_metric", "reply_rate")

    if show_all or frameworks:
        _print_framework_table(db_path, test["id"], primary)
    if show_all or heatmap:
        _print_framework_motion_heatmap(db_path, test["id"])
    if show_all:
        _print_variant_table(db_path, test["id"], primary, test)
    if vertical:
        _print_variant_vertical_heatmap(db_path, test["id"])
    if show_all:
        _print_cost_summary(db_path, test["id"])


def _print_framework_table(db_path: Path, test_id: str, primary: str) -> None:
    stats = framework_stats(db_path, test_id)
    if not stats:
        return

    leader = max(stats, key=lambda s: getattr(s, primary))

    t = Table(title="Framework leaderboard (roll-up across variants)")
    t.add_column("Framework")
    t.add_column("Variants")
    t.add_column("Sent", justify="right")
    t.add_column("Open%", justify="right")
    t.add_column("Reply%", justify="right")
    t.add_column("Booked", justify="right")
    t.add_column("Book%", justify="right")

    for s in sorted(stats, key=lambda s: getattr(s, primary), reverse=True):
        is_leader = s.framework == leader.framework
        marker = "  ← leading" if is_leader else ""
        style = "bold green" if is_leader else ""
        t.add_row(
            f"{s.framework}{marker}",
            ", ".join(s.variant_ids[:3]) + ("..." if len(s.variant_ids) > 3 else ""),
            f"{s.sent:,}",
            f"{s.open_rate * 100:.1f}",
            f"{s.reply_rate * 100:.2f}",
            f"{s.booked}",
            f"{s.book_rate * 100:.2f}",
            style=style,
        )
    console.print(t)
    console.print()


def _print_framework_motion_heatmap(db_path: Path, test_id: str) -> None:
    cells = framework_motion_heatmap(db_path, test_id)
    if not cells:
        return

    frameworks = sorted(set(c.row_key for c in cells))
    motions = sorted(set(c.col_key for c in cells))
    grid = {(c.row_key, c.col_key): c for c in cells}

    t = Table(title="Reply rate (%) by framework × motion")
    t.add_column("Framework")
    for m in motions:
        t.add_column(m, justify="right")
    t.add_column("All", justify="right", style="dim")

    for f in frameworks:
        row_cells = [grid.get((f, m)) for m in motions]
        row = [f]
        agg_sent, agg_replied = 0, 0
        for cell in row_cells:
            if cell and cell.sent:
                row.append(f"{cell.reply_rate * 100:.1f} ({cell.sent:,})")
                agg_sent += cell.sent
                agg_replied += cell.replied
            else:
                row.append("—")
        agg_rate = (agg_replied / agg_sent * 100) if agg_sent else 0
        row.append(f"{agg_rate:.1f}")
        t.add_row(*row)
    console.print(t)
    console.print(
        "[dim]Each cell: reply % (sent count). "
        "Brighter = better. Cells under 50 sent are hidden.[/dim]"
    )
    console.print()


def _print_variant_table(
    db_path: Path, test_id: str, primary: str, test: dict
) -> None:
    stats = variant_stats(db_path, test_id)
    if not stats:
        return

    sig = significance_status(
        stats, test.get("minimum_sent_per_variant", 1500), primary
    )

    leader_id = sig.get("leader_variant_id")

    t = Table(title="Variant detail")
    t.add_column("Variant")
    t.add_column("Framework")
    t.add_column("Sent", justify="right")
    t.add_column("Open%", justify="right")
    t.add_column("Reply%", justify="right")
    t.add_column("Click%", justify="right")
    t.add_column("Booked", justify="right")
    t.add_column("Book%", justify="right")

    for s in sorted(stats, key=lambda s: getattr(s, primary), reverse=True):
        is_leader = s.variant_id == leader_id
        is_sig_loser = s.variant_id in sig.get("significant_winners", [])
        marker = "  ← leading" if is_leader else ""
        style = "bold green" if is_leader else "dim" if is_sig_loser else ""
        t.add_row(
            f"{s.variant_id}{marker}",
            s.framework,
            f"{s.sent:,}",
            f"{s.open_rate * 100:.1f}",
            f"{s.reply_rate * 100:.2f}",
            f"{s.click_rate * 100:.1f}",
            f"{s.booked}",
            f"{s.book_rate * 100:.2f}",
            style=style,
        )
    console.print(t)

    # Significance line
    if sig["ready"]:
        if sig["significant_winners"]:
            console.print(
                f"[green]Significance reached: {leader_id} "
                f"beats {len(sig['significant_winners'])} variants at 95% conf.[/green]"
            )
        else:
            console.print("[yellow]Min sample reached, no significant winner yet.[/yellow]")
    else:
        console.print(
            f"[yellow]NOT YET — need {sig['min_required']}/variant minimum, "
            f"min currently {sig['min_sent']:,}[/yellow]"
        )
    console.print()


def _print_variant_vertical_heatmap(db_path: Path, test_id: str) -> None:
    cells = variant_vertical_heatmap(db_path, test_id)
    if not cells:
        console.print("[dim]Not enough vertical data yet (need 50+ sent per cell).[/dim]")
        return

    t = Table(title="Reply rate (%) by variant × vertical (cells with 50+ sent)")
    t.add_column("Variant")
    t.add_column("Vertical")
    t.add_column("Sent", justify="right")
    t.add_column("Reply%", justify="right")
    t.add_column("Book%", justify="right")
    for c in sorted(cells, key=lambda c: -c.reply_rate):
        t.add_row(
            c.row_key,
            c.col_key,
            f"{c.sent:,}",
            f"{c.reply_rate * 100:.2f}",
            f"{c.book_rate * 100:.2f}",
        )
    console.print(t)
    console.print()


def _print_cost_summary(db_path: Path, test_id: str) -> None:
    cs = cost_summary(db_path, test_id)
    console.print(
        f"[bold]Pipeline cost:[/bold] ${cs['total_cost_usd']:.2f} | "
        f"Booked: {cs['booked']} | "
        f"Cost/booked: "
        + (f"${cs['cost_per_booked']:.2f}" if cs["cost_per_booked"] else "—")
    )


@cli.command()
@click.option("--db", default="ledger.sqlite", type=click.Path())
def insights(db: str) -> None:
    """AI-generated insights from current variant + framework data."""
    from src.analytics.insights_generator import generate_insights

    text = generate_insights(Path(db))
    console.print(text)


@cli.command()
@click.option("--db", default="ledger.sqlite", type=click.Path())
def significance(db: str) -> None:
    """Quick significance check."""
    from src.utils.settings import load_settings

    settings = load_settings()
    test = settings.active_test_config()
    if not test:
        console.print("[yellow]No active test[/yellow]")
        return

    stats = variant_stats(Path(db), test["id"])
    sig = significance_status(
        stats, test.get("minimum_sent_per_variant", 1500), test.get("primary_metric", "reply_rate")
    )
    console.print(sig)


if __name__ == "__main__":
    cli()
