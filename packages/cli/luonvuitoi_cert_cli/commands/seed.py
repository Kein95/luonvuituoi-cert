"""``lvt-cert seed`` — generate fake student data for local testing.

Uses Faker to build a realistic Excel + seed SQLite DB. Columns respect the
project's ``cert.config.json`` ``data_mapping`` so you can round-trip without
editing anything.

Phase 01 ships a stub; real implementation lands in Phase 12 alongside the
``demo-academy`` example.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="Generate fake students for local testing.")
console = Console()


@app.callback(invoke_without_command=True)
def seed(
    count: int = typer.Option(10, "--count", "-n", min=1, max=10_000, help="Number of fake students."),
    locale: str = typer.Option("en_US", help="Faker locale (e.g., vi_VN, en_US)."),
) -> None:
    console.print(f"[yellow]• seed not implemented yet (Phase 12).[/] Would generate {count} students ({locale}).")
