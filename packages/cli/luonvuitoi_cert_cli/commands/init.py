"""``lvt-cert init`` — scaffold a new certificate portal project.

Copies the skeleton under ``scaffolds/`` into ``<target>``, runs an interactive
prompt (non-interactive mode available for CI), and emits a ready-to-edit
``cert.config.json`` plus a minimal set of templates.

Phase 01 ships a stub so the command is discoverable; the real scaffold lives
in Phase 11.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Scaffold a new certificate portal project.")
console = Console()


@app.callback(invoke_without_command=True)
def init_project(
    target: Path = typer.Argument(..., help="Destination directory for the new project."),
    example: str = typer.Option("demo-academy", help="Example to copy (demo-academy is the only one shipped in v0.1)."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Skip prompts; accept all defaults."),
) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        console.print(f"[red]✗ {target} exists and is not empty.[/]")
        raise typer.Exit(code=1)
    console.print(f"[yellow]• scaffolder not implemented yet (Phase 11).[/] Target: {target}, example: {example}")
    if non_interactive:
        console.print("  --non-interactive accepted; nothing copied.")
