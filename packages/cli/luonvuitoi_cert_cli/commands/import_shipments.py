"""``lvt-cert import-shipments`` — bulk-import carrier Excel/CSV into shipments.

Parses a carrier export, matches SBD via ``data_mapping.phone_col``, and
upserts rows into ``shipment_history``. Default behavior is a **dry run**
— operator inspects stats then re-runs with ``--commit`` to persist.

Config: ``features.shipment.import.profiles.<name>`` must be present. Select
the profile via ``--carrier <name>``, or rely on
``features.shipment.import.default``.
"""

from __future__ import annotations

import json as _json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def import_shipments(
    file_path: Path = typer.Argument(..., help="Carrier export file (.xlsx, .xlsm, .csv)."),
    round_id: str = typer.Option("main", "--round", "-r", help="Round id in config.rounds."),
    carrier: str | None = typer.Option(
        None,
        "--carrier",
        help="Profile name in features.shipment.import.profiles. Falls back to the configured default.",
    ),
    commit: bool = typer.Option(
        False, "--commit", help="Write to DB. Omit for dry-run preview (recommended first pass)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit stats as JSON to stdout instead of a table."
    ),
    config_path: Path = typer.Option(Path("cert.config.json"), "--config", "-c"),
    db_path: Path | None = typer.Option(None, "--db", help="Override the default data/<slug>.db path."),
) -> None:
    from luonvuitoi_cert.auth import ActivityLog
    from luonvuitoi_cert.config import load_config
    from luonvuitoi_cert.shipment import BulkImportError, bulk_import_shipments

    try:
        config = load_config(config_path)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]ERR[/] can't load config {config_path}: {e}")
        raise typer.Exit(code=2) from e

    resolved_db = (db_path or Path("data") / f"{config.project.slug}.db").expanduser().resolve()
    if not resolved_db.exists():
        console.print(f"[red]ERR[/] DB not found: {resolved_db}")
        raise typer.Exit(code=2)

    activity = ActivityLog(resolved_db, gsheet_webhook_url=os.getenv("GSHEET_WEBHOOK_URL"))

    try:
        stats = bulk_import_shipments(
            config=config,
            db_path=resolved_db,
            activity=activity,
            file_path=file_path,
            round_id=round_id,
            carrier=carrier,
            commit=commit,
        )
    except BulkImportError as e:
        console.print(f"[red]ERR[/] {e}")
        raise typer.Exit(code=1) from e

    if json_output:
        from dataclasses import asdict

        print(_json.dumps(asdict(stats), ensure_ascii=False, indent=2))
        return

    banner = "[yellow]DRY RUN — no DB changes[/]" if not commit else "[green]COMMITTED[/]"
    console.print(f"\n[bold]Shipment bulk import[/] ({banner})")
    console.print(f"  carrier: [cyan]{stats.carrier}[/]")
    console.print(f"  round:   [cyan]{stats.round_id}[/]")
    console.print(f"  file:    {file_path}\n")

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_row("Parsed", str(stats.parsed))
    summary.add_row("Skipped (status prefix)", str(stats.skipped_prefix))
    summary.add_row("Skipped (no tracking)", str(stats.skipped_no_tracking))
    summary.add_row("Skipped (no phone)", str(stats.skipped_no_phone))
    summary.add_row("Matched SBDs", str(stats.matched_sbds))
    summary.add_row("Unmatched phones", str(stats.unmatched_phones))
    summary.add_row("Rows inserted", str(stats.inserted))
    summary.add_row("Success flag set", str(stats.success_count))
    console.print(summary)

    if stats.status_breakdown:
        console.print("\n[bold]Status breakdown[/]")
        breakdown = Table("✓", "Count", "Status", box=None, padding=(0, 1))
        for status, count in sorted(stats.status_breakdown.items(), key=lambda kv: kv[1], reverse=True):
            is_success = _is_success_preview(
                status,
                config.features.shipment.import_.profiles[stats.carrier].success_keywords
                if config.features.shipment.import_
                else [],
            )
            breakdown.add_row("✓" if is_success else " ", str(count), status)
        console.print(breakdown)

    if not commit:
        console.print("\n[yellow]Re-run with[/] [cyan]--commit[/] [yellow]to write these rows to the DB.[/]")


def _is_success_preview(status: str, keywords: list[str]) -> bool:
    up = (status or "").upper()
    return any(k.upper() in up for k in keywords)
